"""
Pipeline Executor Service

Orchestrates the execution of trading pipelines by:
1. Loading pipeline configuration
2. Instantiating agents in the correct order
3. Managing pipeline state flow
4. Tracking execution progress
5. Handling errors and retries
"""
import structlog
import time
from typing import Dict, Any, List, Optional
from uuid import UUID, uuid4
from datetime import datetime

from app.schemas.pipeline_state import PipelineState
from app.models.pipeline import Pipeline
from app.models.execution import Execution, ExecutionStatus
from app.agents import get_registry
from app.agents.base import AgentError, TriggerNotMetException

logger = structlog.get_logger()

# Metrics (initialized lazily)
_metrics_helper = None

def _get_metrics():
    """Get metrics helper (lazy initialization)."""
    global _metrics_helper
    if _metrics_helper is None:
        try:
            from app.telemetry import get_meter, MetricsHelper
            _metrics_helper = MetricsHelper(get_meter())
        except:
            _metrics_helper = None  # Telemetry not available
    return _metrics_helper


class PipelineExecutor:
    """
    Executes a trading pipeline by running agents in sequence.
    
    This is the core execution engine that:
    - Validates pipeline configuration
    - Creates execution records
    - Runs agents in order
    - Manages state transitions
    - Handles errors gracefully
    - Tracks costs and performance
    
    Usage:
        executor = PipelineExecutor(pipeline_config, user_id)
        result = await executor.execute()
    """
    
    def __init__(
        self,
        pipeline: Pipeline,
        user_id: UUID,
        mode: str = "paper",
        execution_id: Optional[UUID] = None
    ):
        """
        Initialize the pipeline executor.
        
        Args:
            pipeline: Pipeline database model with config
            user_id: ID of user executing the pipeline
            mode: Execution mode ("live", "paper", "simulation", "validation")
            execution_id: Optional pre-created execution ID
        """
        self.pipeline = pipeline
        self.user_id = user_id
        self.mode = mode
        self.execution_id = execution_id or uuid4()
        
        self.registry = get_registry()
        self.logger = logger.bind(
            pipeline_id=str(pipeline.id),
            execution_id=str(self.execution_id),
            user_id=str(user_id)
        )
        
        # Parse pipeline config
        self.config = pipeline.config
        self.nodes = self.config.get("nodes", [])
        self.edges = self.config.get("edges", [])
        
        # Validate configuration
        self._validate_config()
    
    def _validate_config(self):
        """Validate pipeline configuration."""
        if not self.nodes:
            raise ValueError("Pipeline has no nodes configured")
        
        # Ensure all agent types exist in registry
        for node in self.nodes:
            agent_type = node.get("agent_type")
            if not self.registry.get_metadata(agent_type):
                raise ValueError(f"Unknown agent type: {agent_type}")
        
        self.logger.info("pipeline_config_validated", nodes=len(self.nodes), edges=len(self.edges))
    
    def _build_execution_order(self) -> List[Dict[str, Any]]:
        """
        Build the execution order based on edges using topological sort.
        
        Returns:
            List of nodes in execution order
            
        Raises:
            ValueError: If pipeline has cycles
        """
        # Build adjacency list and in-degree count
        node_map = {node["id"]: node for node in self.nodes}
        adjacency = {node["id"]: [] for node in self.nodes}
        in_degree = {node["id"]: 0 for node in self.nodes}
        
        # Build graph from edges (filter out tool connections)
        for edge in self.edges:
            from_id = edge.get("from") or edge.get("source")
            to_id = edge.get("to") or edge.get("target")
            
            # Skip tool connections (tools are not executed)
            if from_id in node_map and to_id in node_map:
                from_node = node_map[from_id]
                to_node = node_map[to_id]
                
                # Only add edge if both are agents (not tools)
                if from_node.get("node_category") != "tool" and to_node.get("node_category") != "tool":
                    adjacency[from_id].append(to_id)
                    in_degree[to_id] += 1
        
        # Topological sort using Kahn's algorithm
        queue = [node_id for node_id in in_degree if in_degree[node_id] == 0]
        execution_order = []
        
        while queue:
            # Sort queue to ensure deterministic order
            queue.sort()
            current = queue.pop(0)
            
            # Only add agents (not tools) to execution order
            if node_map[current].get("node_category") != "tool":
                execution_order.append(node_map[current])
            
            # Process neighbors
            for neighbor in adjacency[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # Check for cycles
        if len(execution_order) != len([n for n in self.nodes if n.get("node_category") != "tool"]):
            raise ValueError("Pipeline has cycles or disconnected nodes")
        
        self.logger.info("execution_order_built", steps=len(execution_order))
        return execution_order
    
    async def execute(self) -> PipelineState:
        """
        Execute the complete pipeline.
        
        Returns:
            Final pipeline state after all agents have run
            
        Raises:
            AgentError: If an agent fails critically
            TriggerNotMetException: If trigger conditions not met
        """
        self.logger.info("pipeline_execution_started")
        
        # Initialize pipeline state
        state = PipelineState(
            pipeline_id=self.pipeline.id,
            execution_id=self.execution_id,
            user_id=self.user_id,
            symbol=self.config.get("symbol", "UNKNOWN"),
            mode=self.mode
        )
        
        # Get execution order
        execution_order = self._build_execution_order()
        
        # Initialize agent states tracking
        agent_states = []
        for node in execution_order:
            agent_states.append({
                "agent_id": node["id"],
                "agent_type": node["agent_type"],
                "status": "pending",
                "started_at": None,
                "completed_at": None,
                "error": None,
                "cost": 0.0
            })
        
        # Execute each agent in sequence
        for i, node in enumerate(execution_order):
            agent_type = node["agent_type"]
            agent_id = node["id"]
            agent_config = node.get("config", {})
            
            # Update agent state to running
            agent_states[i]["status"] = "running"
            agent_states[i]["started_at"] = datetime.utcnow().isoformat()
            
            self.logger.info(
                "executing_agent",
                step=f"{i+1}/{len(execution_order)}",
                agent_type=agent_type,
                agent_id=agent_id
            )
            
            try:
                # Create agent instance
                agent = self.registry.create_agent(
                    agent_type=agent_type,
                    agent_id=agent_id,
                    config=agent_config
                )
                
                # Execute agent
                state = agent.process(state)
                
                # Update agent state to completed
                agent_states[i]["status"] = "completed"
                agent_states[i]["completed_at"] = datetime.utcnow().isoformat()
                agent_states[i]["cost"] = state.agent_costs.get(agent_id, 0.0)
                
                self.logger.info(
                    "agent_completed",
                    agent_type=agent_type,
                    cost=state.agent_costs.get(agent_id, 0.0)
                )
                
            except TriggerNotMetException as e:
                # Trigger not met - not an error, just skip execution
                self.logger.info("trigger_not_met", reason=str(e))
                state.trigger_met = False
                state.trigger_reason = str(e)
                agent_states[i]["status"] = "skipped"
                agent_states[i]["completed_at"] = datetime.utcnow().isoformat()
                agent_states[i]["error"] = "Trigger not met"
                break
                
            except AgentError as e:
                # Agent-specific error
                self.logger.error("agent_error", agent_type=agent_type, error=str(e))
                state.errors.append(f"Agent {agent_type} failed: {str(e)}")
                agent_states[i]["status"] = "failed"
                agent_states[i]["completed_at"] = datetime.utcnow().isoformat()
                agent_states[i]["error"] = str(e)
                
                # Decide whether to continue or abort
                if self._should_abort_on_error(agent_type, str(e)):
                    raise
                else:
                    # Continue to next agent
                    continue
                    
            except Exception as e:
                # Unexpected error
                self.logger.exception("unexpected_error", agent_type=agent_type)
                state.errors.append(f"Unexpected error in {agent_type}: {str(e)}")
                agent_states[i]["status"] = "failed"
                agent_states[i]["completed_at"] = datetime.utcnow().isoformat()
                agent_states[i]["error"] = str(e)
                raise
        
        # Mark completion
        state.completed_at = datetime.utcnow()
        
        # Store agent states in pipeline state for database persistence
        state.agent_execution_states = agent_states
        
        self.logger.info(
            "pipeline_execution_completed",
            total_cost=state.total_cost,
            errors=len(state.errors),
            warnings=len(state.warnings),
            trigger_met=state.trigger_met
        )
        
        return state
    
    def _should_abort_on_error(self, agent_type: str, error: str) -> bool:
        """
        Determine if pipeline should abort on this error.
        
        Some agents (like market data) are critical and should abort.
        Others (like reporting) can fail without stopping the pipeline.
        
        Args:
            agent_type: Type of agent that failed
            error: Error message
            
        Returns:
            True if should abort, False if should continue
        """
        # Critical agents that must succeed
        critical_agents = [
            "time_trigger",
            "market_data_agent",
            "risk_manager_agent"
        ]
        
        if agent_type in critical_agents:
            return True
        
        # Check for specific critical errors
        critical_errors = [
            "InsufficientDataError",
            "BudgetExceededException",
            "AuthenticationError"
        ]
        
        for critical_error in critical_errors:
            if critical_error in error:
                return True
        
        return False
    
    def execute_with_sync_db_tracking(self, db_session, execution):
        """
        Execute pipeline with real-time database updates (synchronous version for Celery).
        
        Args:
            db_session: Synchronous SQLAlchemy session
            execution: Execution database record
            
        Returns:
            Updated Execution record
        """
        # Import flag_modified for JSONB column tracking
        from sqlalchemy.orm.attributes import flag_modified
        
        # Track execution metrics
        start_time = time.time()
        metrics = _get_metrics()
        
        if metrics:
            exec_counter = metrics.counter(
                "pipeline_executions_total",
                description="Total pipeline executions"
            )
            exec_duration = metrics.histogram(
                "pipeline_execution_duration_seconds",
                description="Pipeline execution duration",
                unit="s"
            )
        
        # Initialize state
        state = PipelineState(
            pipeline_id=self.pipeline.id,
            execution_id=self.execution_id,
            user_id=self.user_id,
            symbol=self.config.get("symbol", "UNKNOWN"),
            mode=self.mode
        )
        
        # Get execution order
        execution_order = self._build_execution_order()
        
        # Initialize agent states tracking
        agent_states = []
        for node in execution_order:
            agent_states.append({
                "agent_id": node["id"],
                "agent_type": node["agent_type"],
                "status": "pending",
                "started_at": None,
                "completed_at": None,
                "error": None,
                "cost": 0.0
            })
        
        # Update execution with initial agent states
        execution.agent_states = agent_states
        db_session.commit()
        
        # Execute each agent in sequence
        for i, node in enumerate(execution_order):
            agent_type = node["agent_type"]
            agent_id = node["id"]
            agent_config = node.get("config", {})
            
            # Update agent state to running
            agent_states[i]["status"] = "running"
            agent_states[i]["started_at"] = datetime.utcnow().isoformat()
            
            # Update DB with current progress
            execution.agent_states = agent_states
            execution.logs = self._serialize_logs(state.execution_log)
            db_session.commit()
            
            self.logger.info(
                "executing_agent",
                step=f"{i+1}/{len(execution_order)}",
                agent_type=agent_type,
                agent_id=agent_id
            )
            
            try:
                # Create agent instance
                agent = self.registry.create_agent(
                    agent_type=agent_type,
                    agent_id=agent_id,
                    config=agent_config
                )
                
                # Execute agent
                state = agent.process(state)
                
                # Update agent state to completed
                agent_states[i]["status"] = "completed"
                agent_states[i]["completed_at"] = datetime.utcnow().isoformat()
                agent_states[i]["cost"] = state.agent_costs.get(agent_id, 0.0)
                
                # Update DB with progress
                execution.agent_states = agent_states
                execution.logs = self._serialize_logs(state.execution_log)
                execution.reports = self._serialize_reports(state.agent_reports)
                execution.cost = state.total_cost
                execution.cost_breakdown = state.agent_costs
                
                # Mark JSONB columns as modified so SQLAlchemy saves them
                flag_modified(execution, "agent_states")
                flag_modified(execution, "logs")
                flag_modified(execution, "reports")
                flag_modified(execution, "cost_breakdown")
                
                db_session.commit()
                
                self.logger.info(
                    "agent_completed",
                    agent_type=agent_type,
                    cost=state.agent_costs.get(agent_id, 0.0)
                )
                
            except TriggerNotMetException as e:
                # Trigger not met - mark current agent as skipped
                self.logger.info("trigger_not_met", reason=str(e))
                state.trigger_met = False
                state.trigger_reason = str(e)
                agent_states[i]["status"] = "skipped"
                agent_states[i]["completed_at"] = datetime.utcnow().isoformat()
                agent_states[i]["error"] = "Trigger not met"
                
                # Mark all remaining agents as skipped too
                for j in range(i + 1, len(agent_states)):
                    agent_states[j]["status"] = "skipped"
                    agent_states[j]["completed_at"] = datetime.utcnow().isoformat()
                    agent_states[j]["error"] = "Skipped due to trigger not met"
                
                execution.agent_states = agent_states
                flag_modified(execution, "agent_states")
                execution.reports = self._serialize_reports(state.agent_reports)
                flag_modified(execution, "reports")
                db_session.commit()
                raise
                
            except AgentError as e:
                # Agent-specific error
                self.logger.error("agent_error", agent_type=agent_type, error=str(e))
                state.errors.append(f"Agent {agent_type} failed: {str(e)}")
                agent_states[i]["status"] = "failed"
                agent_states[i]["completed_at"] = datetime.utcnow().isoformat()
                agent_states[i]["error"] = str(e)
                execution.agent_states = agent_states
                flag_modified(execution, "agent_states")
                execution.reports = self._serialize_reports(state.agent_reports)
                flag_modified(execution, "reports")
                db_session.commit()
                
                # Decide whether to continue or abort
                if self._should_abort_on_error(agent_type, str(e)):
                    raise
                else:
                    # Continue to next agent
                    continue
                    
            except Exception as e:
                # Unexpected error
                self.logger.exception("unexpected_error", agent_type=agent_type)
                state.errors.append(f"Unexpected error in {agent_type}: {str(e)}")
                agent_states[i]["status"] = "failed"
                agent_states[i]["completed_at"] = datetime.utcnow().isoformat()
                agent_states[i]["error"] = str(e)
                execution.agent_states = agent_states
                flag_modified(execution, "agent_states")
                execution.reports = self._serialize_reports(state.agent_reports)
                flag_modified(execution, "reports")
                db_session.commit()
                raise
        
        # Mark completion
        state.completed_at = datetime.utcnow()
        
        # Track execution completion metrics
        execution_time = time.time() - start_time
        final_status = "success" if not state.errors else "failed"
        
        if metrics:
            exec_counter.add(1, {
                "status": final_status,
                "pipeline_id": str(self.pipeline.id),
                "trigger_mode": self.pipeline.trigger_mode.value if hasattr(self.pipeline, 'trigger_mode') else "unknown"
            })
            exec_duration.record(execution_time, {
                "status": final_status,
                "pipeline_id": str(self.pipeline.id)
            })
        
        # Update final execution record
        execution.status = ExecutionStatus.COMPLETED if not state.errors else ExecutionStatus.FAILED
        execution.completed_at = datetime.utcnow()
        
        # Serialize result models
        def serialize_model(model):
            if model is None:
                return None
            data = model.dict()
            for key, value in data.items():
                if isinstance(value, datetime):
                    data[key] = value.isoformat()
            return data
        
        execution.result = {
            "trigger_met": state.trigger_met,
            "trigger_reason": state.trigger_reason,
            "strategy": serialize_model(state.strategy),
            "risk_assessment": serialize_model(state.risk_assessment),
            "trade_execution": serialize_model(state.trade_execution),
            "errors": state.errors,
            "warnings": state.warnings,
            "agent_reports": self._serialize_reports(state.agent_reports),
        }
        execution.agent_states = agent_states
        execution.logs = self._serialize_logs(state.execution_log)
        execution.reports = self._serialize_reports(state.agent_reports)
        execution.cost = state.total_cost
        execution.cost_breakdown = state.agent_costs
        
        # Mark JSONB columns as modified
        flag_modified(execution, "agent_states")
        flag_modified(execution, "logs")
        flag_modified(execution, "reports")
        flag_modified(execution, "cost_breakdown")
        
        db_session.commit()
        
        self.logger.info(
            "pipeline_execution_completed",
            total_cost=state.total_cost,
            errors=len(state.errors),
            warnings=len(state.warnings),
            trigger_met=state.trigger_met
        )
        
        return execution
    
    async def execute_with_realtime_updates(self, db_session, execution):
        """
        Execute pipeline with real-time database updates for agent progress.
        
        Args:
            db_session: SQLAlchemy async session
            execution: Execution database record
            
        Returns:
            Updated PipelineState
        """
        # Initialize state
        state = PipelineState(
            pipeline_id=self.pipeline.id,
            execution_id=self.execution_id,
            user_id=self.user_id,
            symbol=self.config.get("symbol", "UNKNOWN"),
            mode=self.mode
        )
        
        # Get execution order
        execution_order = self._build_execution_order()
        
        # Initialize agent states tracking
        agent_states = []
        for node in execution_order:
            agent_states.append({
                "agent_id": node["id"],
                "agent_type": node["agent_type"],
                "status": "pending",
                "started_at": None,
                "completed_at": None,
                "error": None,
                "cost": 0.0
            })
        
        # Update execution with initial agent states
        execution.agent_states = agent_states
        await db_session.commit()
        
        # Execute each agent in sequence
        for i, node in enumerate(execution_order):
            agent_type = node["agent_type"]
            agent_id = node["id"]
            agent_config = node.get("config", {})
            
            # Update agent state to running
            agent_states[i]["status"] = "running"
            agent_states[i]["started_at"] = datetime.utcnow().isoformat()
            
            # Update DB with current progress
            execution.agent_states = agent_states
            execution.logs = self._serialize_logs(state.execution_log)
            await db_session.commit()
            
            self.logger.info(
                "executing_agent",
                step=f"{i+1}/{len(execution_order)}",
                agent_type=agent_type,
                agent_id=agent_id
            )
            
            try:
                # Create agent instance
                agent = self.registry.create_agent(
                    agent_type=agent_type,
                    agent_id=agent_id,
                    config=agent_config
                )
                
                # Execute agent
                state = agent.process(state)
                
                # Update agent state to completed
                agent_states[i]["status"] = "completed"
                agent_states[i]["completed_at"] = datetime.utcnow().isoformat()
                agent_states[i]["cost"] = state.agent_costs.get(agent_id, 0.0)
                
                # Update DB with progress
                execution.agent_states = agent_states
                execution.logs = self._serialize_logs(state.execution_log)
                execution.reports = self._serialize_reports(state.agent_reports)
                execution.cost = state.total_cost
                execution.cost_breakdown = state.agent_costs
                await db_session.commit()
                
                self.logger.info(
                    "agent_completed",
                    agent_type=agent_type,
                    cost=state.agent_costs.get(agent_id, 0.0)
                )
                
            except TriggerNotMetException as e:
                # Trigger not met - not an error, just skip execution
                self.logger.info("trigger_not_met", reason=str(e))
                state.trigger_met = False
                state.trigger_reason = str(e)
                agent_states[i]["status"] = "skipped"
                agent_states[i]["completed_at"] = datetime.utcnow().isoformat()
                agent_states[i]["error"] = "Trigger not met"
                execution.agent_states = agent_states
                await db_session.commit()
                break
                
            except AgentError as e:
                # Agent-specific error
                self.logger.error("agent_error", agent_type=agent_type, error=str(e))
                state.errors.append(f"Agent {agent_type} failed: {str(e)}")
                agent_states[i]["status"] = "failed"
                agent_states[i]["completed_at"] = datetime.utcnow().isoformat()
                agent_states[i]["error"] = str(e)
                execution.agent_states = agent_states
                await db_session.commit()
                
                # Decide whether to continue or abort
                if self._should_abort_on_error(agent_type, str(e)):
                    raise
                else:
                    # Continue to next agent
                    continue
                    
            except Exception as e:
                # Unexpected error
                self.logger.exception("unexpected_error", agent_type=agent_type)
                state.errors.append(f"Unexpected error in {agent_type}: {str(e)}")
                agent_states[i]["status"] = "failed"
                agent_states[i]["completed_at"] = datetime.utcnow().isoformat()
                agent_states[i]["error"] = str(e)
                execution.agent_states = agent_states
                await db_session.commit()
                raise
        
        # Mark completion
        state.completed_at = datetime.utcnow()
        
        # Store agent states in pipeline state for database persistence
        state.agent_execution_states = agent_states
        
        self.logger.info(
            "pipeline_execution_completed",
            total_cost=state.total_cost,
            errors=len(state.errors),
            warnings=len(state.warnings),
            trigger_met=state.trigger_met
        )
        
        return state
    
    def _serialize_logs(self, logs):
        """Convert execution logs to JSON-serializable format."""
        serialized = []
        for log_entry in logs:
            serialized_entry = {}
            for key, value in log_entry.items():
                serialized_entry[key] = self._serialize_value(value)
            serialized.append(serialized_entry)
        return serialized
    
    def _serialize_reports(self, reports):
        """Convert agent reports to JSON-safe dict."""
        if not reports:
            return {}
        serialized = {}
        for agent_id, report in reports.items():
            serialized[agent_id] = self._serialize_value(report.dict())
        return serialized
    
    def _serialize_value(self, value):
        """Recursively convert datetimes and nested structures."""
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, list):
            return [self._serialize_value(v) for v in value]
        if isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        return value
    
    async def execute_with_db_tracking(self, db_session) -> Execution:
        """
        Execute pipeline and track in database.
        
        This is the main entry point for executing pipelines with full tracking.
        
        Args:
            db_session: SQLAlchemy async session
            
        Returns:
            Execution database record with results
        """
        # Get or create execution record
        from sqlalchemy import select
        result = await db_session.execute(
            select(Execution).where(Execution.id == self.execution_id)
        )
        execution = result.scalar_one_or_none()
        
        if not execution:
            # Create new execution if it doesn't exist
            execution = Execution(
                id=self.execution_id,
                pipeline_id=self.pipeline.id,
                user_id=self.user_id,
                status=ExecutionStatus.RUNNING,
                started_at=datetime.utcnow()
            )
            db_session.add(execution)
        else:
            # Update existing execution
            execution.status = ExecutionStatus.RUNNING
            if not execution.started_at:
                execution.started_at = datetime.utcnow()
        
        await db_session.commit()
        
        try:
            # Execute pipeline and update DB in real-time
            state = await self.execute_with_realtime_updates(db_session, execution)
            
            # Update execution record with final results
            execution.status = ExecutionStatus.COMPLETED if not state.errors else ExecutionStatus.FAILED
            execution.completed_at = datetime.utcnow()
            
            # Convert Pydantic models to JSON-serializable dicts
            def serialize_model(model):
                """Convert Pydantic model to JSON-serializable dict."""
                if model is None:
                    return None
                data = model.dict()
                # Convert datetime objects to ISO format strings
                for key, value in data.items():
                    if isinstance(value, datetime):
                        data[key] = value.isoformat()
                return data
            
            def serialize_logs(logs):
                """Convert execution logs to JSON-serializable format."""
                serialized = []
                for log_entry in logs:
                    serialized_entry = {}
                    for key, value in log_entry.items():
                        if isinstance(value, datetime):
                            serialized_entry[key] = value.isoformat()
                        else:
                            serialized_entry[key] = value
                    serialized.append(serialized_entry)
                return serialized
            
            execution.result = {
                "trigger_met": state.trigger_met,
                "trigger_reason": state.trigger_reason,
                "strategy": serialize_model(state.strategy),
                "risk_assessment": serialize_model(state.risk_assessment),
                "trade_execution": serialize_model(state.trade_execution),
                "errors": state.errors,
                "warnings": state.warnings,
                "agent_reports": self._serialize_reports(state.agent_reports),
            }
            execution.cost = state.total_cost
            execution.logs = serialize_logs(state.execution_log)
            execution.agent_states = getattr(state, 'agent_execution_states', [])
            execution.reports = self._serialize_reports(state.agent_reports)
            execution.cost_breakdown = state.agent_costs
            
            await db_session.commit()
            
            self.logger.info("execution_saved_to_db", execution_id=str(execution.id))
            
            return execution
            
        except TriggerNotMetException:
            # Trigger not met - mark as skipped
            execution.status = ExecutionStatus.SKIPPED
            execution.completed_at = datetime.utcnow()
            execution.result = {"trigger_met": False, "reason": "Trigger conditions not met"}
            execution.logs = serialize_logs(getattr(locals().get("state", None), "execution_log", []))
            execution.agent_states = getattr(locals().get("state", None), "agent_execution_states", [])
            execution.reports = self._serialize_reports(getattr(locals().get("state", None), "agent_reports", {}))
            await db_session.commit()
            return execution
            
        except Exception as e:
            # Execution failed
            execution.status = ExecutionStatus.FAILED
            execution.completed_at = datetime.utcnow()
            execution.result = {"error": str(e)}
            await db_session.commit()
            raise


