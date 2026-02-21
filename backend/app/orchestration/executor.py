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
from datetime import datetime, timedelta

from app.schemas.pipeline_state import PipelineState
from app.models.pipeline import Pipeline
from app.models.execution import Execution, ExecutionStatus
from app.models.scanner import Scanner
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
        execution_id: Optional[UUID] = None,
        signal_context: Optional[Dict[str, Any]] = None,
        symbol_override: Optional[str] = None,
        db_session: Optional[Any] = None
    ):
        """
        Initialize the pipeline executor.
        
        Args:
            pipeline: Pipeline database model with config
            user_id: ID of user executing the pipeline
            mode: Execution mode ("live", "paper", "simulation", "validation")
            execution_id: Optional pre-created execution ID
            signal_context: Optional signal data that triggered this execution
            symbol_override: Optional symbol override (for scanner-based pipelines)
            db_session: Optional database session for loading scanner
        """
        self.pipeline = pipeline
        self.user_id = user_id
        self.mode = mode
        self.execution_id = execution_id or uuid4()
        self.signal_context = signal_context
        self.symbol_override = symbol_override
        self.db_session = db_session
        
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
        
        # Load scanner tickers if pipeline uses a scanner
        self.scanner_tickers = []
        self.logger.info("scanner_check", has_scanner_id=bool(pipeline.scanner_id), has_db_session=bool(db_session), scanner_id=str(pipeline.scanner_id) if pipeline.scanner_id else None)
        
        if pipeline.scanner_id and db_session:
            try:
                scanner = db_session.query(Scanner).filter(Scanner.id == pipeline.scanner_id).first()
                if scanner:
                    self.scanner_tickers = scanner.get_tickers()
                    self.logger.info("scanner_loaded", scanner_id=str(scanner.id), ticker_count=len(self.scanner_tickers), tickers=self.scanner_tickers[:3])
                else:
                    self.logger.warning("scanner_not_found", scanner_id=str(pipeline.scanner_id))
            except Exception as e:
                self.logger.error("scanner_load_error", error=str(e), exc_info=True)
        else:
            self.logger.info("scanner_loading_skipped", reason="no_scanner_id" if not pipeline.scanner_id else "no_db_session")
        
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
        Build the execution order using the fixed agent sequence.
        
        The platform now uses a FIXED execution order (not graph-based):
        Market Data → Bias → Strategy → Risk Manager → Trade Manager
        
        This method filters the pipeline nodes to match this sequence,
        ignoring tool nodes and ensuring consistent, predictable execution.
        
        Returns:
            List of nodes in execution order (fixed sequence)
        """
        # Fixed agent execution sequence (canonical order)
        FIXED_AGENT_ORDER = [
            "market_data_agent",
            "bias_agent",
            "strategy_agent",
            "risk_manager_agent",
            "trade_manager_agent"
        ]
        
        # Build a map of agent_type -> node for quick lookup
        node_map = {}
        for node in self.nodes:
            agent_type = node.get("agent_type") or node.get("type")
            # Skip tool nodes (they are attached configs, not execution steps)
            if agent_type and node.get("node_category") != "tool":
                node_map[agent_type] = node
        
        # Build execution order by filtering nodes to match fixed sequence
        execution_order = []
        for agent_type in FIXED_AGENT_ORDER:
            if agent_type in node_map:
                execution_order.append(node_map[agent_type])
        
        if not execution_order:
            self.logger.error("no_agents_found_in_pipeline")
            raise ValueError("Pipeline has no valid agents to execute")
        
        self.logger.info(
            "execution_order_built_fixed_sequence",
            agent_count=len(execution_order),
            agents=[n.get("agent_type") for n in execution_order]
        )
        return execution_order
    
    async def _fetch_market_data_for_pipeline(self, state: PipelineState):
        """
        Fetch market data for the pipeline and populate state.market_data.
        
        In paper/test mode, generates mock data.
        In live mode, fetches from data plane.
        
        Args:
            state: Pipeline state to populate with market data
        """
        # Determine which timeframes are needed by agents
        required_timeframes = self._get_required_timeframes()

        # If we can't infer timeframes (e.g., missing instructions), don't leave state.market_data empty.
        # This previously caused downstream agents to crash on None market_data.
        if not required_timeframes:
            self.logger.warning("no_timeframes_required_defaulting", mode=self.mode)
            if self.mode in ["paper", "simulation", "validation"]:
                required_timeframes = ["5m", "1h", "1d"]
            else:
                # Live mode fallback: at minimum fetch daily to give agents something to work with
                required_timeframes = ["1d"]
        
        # Store timeframes in state for agent access
        state.timeframes = required_timeframes
        
        self.logger.info(
            "fetching_market_data",
            symbol=state.symbol,
            timeframes=required_timeframes,
            mode=self.mode
        )
        
        # 🚫 RULE: NEVER USE MOCK DATA - Always fetch real data from Data Plane
        try:
            state.market_data = await self._fetch_from_data_plane(state.symbol, required_timeframes)
            self.logger.info("market_data_fetched_from_data_plane", mode=self.mode)
        except Exception as e:
            self.logger.error("data_plane_fetch_failed", error=str(e), exc_info=True)
            raise RuntimeError(f"Failed to fetch market data from Data Plane: {str(e)}.")
    
    def _get_required_timeframes(self) -> List[str]:
        """
        Determine which timeframes are required by agents in the pipeline.
        
        Collects timeframes from ALL sources:
        1. Agent instructions (natural language parsing)
        2. Agent metadata (requires_timeframes)
        3. Explicit config fields
        
        Returns:
            List of unique timeframe strings sorted by duration
        """
        from app.services.instruction_parser import instruction_parser
        
        timeframes = set()
        
        for node in self.nodes:
            agent_type = node.get("agent_type")
            
            # Skip tools
            if node.get("node_category") == "tool":
                continue
            
            try:
                config = node.get("config", {})
                
                # 1. Parse timeframes from instructions (instruction-driven!)
                instructions = config.get("instructions", "")
                if instructions:
                    extracted_tfs = instruction_parser.extract_timeframes(instructions)
                    if extracted_tfs:
                        timeframes.update(extracted_tfs)
                        self.logger.debug(
                            "timeframes_extracted_from_instructions",
                            agent_type=agent_type,
                            extracted=extracted_tfs
                        )
                
                # 2. Check agent metadata (ALWAYS, not just as fallback)
                metadata = self.registry.get_metadata(agent_type)
                if metadata and metadata.requires_timeframes:
                    timeframes.update(metadata.requires_timeframes)
                    self.logger.debug(
                        "timeframes_from_metadata",
                        agent_type=agent_type,
                        timeframes=metadata.requires_timeframes
                    )
                    
            except Exception as e:
                self.logger.warning(
                    "failed_to_get_timeframes_for_agent",
                    agent_type=agent_type,
                    error=str(e)
                )
        
        sorted_timeframes = sorted(list(timeframes))
        self.logger.info("pipeline_timeframes_determined", timeframes=sorted_timeframes)
        
        return sorted_timeframes
    
    async def _fetch_from_data_plane(self, symbol: str, timeframes: List[str]):
        """
        Fetch market data from data plane service.
        
        Args:
            symbol: Trading symbol
            timeframes: List of timeframes to fetch
            
        Returns:
            MarketData object
        """
        import httpx
        from app.config import settings
        from app.schemas.pipeline_state import MarketData, TimeframeData
        
        data_plane_url = getattr(settings, "DATA_PLANE_URL", "http://data-plane:8000")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Fetch candles for each timeframe
            timeframe_data = {}
            current_price = 0
            bid = None
            ask = None
            
            for tf in timeframes:
                candle_response = await client.get(
                    f"{data_plane_url}/api/v1/data/candles/{symbol}",
                    params={"timeframe": tf, "limit": 100}
                )
                candle_response.raise_for_status()
                candle_data = candle_response.json()
                
                # Convert to TimeframeData objects
                candles = [
                    TimeframeData(**candle) for candle in candle_data.get("candles", [])
                ]
                timeframe_data[tf] = candles
                
                # Use the latest candle from the first timeframe for current price
                if candles and current_price == 0:
                    latest_candle = candles[-1]
                    current_price = latest_candle.close
                    # For forex, bid/ask can be approximated from close (or use close for both)
                    bid = latest_candle.close
                    ask = latest_candle.close
            
            # Calculate spread from bid/ask
            spread = None
            if bid and ask:
                spread = ask - bid
            
            market_data = MarketData(
                symbol=symbol,
                current_price=current_price,
                bid=bid,
                ask=ask,
                spread=spread,
                timeframes=timeframe_data,
                market_status="open",  # Assume open if we got data
                last_updated=datetime.utcnow()
            )
            
            return market_data
    
    def _fetch_market_data_sync(self, state: PipelineState):
        """
        Synchronous version of _fetch_market_data_for_pipeline for use in Celery tasks.
        
        Args:
            state: Pipeline state to populate with market data
        """
        # Determine which timeframes are needed by agents
        required_timeframes = self._get_required_timeframes()

        # Mirror async behavior: never leave market_data empty in any mode.
        if not required_timeframes:
            self.logger.warning("no_timeframes_required_defaulting", mode=self.mode)
            required_timeframes = ["5m", "1h", "1d"]
        
        # Store timeframes in state for agent access
        state.timeframes = required_timeframes
        
        self.logger.info(
            "fetching_market_data_sync",
            symbol=state.symbol,
            timeframes=required_timeframes,
            mode=self.mode
        )
        
        # ⚠️ FIX #4: Add retry logic with exponential backoff for Data Plane failures
        import requests
        from app.config import settings
        from app.schemas.pipeline_state import MarketData, TimeframeData
        import time
        
        data_plane_url = getattr(settings, "DATA_PLANE_URL", "http://data-plane:8000")
        
        max_retries = 3
        base_delay = 1  # seconds
        
        for attempt in range(max_retries):
            try:
                # Fetch candles for each timeframe
                timeframe_data = {}
                current_price = 0
                bid = None
                ask = None
                
                for tf in required_timeframes:
                    candle_response = requests.get(
                        f"{data_plane_url}/api/v1/data/candles/{state.symbol}",
                        params={"timeframe": tf, "limit": 100},
                        timeout=10.0
                    )
                    candle_response.raise_for_status()
                    candle_data = candle_response.json()
                    
                    # Convert to TimeframeData objects
                    candles = []
                    for candle in candle_data.get("candles", []):
                        candles.append(TimeframeData(
                            timeframe=tf,
                            timestamp=candle.get("time") or candle.get("timestamp"),
                            open=candle["open"],
                            high=candle["high"],
                            low=candle["low"],
                            close=candle["close"],
                            volume=candle.get("volume", 0)
                        ))
                    timeframe_data[tf] = candles
                    
                    # Use the latest candle from the first timeframe for current price
                    if candles and current_price == 0:
                        latest_candle = candles[-1]
                        current_price = latest_candle.close
                        bid = latest_candle.close
                        ask = latest_candle.close
                
                spread = None
                if bid and ask:
                    spread = ask - bid
                
                state.market_data = MarketData(
                    symbol=state.symbol,
                    current_price=current_price,
                    bid=bid,
                    ask=ask,
                    spread=spread,
                    timeframes=timeframe_data,
                    market_status="open",  # Assume open if we got data
                    last_updated=datetime.utcnow()
                )
                
                self.logger.info("market_data_fetched_from_data_plane_sync", mode=self.mode, attempt=attempt + 1)
                return  # Success!
                
            except requests.exceptions.RequestException as e:
                is_last_attempt = (attempt == max_retries - 1)
                
                if is_last_attempt:
                    # All retries exhausted
                    self.logger.error(
                        "data_plane_fetch_sync_failed_all_retries",
                        error=str(e),
                        attempts=max_retries,
                        exc_info=True
                    )
                    raise RuntimeError(
                        f"Failed to fetch market data from Data Plane after {max_retries} attempts: {str(e)}. "
                        f"Please check Data Plane service health."
                    )
                else:
                    # Retry with exponential backoff
                    delay = base_delay * (2 ** attempt)  # 1s, 2s, 4s
                    self.logger.warning(
                        "data_plane_fetch_retry",
                        error=str(e),
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        retry_delay_seconds=delay
                    )
                    time.sleep(delay)
                    continue  # Retry
            
            except Exception as e:
                # Unexpected error (e.g., data parsing)
                self.logger.error("data_plane_fetch_sync_failed", error=str(e), exc_info=True)
                raise RuntimeError(f"Failed to fetch market data from Data Plane: {str(e)}")
    
    async def execute(self) -> PipelineState:
        """
        Execute the complete pipeline (async version for testing).
        
        This is a simplified execution path that runs agents without database tracking.
        It's primarily used for unit tests where speed and simplicity are more important
        than real-time progress updates.
        
        For PRODUCTION use (Celery tasks), use execute_with_sync_db_tracking() instead,
        which provides:
        - Real-time database commits after each agent (for live UI updates)
        - Monitoring task scheduling for open positions
        - PDF report generation
        - Prometheus metrics recording
        - Optimistic locking for concurrent execution safety
        
        Returns:
            Final pipeline state after all agents have run (in-memory object)
            
        Raises:
            AgentError: If an agent fails critically
            TriggerNotMetException: If trigger conditions not met
        """
        self.logger.info("pipeline_execution_started")
        
        # Initialize pipeline state
        # Create pipeline state with signal context if available
        from app.schemas.pipeline_state import SignalData
        
        signal_data = None
        if self.signal_context:
            signal_data = SignalData(**self.signal_context)
        
        # DEBUG: Log scanner tickers state at beginning of execute
        self.logger.debug("execute_symbol_debug", 
                        has_symbol_override=bool(self.symbol_override),
                        symbol_override=self.symbol_override,
                        scanner_tickers_len=len(self.scanner_tickers) if self.scanner_tickers else 0)
        
        # Determine the symbol to use for this execution
        # ALL executions are signal-based (including periodic via signal generator)
        # Symbol always comes from symbol_override (passed by trigger-dispatcher)
        execution_symbol = self.symbol_override
        
        if not execution_symbol:
            # Fallback: Use first scanner ticker if symbol_override not provided
            # This should rarely happen - mainly for manual testing
            if self.scanner_tickers:
                execution_symbol = self.scanner_tickers[0]
                self.logger.warning("using_scanner_fallback", symbol=execution_symbol, total_tickers=len(self.scanner_tickers))
            else:
                # No symbol available - this is an error state
                raise ValueError("No symbol available: pipeline must have scanner_id and execution must provide symbol_override")
        
        self.logger.info("execution_symbol_determined", symbol=execution_symbol)
        
        state = PipelineState(
            pipeline_id=self.pipeline.id,
            execution_id=self.execution_id,
            user_id=self.user_id,
            symbol=execution_symbol,
            mode=self.mode,
            signal_data=signal_data
        )
        
        # Fetch market data before running agents
        await self._fetch_market_data_for_pipeline(state)
        
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
            "risk_manager_agent"  # Risk manager must succeed to prevent bad trades
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
        
        This is the PRODUCTION execution path used by Celery tasks. It differs from the
        async execute() method in several key ways:
        
        1. **Synchronous**: Uses sync DB operations (Celery tasks are sync by default)
        2. **Real-time DB updates**: Commits agent progress after each step for live UI updates
        3. **Monitoring**: Schedules monitoring tasks for open positions
        4. **PDF Reports**: Generates PDF reports on completion
        5. **Metrics**: Records Prometheus metrics (duration, success/failure)
        6. **Optimistic locking**: Increments execution.version to prevent race conditions
        
        The async execute() method is used only for testing (fast, in-memory, no DB overhead).
        
        Args:
            db_session: Synchronous SQLAlchemy session
            execution: Execution database record (pre-created, will be updated in real-time)
            
        Returns:
            Updated Execution record
        """
        # Import flag_modified for JSONB column tracking
        from sqlalchemy.orm.attributes import flag_modified
        
        # Track execution metrics
        start_time = time.time()
        
        # Use prometheus_client histogram and counter for metrics tracking
        from app.telemetry import pipeline_duration_histogram, pipeline_executions_counter
        
        # Initialize state
        # Create pipeline state with signal context if available
        from app.schemas.pipeline_state import SignalData
        
        signal_data = None
        if self.signal_context:
            signal_data = SignalData(**self.signal_context)
        
        # Determine the symbol to use for this execution
        # ALL executions are signal-based (including periodic via signal generator)
        # Symbol always comes from symbol_override (passed by trigger-dispatcher)
        execution_symbol = self.symbol_override
        
        if not execution_symbol:
            # Fallback: Use first scanner ticker if symbol_override not provided
            # This should rarely happen - mainly for manual testing
            if self.scanner_tickers:
                execution_symbol = self.scanner_tickers[0]
                self.logger.warning("sync_using_scanner_fallback", symbol=execution_symbol, total_tickers=len(self.scanner_tickers))
            else:
                # No symbol available - this is an error state
                raise ValueError("No symbol available: pipeline must have scanner_id and execution must provide symbol_override")
        
        self.logger.info("sync_execution_symbol_determined", symbol=execution_symbol)
        
        state = PipelineState(
            pipeline_id=self.pipeline.id,
            execution_id=self.execution_id,
            user_id=self.user_id,
            symbol=execution_symbol,
            mode=self.mode,
            signal_data=signal_data
        )
        
        # Fetch market data before running agents (synchronous version)
        self._fetch_market_data_sync(state)
        
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
            
            # ── Approval gate: pause before Trade Manager if approval is required ──
            if agent_type == "trade_manager_agent":
                from app.services.approval_service import ApprovalService
                if ApprovalService.should_require_approval(self.pipeline, self.mode):
                    # Only pause if risk approved and action is not HOLD
                    should_pause = (
                        state.risk_assessment
                        and getattr(state.risk_assessment, "approved", False)
                        and state.strategy
                        and getattr(state.strategy, "action", "HOLD") != "HOLD"
                    )
                    if should_pause:
                        agent_states[i]["status"] = "awaiting_approval"
                        execution.agent_states = agent_states
                        flag_modified(execution, "agent_states")

                        # Persist current results so approval UI can show them
                        result = {}
                        if state.strategy:
                            result["strategy"] = state.strategy.dict() if hasattr(state.strategy, "dict") else state.strategy
                        if state.risk_assessment:
                            result["risk_assessment"] = state.risk_assessment.dict() if hasattr(state.risk_assessment, "dict") else state.risk_assessment
                        if state.market_bias:
                            result["market_bias"] = state.market_bias.dict() if hasattr(state.market_bias, "dict") else state.market_bias
                        execution.result = result
                        flag_modified(execution, "result")
                        execution.reports = self._serialize_reports(state.agent_reports)
                        flag_modified(execution, "reports")

                        ApprovalService.initiate_approval(execution, self.pipeline, state, db_session)
                        self.logger.info(
                            "approval_gate_activated",
                            execution_id=str(execution.id),
                            pipeline_id=str(self.pipeline.id),
                        )
                        return execution  # Exit executor — Celery task ends here

            # Update agent state to running
            agent_states[i]["status"] = "running"
            agent_states[i]["started_at"] = datetime.utcnow().isoformat()

            # Update DB with current progress
            execution.agent_states = agent_states
            execution.logs = self._serialize_logs(state.execution_log)
            # JSONB mutation: mark modified so "running" status is persisted even if agent hangs
            flag_modified(execution, "agent_states")
            flag_modified(execution, "logs")
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
                
                # ⚠️ FIX #1: Increment version for optimistic locking
                execution.version += 1
                
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
        final_status = "completed" if not state.errors else "failed"
        
        # Record execution metrics in Prometheus
        pipeline_executions_counter.labels(
            status=final_status,
            pipeline_id=str(self.pipeline.id)
        ).inc()
        
        pipeline_duration_histogram.labels(
            status=final_status,
            pipeline_id=str(self.pipeline.id)
        ).observe(execution_time)
        
        # Update final execution record
        # Check if entering monitoring mode (Trade Manager)
        if state.execution_phase == "monitoring":
            execution.status = ExecutionStatus.MONITORING
            execution.execution_phase = "monitoring"
            execution.monitor_interval_minutes = state.monitor_interval_minutes
            execution.next_check_at = datetime.utcnow() + timedelta(minutes=state.monitor_interval_minutes)
            execution.completed_at = None  # Not completed yet, still monitoring
        else:
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
        
        def serialize_artifacts(artifacts):
            """Recursively serialize artifacts, converting datetime objects to ISO strings."""
            if isinstance(artifacts, dict):
                return {k: serialize_artifacts(v) for k, v in artifacts.items()}
            elif isinstance(artifacts, list):
                return [serialize_artifacts(item) for item in artifacts]
            elif isinstance(artifacts, datetime):
                return artifacts.isoformat()
            else:
                return artifacts
        
        execution.result = {
            "trigger_met": state.trigger_met,
            "trigger_reason": state.trigger_reason,
            "strategy": serialize_model(state.strategy),
            "risk_assessment": serialize_model(state.risk_assessment),
            "trade_execution": serialize_model(state.trade_execution),
            "errors": state.errors,
            "warnings": state.warnings,
            "agent_reports": self._serialize_reports(state.agent_reports),
            "execution_artifacts": serialize_artifacts(state.execution_artifacts),
        }
        execution.agent_states = agent_states
        execution.logs = self._serialize_logs(state.execution_log)
        execution.reports = self._serialize_reports(state.agent_reports)
        execution.cost = state.total_cost
        execution.cost_breakdown = state.agent_costs
        
        # Mark JSONB columns as modified
        flag_modified(execution, "result")  # CRITICAL: Mark result column (contains execution_artifacts/chart)
        flag_modified(execution, "agent_states")
        flag_modified(execution, "logs")
        flag_modified(execution, "reports")
        flag_modified(execution, "cost_breakdown")
        
        # ⚠️ FIX #1: Increment version for optimistic locking
        execution.version += 1
        
        db_session.commit()
        
        self.logger.info(
            "pipeline_execution_completed",
            total_cost=state.total_cost,
            errors=len(state.errors),
            warnings=len(state.warnings),
            trigger_met=state.trigger_met
        )
        
        # Generate PDF report if execution completed successfully
        if execution.status == ExecutionStatus.COMPLETED:
            self._generate_pdf_report_sync(execution, db_session)
        
        # Persist full PipelineState snapshot so monitoring/reconciliation
        # can round-trip state without lossy reconstruction from execution.result.
        if execution.status == ExecutionStatus.MONITORING:
            from app.orchestration.tasks._helpers import save_pipeline_state
            save_pipeline_state(execution, state, db=db_session)
            db_session.commit()

        # Schedule monitoring task if entering monitoring mode
        if execution.status == ExecutionStatus.MONITORING:
            from app.orchestration.tasks import schedule_monitoring_check
            # Schedule first check immediately (countdown=0) so UI shows P&L right away
            # Subsequent checks will use the configured interval
            schedule_monitoring_check.apply_async(
                args=[str(execution.id)],
                countdown=0  # First check happens immediately
            )
            self.logger.info(
                "monitoring_scheduled",
                execution_id=str(execution.id),
                first_check="immediate",
                interval_minutes=execution.monitor_interval_minutes,
                next_check_at=execution.next_check_at.isoformat() if execution.next_check_at else "immediate"
            )
        
        return execution
    
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
    
    def _generate_pdf_report_sync(self, execution: Any, db_session: Any):
        """
        Generate PDF report for completed execution (synchronous version).
        
        Runs in background to avoid blocking execution completion.
        """
        try:
            from app.services.pdf_generator import pdf_generator
            from app.services.executive_report_generator import executive_report_generator
            from sqlalchemy.orm.attributes import flag_modified
            
            self.logger.info("generating_pdf_report", execution_id=str(execution.id))
            
            # Prepare execution data
            execution_data = {
                "id": str(execution.id),
                "pipeline_name": self.pipeline.name if hasattr(self.pipeline, 'name') else "Unknown",
                "symbol": execution.symbol,
                "mode": execution.mode,
                "status": execution.status.value,
                "started_at": execution.started_at.isoformat() if execution.started_at else None,
                "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
                "duration_seconds": (execution.completed_at - execution.started_at).total_seconds() if execution.started_at and execution.completed_at else None,
                "cost": execution.cost,
                "trigger_source": getattr(self, 'trigger_source', 'N/A'),
                "reports": execution.reports or {},
                "result": execution.result or {},
            }
            
            # Try to generate AI summary (optional - don't fail if it errors)
            # NOTE: executive_report_generator methods are synchronous
            executive_summary = None
            try:
                executive_summary = executive_report_generator.generate_executive_summary_sync(
                    execution_data,
                    langfuse_trace=None
                )
            except Exception as e:
                self.logger.warning("executive_summary_generation_failed", error=str(e))
            
            # Generate PDF (synchronous)
            pdf_path = pdf_generator.generate_execution_report(
                execution_id=str(execution.id),
                execution_data=execution_data,
                executive_summary=executive_summary
            )
            
            # Update execution record with PDF path
            execution.report_pdf_path = pdf_path
            flag_modified(execution, "report_pdf_path")
            db_session.commit()
            
            self.logger.info("pdf_report_generated_successfully", 
                           execution_id=str(execution.id),
                           pdf_path=pdf_path)
            
        except Exception as e:
            # Log error but don't fail the execution
            self.logger.error("pdf_generation_failed", 
                            execution_id=str(execution.id),
                            error=str(e))
