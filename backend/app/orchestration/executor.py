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
from typing import Dict, Any, List, Optional
from uuid import UUID, uuid4
from datetime import datetime

from app.schemas.pipeline_state import PipelineState
from app.models.pipeline import Pipeline
from app.models.execution import Execution, ExecutionStatus
from app.agents import get_registry
from app.agents.base import AgentError, TriggerNotMetException

logger = structlog.get_logger()


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
        
        # Execute each agent in sequence
        for i, node in enumerate(execution_order):
            agent_type = node["agent_type"]
            agent_id = node["id"]
            agent_config = node.get("config", {})
            
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
                break
                
            except AgentError as e:
                # Agent-specific error
                self.logger.error("agent_error", agent_type=agent_type, error=str(e))
                state.errors.append(f"Agent {agent_type} failed: {str(e)}")
                
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
                raise
        
        # Mark completion
        state.completed_at = datetime.utcnow()
        
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
            # Execute pipeline
            state = await self.execute()
            
            # Update execution record with results
            execution.status = ExecutionStatus.COMPLETED if not state.errors else ExecutionStatus.FAILED
            execution.completed_at = datetime.utcnow()
            execution.result = {
                "trigger_met": state.trigger_met,
                "trigger_reason": state.trigger_reason,
                "strategy": state.strategy.dict() if state.strategy else None,
                "risk_assessment": state.risk_assessment.dict() if state.risk_assessment else None,
                "trade_execution": state.trade_execution.dict() if state.trade_execution else None,
                "errors": state.errors,
                "warnings": state.warnings
            }
            execution.cost = state.total_cost
            execution.logs = state.execution_log
            
            await db_session.commit()
            
            self.logger.info("execution_saved_to_db", execution_id=str(execution.id))
            
            return execution
            
        except TriggerNotMetException:
            # Trigger not met - mark as skipped
            execution.status = ExecutionStatus.SKIPPED
            execution.completed_at = datetime.utcnow()
            execution.result = {"trigger_met": False, "reason": "Trigger conditions not met"}
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

