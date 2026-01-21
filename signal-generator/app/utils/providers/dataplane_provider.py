"""
Data Plane Provider

Uses the Data Plane API for fetching market data and calculating indicators.
This provider supports:
- Stocks (via Finnhub)
- Forex (via OANDA)
- Local indicator calculation (via TA-Lib)

Benefits:
- Works with any asset class
- Local indicator calculation (300x faster)
- Centralized caching
- No direct Finnhub rate limits
"""
import httpx
import pandas as pd
import structlog
from typing import Optional, Dict, List, Set
from datetime import datetime, timedelta

from app.utils.market_data_provider import MarketDataProvider

logger = structlog.get_logger()


class DataPlaneProvider(MarketDataProvider):
    """
    Data Plane provider - uses centralized data plane for all market data.
    
    This provider delegates to the Data Plane API which:
    - Routes to appropriate provider (Finnhub for stocks, OANDA for forex)
    - Calculates indicators locally using TA-Lib (no API calls)
    - Caches data in Redis (5 min TTL)
    """
    
    # Provider attributes (required by base class)
    provider_name: str = "Data Plane"
    rate_limit_per_minute: int = 999999  # No rate limit (Data Plane handles internally)
    supported_resolutions: Set[str] = {
        "1m", "5m", "15m", "30m",
        "1h", "2h", "4h", "8h",
        "D", "W", "M"
    }
    supported_indicators: Set[str] = {
        "rsi", "macd", "sma", "ema", "bbands",
        "stoch", "atr", "adx", "cci", "mfi", "obv"
    }
    
    def __init__(self, data_plane_url: str = "http://data-plane:8000"):
        """
        Initialize Data Plane provider.
        
        Args:
            data_plane_url: URL of the data plane service
        """
        self.data_plane_url = data_plane_url.rstrip("/")
        
        logger.info(
            "dataplane_provider_initialized",
            url=self.data_plane_url,
            supported_indicators=len(self.supported_indicators)
        )
    
    async def fetch_candles(
        self,
        symbol: str,
        resolution: str = "D",
        lookback_days: int = 365
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV candles from Data Plane.
        
        Args:
            symbol: Ticker symbol (e.g., "AAPL", "EUR_USD")
            resolution: Timeframe (e.g., "5m", "1h", "D")
            lookback_days: Days of history to fetch
            
        Returns:
            DataFrame with columns: time, open, high, low, close, volume
        """
        try:
            # Calculate how many candles we need based on lookback_days
            period_minutes = self._resolution_to_minutes(resolution)
            if period_minutes:
                limit = int((lookback_days * 24 * 60) / period_minutes)
                limit = min(limit, 500)  # Cap at API limit
            else:
                limit = lookback_days  # For daily/weekly/monthly
            
            url = f"{self.data_plane_url}/api/v1/data/candles/{symbol}"
            params = {
                "timeframe": resolution,
                "limit": limit
            }
            
            logger.debug(
                "fetching_candles_from_dataplane",
                symbol=symbol,
                resolution=resolution,
                limit=limit
            )
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
            
            candles = data.get("candles", [])
            if not candles:
                logger.warning("no_candles_returned", symbol=symbol, resolution=resolution)
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(candles)
            
            # Ensure required columns exist
            required_cols = ["timestamp", "open", "high", "low", "close", "volume"]
            if not all(col in df.columns or col == "timestamp" and "time" in df.columns for col in required_cols):
                logger.error(
                    "invalid_candle_format",
                    symbol=symbol,
                    columns=list(df.columns)
                )
                return None
            
            # Rename 'time' to 'timestamp' if needed
            if "time" in df.columns and "timestamp" not in df.columns:
                df = df.rename(columns={"time": "timestamp"})
            
            # Convert timestamp to datetime
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            
            logger.info(
                "candles_fetched_from_dataplane",
                symbol=symbol,
                resolution=resolution,
                count=len(df)
            )
            
            return df
        
        except httpx.HTTPStatusError as e:
            logger.error(
                "dataplane_candles_http_error",
                symbol=symbol,
                status_code=e.response.status_code,
                error=str(e),
                exc_info=True
            )
            return None
        
        except Exception as e:
            logger.error(
                "dataplane_candles_error",
                symbol=symbol,
                error=str(e),
                exc_info=True
            )
            return None
    
    async def fetch_indicator(
        self,
        symbol: str,
        indicator: str,
        resolution: str = "D",
        lookback_days: int = 365,
        **indicator_params
    ) -> Optional[Dict]:
        """
        Fetch technical indicator data from Data Plane (calculated locally).
        
        Args:
            symbol: Ticker symbol
            indicator: Indicator name (rsi, macd, sma, etc.)
            resolution: Timeframe
            lookback_days: Days of history (not used, Data Plane decides)
            **indicator_params: Indicator parameters (e.g., timeperiod=14)
            
        Returns:
            Dict with indicator values and metadata
        """
        try:
            url = f"{self.data_plane_url}/api/v1/data/indicators/{symbol}"
            
            # Build query parameters
            params = {
                "timeframe": resolution,
                "indicators": indicator
            }
            
            # Add indicator-specific parameters
            if indicator == "rsi":
                params["rsi_period"] = indicator_params.get("timeperiod", 14)
            elif indicator == "sma":
                params["sma_period"] = indicator_params.get("timeperiod", 20)
            elif indicator == "ema":
                params["ema_period"] = indicator_params.get("timeperiod", 12)
            elif indicator == "bbands":
                params["bbands_period"] = indicator_params.get("timeperiod", 20)
            
            logger.debug(
                "fetching_indicator_from_dataplane",
                symbol=symbol,
                indicator=indicator,
                resolution=resolution,
                params=params
            )
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
            
            # Extract indicator data
            indicators_data = data.get("indicators", {})
            if indicator not in indicators_data:
                logger.warning(
                    "indicator_not_in_response",
                    symbol=symbol,
                    indicator=indicator,
                    available=list(indicators_data.keys())
                )
                return None
            
            indicator_values = indicators_data[indicator]
            
            # Format response to match Finnhub format (for compatibility)
            result = {
                indicator: indicator_values,
                "timestamp": data.get("timestamp"),
                "ticker": symbol,
                "timeframe": resolution
            }
            
            logger.info(
                "indicator_fetched_from_dataplane",
                symbol=symbol,
                indicator=indicator,
                resolution=resolution
            )
            
            return result
        
        except httpx.HTTPStatusError as e:
            logger.error(
                "dataplane_indicator_http_error",
                symbol=symbol,
                indicator=indicator,
                status_code=e.response.status_code,
                error=str(e),
                exc_info=True
            )
            return None
        
        except Exception as e:
            logger.error(
                "dataplane_indicator_error",
                symbol=symbol,
                indicator=indicator,
                error=str(e),
                exc_info=True
            )
            return None
    
    async def get_latest_price(self, symbol: str) -> Optional[float]:
        """
        Get latest price from Data Plane.
        
        Args:
            symbol: Ticker symbol
            
        Returns:
            Latest price (float) or None
        """
        try:
            url = f"{self.data_plane_url}/api/v1/data/quote/{symbol}"
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
            
            price = data.get("current_price") or data.get("c")
            
            if price is None:
                logger.warning("no_price_in_quote", symbol=symbol, data=data)
                return None
            
            return float(price)
        
        except Exception as e:
            logger.error(
                "dataplane_price_error",
                symbol=symbol,
                error=str(e),
                exc_info=True
            )
            return None
    
    async def search_symbol(self, query: str) -> List[Dict[str, str]]:
        """
        Search for symbols (not implemented in Data Plane yet).
        
        Args:
            query: Search query
            
        Returns:
            Empty list (search not yet implemented)
        """
        logger.warning("search_symbol_not_implemented", query=query)
        return []
    
    def _resolution_to_minutes(self, resolution: str) -> Optional[int]:
        """Convert resolution string to minutes."""
        resolution_map = {
            "1m": 1,
            "5m": 5,
            "15m": 15,
            "30m": 30,
            "1h": 60,
            "2h": 120,
            "4h": 240,
            "8h": 480,
            "D": None,  # Daily - use days
            "W": None,  # Weekly
            "M": None   # Monthly
        }
        return resolution_map.get(resolution)