class ExecutionManager:
    """
    Manages pipeline executions across the system.
    
    Provides high-level operations like:
    - Starting executions
    - Stopping running executions
    - Querying execution status
    - Scheduling recurring executions
    """
    
    @staticmethod
    async def start_execution(
        pipeline_id: UUID,
        user_id: UUID,
        mode: str,
        db_session
    ) -> Execution:
        """
        Start a new pipeline execution.
        
        Args:
            pipeline_id: Pipeline to execute
            user_id: User requesting execution
            mode: Execution mode
            db_session: Database session
            
        Returns:
            Execution record
        """
        from app.models.pipeline import Pipeline
        
        # Load pipeline
        pipeline = await db_session.get(Pipeline, pipeline_id)
        if not pipeline:
            raise ValueError(f"Pipeline {pipeline_id} not found")
        
        if pipeline.user_id != user_id:
            raise PermissionError("Pipeline does not belong to user")
        
        # Create executor and run
        executor = PipelineExecutor(pipeline, user_id, mode)
        execution = await executor.execute_with_db_tracking(db_session)
        
        return execution
    
    @staticmethod
    async def get_execution_status(
        execution_id: UUID,
        user_id: UUID,
        db_session
    ) -> Optional[Execution]:
        """
        Get status of an execution.
        
        Args:
            execution_id: Execution ID
            user_id: User ID (for permission check)
            db_session: Database session
            
        Returns:
            Execution record or None
        """
        from app.models.execution import Execution
        
        execution = await db_session.get(Execution, execution_id)
        if execution and execution.user_id == user_id:
            return execution
        return None

