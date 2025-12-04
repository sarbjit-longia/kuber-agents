"""
Market Data Tool

Fetches real-time and historical market data from Finnhub API.
Also includes MockMarketDataTool for testing with local data.
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import logging
import os

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
    
    @classmethod
    def get_metadata(cls):
        """Get metadata for this tool."""
        from app.schemas.tool import ToolMetadata, ToolConfigSchema
        
        return ToolMetadata(
            tool_type="market_data",
            name="Market Data",
            description="Fetches real-time and historical market data from Finnhub",
            category="data",
            version="1.0.0",
            icon="show_chart",
            is_free=True,  # Free tier available
            config_schema=ToolConfigSchema(
                type="object",
                title="Market Data Configuration",
                properties={
                    "api_key": {
                        "type": "string",
                        "title": "Finnhub API Key",
                        "description": "Optional API key (uses default if not provided)"
                    }
                },
                required=[]
            )
        )
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        # Set API key after parent init (which sets self.config)
        self.api_key = self.config.get("api_key") if self.config else None
        if not self.api_key:
            self.api_key = settings.FINNHUB_API_KEY
        self.base_url = "https://finnhub.io/api/v1"
    
    def _validate_config(self):
        """Validate that we have an API key."""
        if not hasattr(self, 'api_key'):
            self.api_key = settings.FINNHUB_API_KEY
        if not self.api_key:
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
        try:
            if timeframe.endswith("m"):
                minutes_str = timeframe[:-1]
                if not minutes_str:
                    raise ValueError(f"Invalid timeframe format: {timeframe}")
                minutes = int(minutes_str)
                lookback = timedelta(minutes=minutes * periods)
            elif timeframe.endswith("h"):
                hours_str = timeframe[:-1]
                if not hours_str:
                    raise ValueError(f"Invalid timeframe format: {timeframe}")
                hours = int(hours_str)
                lookback = timedelta(hours=hours * periods)
            elif timeframe == "1d":
                lookback = timedelta(days=periods)
            elif timeframe == "1w":
                lookback = timedelta(weeks=periods)
            elif timeframe == "1M":
                lookback = timedelta(days=30 * periods)
            else:
                lookback = timedelta(days=periods)
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid timeframe '{timeframe}': {str(e)}")
        
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
    
    Reads historical data from local files instead of calling external APIs.
    Uses time-shifting to simulate real-time market data from historical data.
    
    Features:
    - Uses real historical AAPL data stored locally
    - Smart time mapping: if current time is outside market hours (9:30 AM - 4 PM EST),
      it maps to equivalent time during market hours from the stored data
    - No API rate limits, works offline, reproducible tests
    
    Data source: backend/data/market_data/AAPL/*.json
    Generate data: python backend/scripts/download_market_data.py
    """
    
    @classmethod
    def get_metadata(cls):
        """Get metadata for this tool."""
        from app.schemas.tool import ToolMetadata, ToolConfigSchema
        
        return ToolMetadata(
            tool_type="mock_market_data",
            name="Mock Market Data (Testing)",
            description="Returns historical AAPL data for testing. No API calls, works offline.",
            category="data",
            version="1.0.0",
            icon="science",  # Science/test icon
            is_free=True,
            config_schema=ToolConfigSchema(
                type="object",
                title="Mock Market Data Configuration",
                properties={
                    "note": {
                        "type": "string",
                        "title": "Info",
                        "description": "This tool uses local AAPL data for testing. Run 'python backend/scripts/download_market_data.py' to generate data.",
                        "default": "Testing mode - uses historical data"
                    }
                },
                required=[]
            )
        )
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize mock tool without requiring API key."""
        # Don't call super().__init__ to avoid MarketDataTool's API key requirement
        from app.tools.base import BaseTool
        BaseTool.__init__(self, config)
        self.api_key = "mock-api-key"  # Dummy key
        self.data_dir = self._get_data_dir()
    
    def _get_data_dir(self):
        """Get the path to the data directory."""
        import os
        # backend/data/market_data/AAPL/
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(backend_dir, "data", "market_data", "AAPL")
    
    def _validate_config(self):
        """Skip validation for mock tool."""
        pass  # No API key validation needed for mock
    
    def _map_current_time_to_market_time(self, now: datetime) -> datetime:
        """
        Map current time to market hours if outside trading hours.
        
        Market hours: 9:30 AM - 4:00 PM EST
        
        Logic:
        - If current time is between 9:30 AM - 4:00 PM: use actual time
        - If before 9:30 AM: map to 10:00 AM
        - If after 4:00 PM: map to 2:00 PM
        
        Args:
            now: Current datetime
            
        Returns:
            Mapped datetime within market hours
        """
        # Get current time components
        current_hour = now.hour
        current_minute = now.minute
        
        # Market hours: 9:30 AM (9.5) to 4:00 PM (16.0)
        current_time_decimal = current_hour + current_minute / 60.0
        
        # Check if within market hours (9:30 AM = 9.5, 4:00 PM = 16.0)
        if 9.5 <= current_time_decimal <= 16.0:
            # Within market hours - use actual time
            mapped_time = now.replace(second=0, microsecond=0)
            logger.info(f"Current time {now.strftime('%H:%M')} is within market hours - using actual time")
        elif current_time_decimal < 9.5:
            # Before market open - map to 10:00 AM
            mapped_time = now.replace(hour=10, minute=0, second=0, microsecond=0)
            logger.info(f"Current time {now.strftime('%H:%M')} is before market open - mapping to 10:00 AM")
        else:
            # After market close - map to 2:00 PM
            mapped_time = now.replace(hour=14, minute=0, second=0, microsecond=0)
            logger.info(f"Current time {now.strftime('%H:%M')} is after market close - mapping to 2:00 PM")
        
        return mapped_time
    
    def _load_timeframe_data(self, timeframe: str, lookback_periods: int) -> List[TimeframeData]:
        """
        Load timeframe data from local JSON file.
        
        Args:
            timeframe: Timeframe (5m, 15m, 1h, 4h, 1d)
            lookback_periods: Number of periods to return
            
        Returns:
            List of TimeframeData objects
        """
        import json
        
        # Map timeframe to filename
        timeframe_map = {
            "5m": "5m.json",
            "15m": "15m.json",
            "1h": "1h.json",
            "4h": "4h.json",
            "1d": "1d.json"
        }
        
        filename = timeframe_map.get(timeframe)
        if not filename:
            logger.warning(f"Unsupported timeframe: {timeframe}, using 5m as fallback")
            filename = "5m.json"
        
        file_path = os.path.join(self.data_dir, filename)
        
        # Check if file exists
        if not os.path.exists(file_path):
            raise ToolError(
                f"Mock data file not found: {file_path}. "
                f"Run 'python backend/scripts/download_market_data.py' to generate data."
            )
        
        # Load data
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        candles_raw = data.get("candles", [])
        
        if not candles_raw:
            raise ToolError(f"No candle data found in {file_path}")
        
        # Get current time mapped to market hours
        current_time = self._map_current_time_to_market_time(datetime.now())
        
        # For intraday data (5m, 15m, 1h), filter candles up to current market time
        if timeframe in ["5m", "15m", "1h"]:
            # Historical data is from a past date, so we shift timestamps to "today"
            # Get the date of the first candle
            first_candle_ts = candles_raw[0]["timestamp"]
            first_candle_dt = datetime.fromtimestamp(first_candle_ts)
            
            # Calculate offset to shift to today
            today = datetime.now().date()
            historical_date = first_candle_dt.date()
            day_offset = (today - historical_date).days
            
            # Filter and shift candles up to current market time
            adjusted_candles = []
            for candle in candles_raw:
                # Shift timestamp to today
                original_dt = datetime.fromtimestamp(candle["timestamp"])
                shifted_dt = original_dt + timedelta(days=day_offset)
                
                # Only include candles up to current mapped market time
                if shifted_dt <= current_time:
                    adjusted_candles.append({
                        **candle,
                        "timestamp": int(shifted_dt.timestamp())
                    })
            
            candles_raw = adjusted_candles
        
        # Limit to lookback_periods
        candles_raw = candles_raw[-lookback_periods:]
        
        # Convert to TimeframeData objects
        candles = []
        for candle in candles_raw:
            candles.append(
                TimeframeData(
                    timeframe=timeframe,
                    open=candle["open"],
                    high=candle["high"],
                    low=candle["low"],
                    close=candle["close"],
                    volume=candle["volume"],
                    timestamp=datetime.fromtimestamp(candle["timestamp"])
                )
            )
        
        logger.info(f"Loaded {len(candles)} candles for {timeframe} (requested: {lookback_periods})")
        
        return candles
    
    async def execute(
        self,
        symbol: str,
        timeframes: List[str],
        lookback_periods: int = 100
    ) -> Dict[str, Any]:
        """
        Load mock market data from local files.
        
        Args:
            symbol: Trading symbol (always returns AAPL data)
            timeframes: List of timeframes
            lookback_periods: Number of periods
            
        Returns:
            Mock market data from local files
        """
        import os
        
        logger.info(f"Loading mock market data for {symbol} (using AAPL historical data)")
        
        # Note: We always use AAPL data regardless of symbol
        if symbol != "AAPL":
            logger.warning(f"Mock tool always uses AAPL data, ignoring symbol: {symbol}")
        
        # Load timeframe data
        timeframe_data = {}
        for timeframe in timeframes:
            try:
                candles = self._load_timeframe_data(timeframe, lookback_periods)
                timeframe_data[timeframe] = candles
            except Exception as e:
                logger.error(f"Failed to load {timeframe} data: {e}")
                raise ToolError(f"Failed to load mock data for {timeframe}: {e}")
        
        # Get current price from latest 5m candle
        if "5m" in timeframe_data and timeframe_data["5m"]:
            latest_candle = timeframe_data["5m"][-1]
            current_price = latest_candle.close
            bid = current_price * 0.9995  # Simulate spread
            ask = current_price * 1.0005
        elif timeframe_data:
            # Use any available timeframe
            latest_candle = list(timeframe_data.values())[0][-1]
            current_price = latest_candle.close
            bid = current_price * 0.9995
            ask = current_price * 1.0005
        else:
            raise ToolError("No timeframe data loaded")
        
        # Create quote
        quote = {
            "c": current_price,
            "h": latest_candle.high,
            "l": latest_candle.low,
            "o": latest_candle.open,
            "bid": bid,
            "ask": ask
        }
        
        logger.info(f"Mock data loaded - Price: ${current_price:.2f}, Timeframes: {len(timeframe_data)}")
        
        return {
            "symbol": "AAPL",  # Always AAPL in mock
            "current_price": current_price,
            "bid": bid,
            "ask": ask,
            "quote": quote,
            "timeframes": timeframe_data,
            "last_updated": datetime.utcnow()
        }

