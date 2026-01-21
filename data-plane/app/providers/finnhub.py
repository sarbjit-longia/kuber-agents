"""
Finnhub Market Data Provider

Provides stock market data via Finnhub API.

Free Tier:
- US stocks (real-time)
- 60 API calls/minute
- Basic technical indicators

Premium Tier ($59-99/mo):
- Forex, crypto, international stocks
- Higher rate limits

Documentation: https://finnhub.io/docs/api
"""
import httpx
from typing import List, Dict
from datetime import datetime, timedelta
import structlog

from .base import BaseProvider, ProviderType, AssetClass


logger = structlog.get_logger()


class FinnhubProvider(BaseProvider):
    """
    Finnhub stock data provider.
    
    Features:
    - Real-time US stock quotes
    - Historical candles (all timeframes)
    - 10,000+ US stocks
    - Free tier: 60 calls/minute
    """
    
    def __init__(self, api_key: str, **kwargs):
        """
        Initialize Finnhub provider.
        
        Args:
            api_key: Finnhub API key
        """
        super().__init__(api_key, **kwargs)
        self.base_url = "https://finnhub.io/api/v1"
        
        logger.info("finnhub_provider_initialized")
    
    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.FINNHUB
    
    @property
    def supported_asset_classes(self) -> List[AssetClass]:
        # Free tier only supports stocks
        # Premium tier adds forex, crypto
        return [AssetClass.STOCKS]
    
    async def get_quote(
        self,
        symbol: str,
        asset_class: AssetClass = AssetClass.STOCKS
    ) -> Dict:
        """
        Get real-time quote from Finnhub.
        
        Example response:
        {
            "c": 178.45,  # current price
            "h": 179.20,  # high
            "l": 177.80,  # low
            "o": 178.00,  # open
            "pc": 177.50,  # previous close
            "t": 1705329600  # timestamp
        }
        """
        if asset_class != AssetClass.STOCKS:
            raise ValueError(f"Finnhub free tier only supports stocks, not {asset_class}")
        
        normalized_symbol = self.normalize_symbol(symbol, asset_class)
        
        url = f"{self.base_url}/quote"
        params = {
            "symbol": normalized_symbol,
            "token": self.api_key
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=10.0)
                response.raise_for_status()
                data = response.json()
                
                if "error" in data:
                    raise ValueError(f"Finnhub error: {data['error']}")
                
                current_price = data.get("c", 0.0)
                
                return {
                    "symbol": symbol,
                    "current_price": current_price,
                    "bid": current_price,  # Finnhub doesn't provide bid/ask for free tier
                    "ask": current_price,
                    "spread": 0.0,
                    "high": data.get("h", 0.0),
                    "low": data.get("l", 0.0),
                    "open": data.get("o", 0.0),
                    "previous_close": data.get("pc", 0.0),
                    "volume": 0,  # Not included in quote endpoint
                    "timestamp": datetime.fromtimestamp(data.get("t", 0))
                }
        
        except httpx.HTTPStatusError as e:
            logger.error(
                "finnhub_quote_http_error",
                symbol=symbol,
                status_code=e.response.status_code,
                error=str(e)
            )
            raise
        except Exception as e:
            logger.error(
                "finnhub_quote_error",
                symbol=symbol,
                error=str(e),
                exc_info=True
            )
            raise
    
    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 100,
        asset_class: AssetClass = AssetClass.STOCKS
    ) -> List[Dict]:
        """
        Get historical candle data from Finnhub.
        
        Example response:
        {
            "c": [178.45, 179.20, ...],  # close prices
            "h": [179.20, 180.00, ...],  # high prices
            "l": [177.80, 178.50, ...],  # low prices
            "o": [178.00, 178.80, ...],  # open prices
            "t": [1705329600, 1705333200, ...],  # timestamps
            "v": [1234567, 987654, ...]  # volumes
        }
        """
        if asset_class != AssetClass.STOCKS:
            raise ValueError(f"Finnhub free tier only supports stocks, not {asset_class}")
        
        normalized_symbol = self.normalize_symbol(symbol, asset_class)
        normalized_timeframe = self.normalize_timeframe(timeframe)
        
        # Calculate time range
        to_ts = int(datetime.now().timestamp())
        
        # Estimate from timestamp based on timeframe
        timeframe_seconds = self._get_timeframe_seconds(timeframe)
        from_ts = to_ts - (count * timeframe_seconds)
        
        url = f"{self.base_url}/stock/candle"
        params = {
            "symbol": normalized_symbol,
            "resolution": normalized_timeframe,
            "from": from_ts,
            "to": to_ts,
            "token": self.api_key
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=15.0)
                response.raise_for_status()
                data = response.json()
                
                if data.get("s") == "no_data":
                    logger.warning("finnhub_no_candle_data", symbol=symbol, timeframe=timeframe)
                    return []
                
                if "error" in data:
                    raise ValueError(f"Finnhub error: {data['error']}")
                
                # Convert Finnhub format to standard format
                candles = []
                for i in range(len(data.get("t", []))):
                    candles.append({
                        "time": datetime.fromtimestamp(data["t"][i]).isoformat(),
                        "open": data["o"][i],
                        "high": data["h"][i],
                        "low": data["l"][i],
                        "close": data["c"][i],
                        "volume": data["v"][i]
                    })
                
                logger.info(
                    "finnhub_candles_fetched",
                    symbol=symbol,
                    timeframe=timeframe,
                    count=len(candles)
                )
                
                return candles
        
        except httpx.HTTPStatusError as e:
            logger.error(
                "finnhub_candles_http_error",
                symbol=symbol,
                status_code=e.response.status_code,
                error=str(e)
            )
            raise
        except Exception as e:
            logger.error(
                "finnhub_candles_error",
                symbol=symbol,
                error=str(e),
                exc_info=True
            )
            raise
    
    def normalize_symbol(self, symbol: str, asset_class: AssetClass) -> str:
        """
        Normalize symbol to Finnhub format.
        
        Stocks: "AAPL" (no change)
        Forex (Premium): "OANDA:EUR_USD"
        
        Args:
            symbol: User-provided symbol
            asset_class: Asset class
        
        Returns:
            Finnhub format symbol
        """
        if asset_class == AssetClass.STOCKS:
            return symbol.upper()
        elif asset_class == AssetClass.FOREX:
            # Convert EUR/USD → OANDA:EUR_USD
            symbol = symbol.replace("/", "_")
            if ":" not in symbol:
                symbol = f"OANDA:{symbol}"
            return symbol.upper()
        else:
            return symbol.upper()
    
    def normalize_timeframe(self, timeframe: str) -> str:
        """
        Normalize timeframe to Finnhub resolution format.
        
        Supports both string and numeric (minute-based) formats:
        - String: "1m", "5m", "1h", "D" → "1", "5", "60", "D"
        - Numeric: "1", "5", "60" → "1", "5", "60" (pass-through)
        
        Args:
            timeframe: Standard format (string like "1h" or numeric like "60")
        
        Returns:
            Finnhub resolution (e.g., "5", "60", "D")
        """
        # String-based mapping
        mapping = {
            "1m": "1",
            "5m": "5",
            "15m": "15",
            "30m": "30",
            "1h": "60",
            "4h": "D",  # Finnhub doesn't support 4h, fallback to daily
            "D": "D",
            "W": "W",
            "M": "M"
        }
        
        # Check string mapping first
        if timeframe in mapping:
            return mapping[timeframe]
        
        # If it's already numeric (e.g., "1", "5", "60"), check if valid
        try:
            minutes = int(timeframe)
            # Finnhub supports: 1, 5, 15, 30, 60 (minutes), D, W, M
            if minutes in [1, 5, 15, 30, 60]:
                return timeframe  # Pass through numeric format
            elif minutes == 240:
                return "D"  # 4h → Daily (not supported)
            elif minutes >= 1440:
                return "D"  # Day or longer
        except ValueError:
            pass  # Not a numeric timeframe
        
        # Default: Daily
        return "D"
    
    def _get_timeframe_seconds(self, timeframe: str) -> int:
        """Get timeframe duration in seconds."""
        mapping = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "30m": 1800,
            "1h": 3600,
            "4h": 14400,
            "D": 86400,
            "W": 604800,
            "M": 2592000
        }
        return mapping.get(timeframe, 86400)
