"""
Market Data Agent

Fetches real-time and historical market data from the Data Plane (centralized cache).
This is a FREE agent (no LLM calls, no external API costs).
"""
from typing import Dict, Any
import asyncio
import httpx

from app.agents.base import BaseAgent, InsufficientDataError, AgentProcessingError
from app.schemas.pipeline_state import PipelineState, AgentMetadata, AgentConfigSchema, MarketData


class MarketDataAgent(BaseAgent):
    """
    Market Data Agent fetches market data from the Data Plane (centralized cache).
    
    This is a FREE agent (no LLM calls, no costs, reads from cache).
    It fetches:
    - Current price/quote from Redis cache (< 1 min old)
    - Historical candle data from Data Plane API
    
    Configuration:
        - timeframes: List of timeframes to fetch (e.g., ["5m", "1h", "4h", "1d"])
        - lookback_periods: Number of periods to fetch per timeframe (default: 100)
    
    Example config:
        {
            "timeframes": ["5m", "1h", "4h", "1d"],
            "lookback_periods": 100
        }
    """
    
    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(
            agent_type="market_data_agent",
            name="Market Data Agent",
            description="Fetches real-time and historical market data from centralized Data Plane (cached, fast, free). No external API calls or tools required.",
            category="data",
            version="2.0.0",  # Version 2.0 - uses Data Plane
            icon="database",
            pricing_rate=0.0,
            is_free=True,
            requires_timeframes=[],
            requires_market_data=False,
            requires_position=False,
            supported_tools=[],  # No tools needed!
            config_schema=AgentConfigSchema(
                type="object",
                title="Market Data Configuration",
                description="Configure which market data to fetch from Data Plane",
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
    
    def process(self, state: PipelineState) -> PipelineState:
        """
        Fetch market data from Data Plane and populate the state.
        
        Args:
            state: Current pipeline state
            
        Returns:
            Updated pipeline state with market data
            
        Raises:
            InsufficientDataError: If symbol is missing
            AgentProcessingError: If data fetch fails
        """
        self.log(state, f"Fetching market data from Data Plane (cached)")
        
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
            
            # Fetch market data from Data Plane API
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're already in an async context
                import nest_asyncio
                nest_asyncio.apply()
            
            market_data_dict = loop.run_until_complete(
                self._fetch_from_data_plane(state.symbol, timeframes, lookback_periods)
            )
            
            # Convert to MarketData schema
            state.market_data = MarketData(
                symbol=market_data_dict["symbol"],
                current_price=market_data_dict["current_price"],
                bid=market_data_dict.get("bid"),
                ask=market_data_dict.get("ask"),
                timestamp=market_data_dict.get("timestamp"),
                timeframes=market_data_dict.get("timeframes", {}),
                last_updated=market_data_dict.get("timestamp")
            )
            
            # Log summary
            total_candles = sum(len(candles) for candles in state.market_data.timeframes.values())
            self.log(
                state,
                f"✓ Market data fetched - Price: ${state.market_data.current_price:.2f}, "
                f"Candles: {total_candles} across {len(timeframes)} timeframes (from cache)"
            )
            self.record_report(
                state,
                title="Market data refreshed",
                summary=f"Fetched {total_candles} candles across {len(timeframes)} timeframes from Data Plane cache",
                metrics={
                    "current_price": state.market_data.current_price,
                    "timeframes": ", ".join(timeframes),
                    "total_candles": total_candles,
                },
                data={
                    "timeframes": timeframes,
                    "lookback_periods": lookback_periods,
                    "source": "data-plane-cache",
                },
            )
            
            # No cost for this agent (it's free)
            self.track_cost(state, 0.0)
            
            return state
        
        except Exception as e:
            error_msg = f"Failed to fetch market data from Data Plane: {str(e)}"
            self.add_error(state, error_msg)
            
            self.record_report(
                state,
                title="Market data fetch failed",
                summary=error_msg,
                status="failed",
                data={
                    "source": "data-plane",
                    "symbol": state.symbol,
                    "timeframes": timeframes if "timeframes" in locals() else self.config.get("timeframes"),
                    "lookback_periods": lookback_periods if "lookback_periods" in locals() else self.config.get("lookback_periods"),
                },
            )
            raise AgentProcessingError(error_msg) from e
    
    async def _fetch_from_data_plane(
        self,
        symbol: str,
        timeframes: list,
        lookback_periods: int
    ) -> Dict:
        """
        Fetch market data from Data Plane API (internal, cached, fast).
        
        Args:
            symbol: Stock ticker symbol
            timeframes: List of timeframes to fetch
            lookback_periods: Number of periods to fetch per timeframe
            
        Returns:
            Dictionary with market data
        """
        async with httpx.AsyncClient() as client:
            # Get quote (cached in Redis)
            quote_response = await client.get(
                f"http://data-plane:8000/api/v1/data/quote/{symbol}",
                timeout=5.0
            )
            quote_response.raise_for_status()
            quote = quote_response.json()
            
            # Get candles for all required timeframes
            timeframes_data = {}
            for tf in timeframes:
                candles_response = await client.get(
                    f"http://data-plane:8000/api/v1/data/candles/{symbol}",
                    params={"timeframe": tf, "limit": lookback_periods},
                    timeout=10.0
                )
                candles_response.raise_for_status()
                candles_data = candles_response.json()
                timeframes_data[tf] = candles_data["candles"]
            
            # Format response
            return {
                "symbol": symbol,
                "current_price": quote["current_price"],
                "bid": None,  # Not provided by Data Plane yet
                "ask": None,  # Not provided by Data Plane yet
                "timestamp": quote.get("timestamp"),
                "timeframes": timeframes_data
            }
