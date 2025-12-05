"""
Market Data Agent

Fetches real-time and historical market data for the pipeline.
This is a FREE agent (no LLM calls).
"""
from typing import Dict, Any
import asyncio

from app.agents.base import BaseAgent, InsufficientDataError, AgentProcessingError
from app.schemas.pipeline_state import PipelineState, AgentMetadata, AgentConfigSchema, MarketData
from app.tools.market_data import MarketDataTool, MockMarketDataTool


class MarketDataAgent(BaseAgent):
    """
    Market Data Agent fetches market data for analysis.
    
    This is a FREE agent (no LLM calls, no costs).
    It fetches:
    - Current price/quote
    - Historical candle data for specified timeframes
    - Technical indicators (future enhancement)
    
    Configuration:
        - timeframes: List of timeframes to fetch (e.g., ["5m", "1h", "4h", "1d"])
        - lookback_periods: Number of periods to fetch per timeframe (default: 100)
        - use_mock_data: Whether to use mock data (for testing)
    
    Example config:
        {
            "timeframes": ["5m", "1h", "4h", "1d"],
            "lookback_periods": 100,
            "use_mock_data": false
        }
    """
    
    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(
            agent_type="market_data_agent",
            name="Market Data Agent",
            description="Fetches real-time and historical market data. Requires a Market Data Tool to be attached.",
            category="data",
            version="1.0.0",
            icon="show_chart",
            pricing_rate=0.0,
            is_free=True,
            requires_timeframes=[],
            requires_market_data=False,
            requires_position=False,
            supported_tools=["market_data", "mock_market_data"],  # Supports both real and mock market data tools
            config_schema=AgentConfigSchema(
                type="object",
                title="Market Data Configuration",
                description="Configure which market data to fetch",
                properties={
                    "timeframes": {
                        "type": "array",
                        "title": "Timeframes",
                        "description": "Which timeframes to fetch data for",
                        "items": {
                            "type": "string",
                            "enum": ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
                        },
                        "default": ["5m", "1h", "4h", "1d"]
                    },
                    "lookback_periods": {
                        "type": "integer",
                        "title": "Lookback Periods",
                        "description": "Number of historical periods to fetch",
                        "default": 100,
                        "minimum": 10,
                        "maximum": 500
                    }
                },
                required=["timeframes"]
            ),
            can_initiate_trades=False,
            can_close_positions=False
        )
    
    def __init__(self, agent_id: str, config: Dict[str, Any]):
        super().__init__(agent_id, config)
        # No hardcoded tools - will load from config
    
    def process(self, state: PipelineState) -> PipelineState:
        """
        Fetch market data and populate the state.
        
        Args:
            state: Current pipeline state
            
        Returns:
            Updated pipeline state with market data
            
        Raises:
            InsufficientDataError: If symbol is missing
            AgentProcessingError: If data fetch fails or no market data tool attached
        """
        # Load configured tools
        tools = self._load_tools()
        
        # Get market data tool (REQUIRED - must be attached by user)
        market_data_tool = tools.get("market_data")
        
        if not market_data_tool:
            raise AgentProcessingError(
                "Market Data Agent requires a Market Data Tool to be attached. "
                "Please attach a tool like 'Finnhub Market Data' in the pipeline builder."
            )
        
        self.log(state, f"Fetching market data (Using {market_data_tool.__class__.__name__})")
        
        # Validate we have a symbol
        if not state.symbol:
            raise InsufficientDataError("No symbol specified in pipeline state")
        
        try:
            # Get configuration
            timeframes = self.config.get("timeframes", ["5m", "1h", "4h", "1d"])
            
            # Handle case where timeframes might be a comma-separated string
            if isinstance(timeframes, str):
                timeframes = [tf.strip() for tf in timeframes.split(",")]
            
            lookback_periods = self.config.get("lookback_periods", 100)
            
            self.log(state, f"Fetching data for {state.symbol} - Timeframes: {','.join(timeframes)}")
            
            # Fetch market data (run async operation)
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're already in an async context, we need to use run_coroutine_threadsafe
                # or schedule it properly. For now, we'll use a simple approach:
                import nest_asyncio
                nest_asyncio.apply()
            
            market_data_dict = loop.run_until_complete(
                market_data_tool.execute(
                    symbol=state.symbol,
                    timeframes=timeframes,
                    lookback_periods=lookback_periods
                )
            )
            
            # Convert to MarketData schema
            state.market_data = MarketData(
                symbol=market_data_dict["symbol"],
                current_price=market_data_dict["current_price"],
                bid=market_data_dict.get("bid"),
                ask=market_data_dict.get("ask"),
                spread=(
                    market_data_dict.get("ask", 0) - market_data_dict.get("bid", 0)
                    if market_data_dict.get("ask") and market_data_dict.get("bid")
                    else None
                ),
                timeframes=market_data_dict["timeframes"],
                market_status="open",  # TODO: Determine actual market status
                last_updated=market_data_dict["last_updated"]
            )
            
            # Log summary
            total_candles = sum(len(candles) for candles in state.market_data.timeframes.values())
            self.log(
                state,
                f"✓ Market data fetched - Price: ${state.market_data.current_price:.2f}, "
                f"Candles: {total_candles} across {len(timeframes)} timeframes"
            )
            self.record_report(
                state,
                title="Market data refreshed",
                summary=f"Fetched {total_candles} candles across {len(timeframes)} timeframes",
                metrics={
                    "current_price": state.market_data.current_price,
                    "timeframes": ", ".join(timeframes),
                    "total_candles": total_candles,
                },
                data={
                    "timeframes": timeframes,
                    "lookback_periods": lookback_periods,
                    "tool": market_data_tool.__class__.__name__,
                },
            )
            
            # No cost for this agent (it's free)
            self.track_cost(state, 0.0)
            
            return state
        
        except Exception as e:
            error_msg = f"Failed to fetch market data: {str(e)}"
            self.add_error(state, error_msg)
            raise AgentProcessingError(error_msg) from e

