"""
Market Data Tool

Fetches real-time and historical market data from Finnhub API.
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import logging

import httpx
from app.config import settings
from app.tools.base import BaseTool, ToolError
from app.schemas.pipeline_state import TimeframeData


logger = logging.getLogger(__name__)


class MarketDataTool(BaseTool):
    """
    Tool for fetching market data from Finnhub API.
    
    Features:
    - Real-time quotes
    - Historical candle data
    - Multiple timeframe support
    
    Configuration:
        api_key: Finnhub API key (optional, uses settings.FINNHUB_API_KEY by default)
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.api_key = self.config.get("api_key", settings.FINNHUB_API_KEY)
        self.base_url = "https://finnhub.io/api/v1"
    
    def _validate_config(self):
        """Validate that we have an API key."""
        if not self.api_key and not settings.FINNHUB_API_KEY:
            logger.warning("No Finnhub API key configured. Market data will not work.")
    
    async def execute(
        self,
        symbol: str,
        timeframes: List[str],
        lookback_periods: int = 100
    ) -> Dict[str, Any]:
        """
        Fetch market data for a symbol across multiple timeframes.
        
        Args:
            symbol: Trading symbol (e.g., "AAPL")
            timeframes: List of timeframes (e.g., ["5m", "1h", "4h", "1d"])
            lookback_periods: Number of periods to fetch for each timeframe
            
        Returns:
            Dictionary with current quote and timeframe data
            
        Raises:
            ToolError: If data fetch fails
        """
        try:
            # Get current quote
            quote = await self._get_quote(symbol)
            
            # Get candle data for each timeframe
            timeframe_data = {}
            for timeframe in timeframes:
                candles = await self._get_candles(symbol, timeframe, lookback_periods)
                timeframe_data[timeframe] = candles
            
            return {
                "symbol": symbol,
                "current_price": quote["c"],  # current price
                "bid": quote.get("bid"),
                "ask": quote.get("ask"),
                "quote": quote,
                "timeframes": timeframe_data,
                "last_updated": datetime.utcnow()
            }
        
        except Exception as e:
            logger.error(f"Failed to fetch market data for {symbol}: {e}")
            raise ToolError(f"Market data fetch failed: {e}")
    
    async def _get_quote(self, symbol: str) -> Dict[str, Any]:
        """
        Get current quote for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Quote data dictionary
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/quote",
                params={"symbol": symbol, "token": self.api_key},
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()
    
    async def _get_candles(
        self,
        symbol: str,
        timeframe: str,
        periods: int = 100
    ) -> List[TimeframeData]:
        """
        Get historical candle data.
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe (e.g., "5m", "1h", "1d")
            periods: Number of periods to fetch
            
        Returns:
            List of TimeframeData objects
        """
        # Map our timeframe format to Finnhub resolution
        resolution_map = {
            "1m": "1",
            "5m": "5",
            "15m": "15",
            "30m": "30",
            "1h": "60",
            "4h": "240",
            "1d": "D",
            "1w": "W",
            "1M": "M"
        }
        
        resolution = resolution_map.get(timeframe, "D")
        
        # Calculate time range
        now = datetime.utcnow()
        
        # Estimate lookback based on timeframe
        if timeframe.endswith("m"):
            minutes = int(timeframe[:-1])
            lookback = timedelta(minutes=minutes * periods)
        elif timeframe.endswith("h"):
            hours = int(timeframe[:-1])
            lookback = timedelta(hours=hours * periods)
        elif timeframe == "1d":
            lookback = timedelta(days=periods)
        elif timeframe == "1w":
            lookback = timedelta(weeks=periods)
        elif timeframe == "1M":
            lookback = timedelta(days=30 * periods)
        else:
            lookback = timedelta(days=periods)
        
        from_ts = int((now - lookback).timestamp())
        to_ts = int(now.timestamp())
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/stock/candle",
                params={
                    "symbol": symbol,
                    "resolution": resolution,
                    "from": from_ts,
                    "to": to_ts,
                    "token": self.api_key
                },
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()
        
        # Check if we got data
        if data.get("s") != "ok":
            logger.warning(f"No candle data available for {symbol} at {timeframe}")
            return []
        
        # Convert to TimeframeData objects
        candles = []
        for i in range(len(data["t"])):
            candles.append(
                TimeframeData(
                    timeframe=timeframe,
                    open=data["o"][i],
                    high=data["h"][i],
                    low=data["l"][i],
                    close=data["c"][i],
                    volume=data["v"][i],
                    timestamp=datetime.fromtimestamp(data["t"][i])
                )
            )
        
        return candles


class MockMarketDataTool(MarketDataTool):
    """
    Mock market data tool for testing and development.
    
    Returns synthetic data without calling external APIs.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize mock tool without requiring API key."""
        super().__init__(config)
        self.api_key = "mock-api-key"  # Set dummy key for mock
    
    def _validate_config(self):
        """Skip validation for mock tool."""
        pass  # No validation needed for mock
    
    async def execute(
        self,
        symbol: str,
        timeframes: List[str],
        lookback_periods: int = 100
    ) -> Dict[str, Any]:
        """
        Generate mock market data.
        
        Args:
            symbol: Trading symbol
            timeframes: List of timeframes
            lookback_periods: Number of periods
            
        Returns:
            Mock market data
        """
        import random
        
        # Generate a base price
        base_price = random.uniform(100, 500)
        
        # Mock current quote
        quote = {
            "c": base_price,
            "h": base_price * 1.01,
            "l": base_price * 0.99,
            "o": base_price * 0.995,
            "bid": base_price * 0.999,
            "ask": base_price * 1.001
        }
        
        # Generate mock candles for each timeframe
        timeframe_data = {}
        for timeframe in timeframes:
            candles = []
            price = base_price * 0.95  # Start lower
            
            for i in range(min(lookback_periods, 100)):
                # Random walk
                change = random.uniform(-0.02, 0.02)
                open_price = price
                close_price = price * (1 + change)
                high_price = max(open_price, close_price) * random.uniform(1.0, 1.01)
                low_price = min(open_price, close_price) * random.uniform(0.99, 1.0)
                
                candles.append(
                    TimeframeData(
                        timeframe=timeframe,
                        open=open_price,
                        high=high_price,
                        low=low_price,
                        close=close_price,
                        volume=int(random.uniform(1000000, 10000000)),
                        timestamp=datetime.utcnow() - timedelta(hours=lookback_periods - i)
                    )
                )
                
                price = close_price
            
            timeframe_data[timeframe] = candles
        
        return {
            "symbol": symbol,
            "current_price": quote["c"],
            "bid": quote["bid"],
            "ask": quote["ask"],
            "quote": quote,
            "timeframes": timeframe_data,
            "last_updated": datetime.utcnow()
        }

