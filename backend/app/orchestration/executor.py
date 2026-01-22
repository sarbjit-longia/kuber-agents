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
            raise RuntimeError(f"Failed to fetch market data from Data Plane: {str(e)}. Mock data is disabled.")
    
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
                
                # 3. Check explicit config fields (for backward compatibility)
                if "strategy_timeframe" in config:
                    timeframes.add(config["strategy_timeframe"])
                if "primary_timeframe" in config:
                    timeframes.add(config["primary_timeframe"])
                if "secondary_timeframes" in config:
                    timeframes.update(config["secondary_timeframes"])
                    
            except Exception as e:
                self.logger.warning(
                    "failed_to_get_timeframes_for_agent",
                    agent_type=agent_type,
                    error=str(e)
                )
        
        sorted_timeframes = sorted(list(timeframes))
        self.logger.info("pipeline_timeframes_determined", timeframes=sorted_timeframes)
        
        return sorted_timeframes
    
    def _generate_mock_market_data(self, symbol: str, timeframes: List[str]):
        """
        Generate mock market data for testing.
        
        Args:
            symbol: Trading symbol
            timeframes: List of timeframes to generate
            
        Returns:
            MarketData object with mock data
        """
        import random
        from app.schemas.pipeline_state import MarketData, TimeframeData
        
        # 🐛 FIX: Generate realistic mock price based on asset type
        # Forex pairs (e.g., EUR_USD, GBP/USD) should be around 1.0-2.0
        # Stocks should be around 50-500
        is_forex = "/" in symbol or "_" in symbol and len(symbol.split("_")) == 2 and all(len(part) == 3 for part in symbol.split("_"))
        
        if is_forex:
            base_price = random.uniform(0.5, 2.0)  # Forex range
            volatility = 0.002  # 0.2% volatility for forex
        else:
            base_price = random.uniform(50, 500)  # Stock range
            volatility = 0.02  # 2% volatility for stocks
        
        # Generate mock timeframe data
        timeframe_data = {}
        for tf in timeframes:
            candles = []
            price = base_price
            
            # Generate 100 candles with random walk
            for i in range(100):
                change = random.uniform(-volatility * 10, volatility * 10)  # Use asset-specific volatility
                price = price * (1 + change)
                
                high = price * (1 + volatility * 5)
                low = price * (1 - volatility * 5)
                open_price = price * (1 + random.uniform(-volatility * 2.5, volatility * 2.5))
                close_price = price
                
                # Use appropriate decimal precision: 5 for forex, 2 for stocks
                decimal_places = 5 if is_forex else 2
                
                candle = TimeframeData(
                    timeframe=tf,
                    timestamp=datetime.utcnow() - timedelta(minutes=(100-i) * 5),
                    open=round(open_price, decimal_places),
                    high=round(high, decimal_places),
                    low=round(low, decimal_places),
                    close=round(close_price, decimal_places),
                    volume=random.randint(100000, 10000000)
                )
                candles.append(candle)
            
            timeframe_data[tf] = candles
        
        market_data = MarketData(
            symbol=symbol,
            current_price=round(price, 5 if is_forex else 2),
            bid=round(price * 0.999, 5 if is_forex else 2),
            ask=round(price * 1.001, 5 if is_forex else 2),
            spread=round(price * 0.002, 5 if is_forex else 2),
            timeframes=timeframe_data,
            market_status="open" if self.mode == "live" else "mock",
            last_updated=datetime.utcnow()
        )
        
        self.logger.debug(
            "mock_market_data_generated",
            symbol=symbol,
            price=price,
            timeframes=len(timeframes)
        )
        
        return market_data
    
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
            # Fetch quote
            quote_response = await client.get(f"{data_plane_url}/api/v1/data/quote/{symbol}")
            quote_response.raise_for_status()
            quote_data = quote_response.json()
            
            # Fetch candles for each timeframe
            timeframe_data = {}
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
            
            market_data = MarketData(
                symbol=symbol,
                current_price=quote_data.get("c", 0),
                bid=quote_data.get("b"),
                ask=quote_data.get("a"),
                spread=quote_data.get("a", 0) - quote_data.get("b", 0) if quote_data.get("a") and quote_data.get("b") else None,
                timeframes=timeframe_data,
                market_status=quote_data.get("market_status", "unknown"),
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
        
        # 🚫 RULE: NEVER USE MOCK DATA - Always fetch real data from Data Plane
        # Use synchronous HTTP library (requests) for Celery tasks
        import requests
        from app.config import settings
        from app.schemas.pipeline_state import MarketData, TimeframeData
        
        data_plane_url = getattr(settings, "DATA_PLANE_URL", "http://data-plane:8000")
        
        try:
            # Fetch quote
            quote_response = requests.get(
                f"{data_plane_url}/api/v1/data/quote/{state.symbol}",
                timeout=10.0
            )
            quote_response.raise_for_status()
            quote_data = quote_response.json()
            
            # Fetch candles for each timeframe
            timeframe_data = {}
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
            
            state.market_data = MarketData(
                symbol=state.symbol,
                current_price=quote_data.get("c", 0),
                bid=quote_data.get("b"),
                ask=quote_data.get("a"),
                spread=quote_data.get("a", 0) - quote_data.get("b", 0) if quote_data.get("a") and quote_data.get("b") else None,
                timeframes=timeframe_data,
                market_status=quote_data.get("market_status", "unknown"),
                last_updated=datetime.utcnow()
            )
            
            self.logger.info("market_data_fetched_from_data_plane_sync", mode=self.mode)
            
        except Exception as e:
            self.logger.error("data_plane_fetch_sync_failed", error=str(e), exc_info=True)
            raise RuntimeError(f"Failed to fetch market data from Data Plane: {str(e)}. Mock data is disabled.")
    
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
        # Create pipeline state with signal context if available
        from app.schemas.pipeline_state import SignalData
        
        signal_data = None
        if self.signal_context:
            signal_data = SignalData(**self.signal_context)
        
        # DEBUG: Log scanner tickers state at beginning of execute
        self.logger.info("execute_symbol_debug", 
                        has_symbol_override=bool(self.symbol_override),
                        symbol_override=self.symbol_override,
                        scanner_tickers_type=type(self.scanner_tickers).__name__,
                        scanner_tickers_len=len(self.scanner_tickers) if self.scanner_tickers else 0,
                        scanner_tickers_bool=bool(self.scanner_tickers),
                        scanner_tickers_value=self.scanner_tickers if self.scanner_tickers else None,
                        config_symbol=self.config.get("symbol"))
        
        # Determine the symbol to use for this execution
        # Priority: 1. symbol_override (from signal), 2. scanner tickers, 3. config symbol, 4. UNKNOWN
        execution_symbol = "UNKNOWN"
        if self.symbol_override:
            execution_symbol = self.symbol_override
            self.logger.info("using_symbol_override", symbol=execution_symbol)
        elif self.scanner_tickers:
            # For scanner-based pipelines, use the first ticker
            # (Signal-based execution should provide symbol_override)
            execution_symbol = self.scanner_tickers[0]
            self.logger.info("using_scanner_ticker", symbol=execution_symbol, total_tickers=len(self.scanner_tickers))
        elif self.config.get("symbol"):
            execution_symbol = self.config.get("symbol")
            self.logger.info("using_config_symbol", symbol=execution_symbol)
        
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
        # Create pipeline state with signal context if available
        from app.schemas.pipeline_state import SignalData
        
        signal_data = None
        if self.signal_context:
            signal_data = SignalData(**self.signal_context)
        
        # Determine the symbol to use for this execution
        # Priority: 1. symbol_override (from signal), 2. scanner tickers, 3. config symbol, 4. UNKNOWN
        execution_symbol = "UNKNOWN"
        if self.symbol_override:
            execution_symbol = self.symbol_override
            self.logger.info("sync_using_symbol_override", symbol=execution_symbol)
        elif self.scanner_tickers:
            # For scanner-based pipelines, use the first ticker
            # (Signal-based execution should provide symbol_override)
            execution_symbol = self.scanner_tickers[0]
            self.logger.info("sync_using_scanner_ticker", symbol=execution_symbol, total_tickers=len(self.scanner_tickers))
        elif self.config.get("symbol"):
            execution_symbol = self.config.get("symbol")
            self.logger.info("sync_using_config_symbol", symbol=execution_symbol)
        
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
        final_status = "completed" if not state.errors else "failed"
        
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
        # Create pipeline state with signal context if available
        from app.schemas.pipeline_state import SignalData
        
        signal_data = None
        if self.signal_context:
            signal_data = SignalData(**self.signal_context)
        
        state = PipelineState(
            pipeline_id=self.pipeline.id,
            execution_id=self.execution_id,
            user_id=self.user_id,
            symbol=self.config.get("symbol", "UNKNOWN"),
            mode=self.mode,
            signal_data=signal_data
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
    
    async def _generate_pdf_report_async(self, execution: Any, db_session: Any):
        """
        Generate PDF report for completed execution.
        
        Runs in background to avoid blocking execution completion.
        """
        try:
            from app.services.pdf_generator import pdf_generator
            from app.services.executive_report_generator import executive_report_generator
            
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
            executive_summary = None
            try:
                executive_summary = await executive_report_generator.generate_executive_summary(
                    execution_data,
                    langfuse_trace=None
                )
            except Exception as e:
                self.logger.warning("executive_summary_generation_failed", error=str(e))
            
            # Generate PDF
            pdf_path = pdf_generator.generate_execution_report(
                execution_id=str(execution.id),
                execution_data=execution_data,
                executive_summary=executive_summary
            )
            
            # Update execution record with PDF path
            execution.report_pdf_path = pdf_path
            await db_session.commit()
            
            self.logger.info("pdf_report_generated_successfully", 
                           execution_id=str(execution.id),
                           pdf_path=pdf_path)
            
        except Exception as e:
            # Log error but don't fail the execution
            self.logger.error("pdf_generation_failed", 
                            execution_id=str(execution.id),
                            error=str(e))
    
    def _generate_pdf_report_sync(self, execution: Any, db_session: Any):
        """
        Generate PDF report for completed execution (synchronous version for Celery).
        
        Args:
            execution: Execution database record
            db_session: Synchronous SQLAlchemy session
        """
        try:
            from app.services.pdf_generator import pdf_generator
            from app.services.executive_report_generator import executive_report_generator
            import asyncio
            
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
            executive_summary = None
            try:
                # Run async code in sync context
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Create new event loop if one is already running
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    executive_summary = loop.run_until_complete(
                        executive_report_generator.generate_executive_summary(
                            execution_data,
                            langfuse_trace=None
                        )
                    )
                    loop.close()
                else:
                    executive_summary = loop.run_until_complete(
                        executive_report_generator.generate_executive_summary(
                            execution_data,
                            langfuse_trace=None
                        )
                    )
            except Exception as e:
                self.logger.warning("executive_summary_generation_failed", error=str(e))
            
            # Build comprehensive executive report (same structure as /executive-report endpoint)
            executive_report = {
                "execution_context": {
                    "id": str(execution.id),
                    "pipeline_name": execution_data["pipeline_name"],
                    "symbol": execution.symbol,
                    "mode": execution.mode,
                    "started_at": execution_data["started_at"],
                    "completed_at": execution_data["completed_at"],
                    "duration_seconds": execution_data["duration_seconds"],
                    "total_cost": execution.cost,
                },
                "agent_reports": execution.reports or {},
            }
            
            # Add AI-generated summary if available
            if executive_summary:
                executive_report.update(executive_summary)
            
            # Add execution artifacts and results
            if execution.result and isinstance(execution.result, dict):
                executive_report["execution_artifacts"] = execution.result.get("execution_artifacts", {})
                executive_report["strategy"] = execution.result.get("strategy")
                executive_report["bias"] = execution.result.get("biases")
                executive_report["risk_assessment"] = execution.result.get("risk_assessment")
                executive_report["trade_execution"] = execution.result.get("trade_execution")
            
            # Save executive report to database
            execution.executive_report = executive_report
            
            # Generate PDF using the full executive report (this is a sync method)
            pdf_path = pdf_generator.generate_execution_report(
                execution_id=str(execution.id),
                execution_data=execution_data,
                executive_summary=executive_summary,  # Keep for backward compatibility
                executive_report=executive_report  # Use full report
            )
            
            # Update execution record with PDF path
            execution.report_pdf_path = pdf_path
            db_session.commit()
            
            self.logger.info("pdf_report_generated_successfully", 
                           execution_id=str(execution.id),
                           pdf_path=pdf_path)
            
        except Exception as e:
            # Log error but don't fail the execution
            self.logger.error("pdf_generation_failed", 
                            execution_id=str(execution.id),
                            error=str(e),
                            exc_info=True)
    
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
            execution.cost = state.total_cost
            execution.logs = serialize_logs(state.execution_log)
            execution.agent_states = getattr(state, 'agent_execution_states', [])
            execution.reports = self._serialize_reports(state.agent_reports)
            execution.cost_breakdown = state.agent_costs
            
            # Generate PDF report if execution completed successfully
            if execution.status == ExecutionStatus.COMPLETED:
                await self._generate_pdf_report_async(execution, db_session)
            
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
        executor = PipelineExecutor(pipeline, user_id, mode, db_session=db_session)
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

