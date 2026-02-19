"""
Tiingo Market Data Provider

Provides stock market data via Tiingo REST API.

Free Tier:
- EOD (end-of-day) stock data
- IEX real-time quotes and intraday data
- 500 unique symbols/month
- ~50 requests/hour

Paid Tier ($30/mo):
- Higher rate limits
- Commercial use license
- Same API endpoints — seamless upgrade

API Endpoints:
- EOD Daily:   GET /tiingo/daily/<ticker>/prices
- IEX Quote:   GET /iex/<ticker>
- IEX Candles: GET /iex/<ticker>/prices?resampleFreq=5min&startDate=...

Authentication: Header "Authorization: Token <api_key>"

Documentation: https://www.tiingo.com/documentation/general/overview
"""
import httpx
from typing import List, Dict
from datetime import datetime, timedelta
import structlog
import time

from .base import BaseProvider, ProviderType, AssetClass


logger = structlog.get_logger()


# Tiingo IEX resample frequency mapping
TIMEFRAME_TO_RESAMPLE = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1hour",
    "4h": "4hour",
    "D": None,   # Use EOD endpoint
    "W": None,   # Use EOD endpoint
    "M": None,   # Use EOD endpoint
}

# Numeric (minutes) to resample frequency mapping
NUMERIC_TO_RESAMPLE = {
    1: "1min",
    5: "5min",
    15: "15min",
    30: "30min",
    60: "1hour",
    240: "4hour",
}


class TiingoProvider(BaseProvider):
    """
    Tiingo stock data provider.
    
    Features:
    - Real-time IEX quotes (last, bid, ask, volume)
    - Historical EOD candles (all US stocks)
    - Intraday IEX candles (1min to 4hour)
    - Stocks and crypto supported
    - Free tier: ~50 req/hour, 500 unique symbols/month
    - Paid tier ($30/mo): Higher limits, commercial use
    """
    
    BASE_URL = "https://api.tiingo.com"
    
    def __init__(self, api_key: str, **kwargs):
        """
        Initialize Tiingo provider.
        
        Args:
            api_key: Tiingo API token
        """
        super().__init__(api_key, **kwargs)
        self.headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
        }
        
        logger.info("tiingo_provider_initialized")
    
    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.TIINGO
    
    @property
    def supported_asset_classes(self) -> List[AssetClass]:
        # Tiingo supports stocks and crypto
        # Forex is handled by OANDA in our architecture
        return [AssetClass.STOCKS, AssetClass.CRYPTO]
    
    async def get_quote(
        self,
        symbol: str,
        asset_class: AssetClass = AssetClass.STOCKS
    ) -> Dict:
        """
        Get real-time quote from Tiingo IEX endpoint.
        
        IEX endpoint returns:
        [
            {
                "ticker": "AAPL",
                "tngoLast": 178.45,
                "last": 178.45,
                "lastSaleTimestamp": "2024-01-15T20:00:00+00:00",
                "prevClose": 177.50,
                "open": 178.00,
                "high": 179.20,
                "low": 177.80,
                "mid": 178.35,
                "bidPrice": 178.40,
                "askPrice": 178.50,
                "volume": 54321234,
                "bidSize": 100,
                "askSize": 200
            }
        ]
        """
        if asset_class not in (AssetClass.STOCKS, AssetClass.CRYPTO):
            raise ValueError(f"Tiingo does not support {asset_class}. Use OANDA for forex.")
        
        normalized_symbol = self.normalize_symbol(symbol, asset_class)
        
        url = f"{self.BASE_URL}/iex/{normalized_symbol}"
        
        start_time = time.time()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers=self.headers,
                    timeout=10.0
                )
                duration = time.time() - start_time
                
                response.raise_for_status()
                data = response.json()
                
                # Track successful API call
                self._track_api_call("quote", duration, "success")
                
                if not data:
                    raise ValueError(f"No quote data returned for {symbol}")
                
                # Tiingo returns a list, take the first item
                quote = data[0] if isinstance(data, list) else data
                
                current_price = quote.get("tngoLast") or quote.get("last", 0.0)
                
                # Parse timestamp
                timestamp_str = quote.get("lastSaleTimestamp", "")
                try:
                    timestamp = datetime.fromisoformat(
                        timestamp_str.replace("Z", "+00:00")
                    ) if timestamp_str else datetime.utcnow()
                except (ValueError, AttributeError):
                    timestamp = datetime.utcnow()
                
                return {
                    "symbol": symbol,
                    "current_price": current_price,
                    "bid": quote.get("bidPrice", current_price),
                    "ask": quote.get("askPrice", current_price),
                    "spread": round(
                        (quote.get("askPrice", 0) or 0) - (quote.get("bidPrice", 0) or 0),
                        4
                    ),
                    "high": quote.get("high", 0.0) or 0.0,
                    "low": quote.get("low", 0.0) or 0.0,
                    "open": quote.get("open", 0.0) or 0.0,
                    "previous_close": quote.get("prevClose", 0.0) or 0.0,
                    "volume": quote.get("volume", 0) or 0,
                    "timestamp": timestamp,
                }
        
        except httpx.HTTPStatusError as e:
            duration = time.time() - start_time
            self._track_api_call("quote", duration, "error")
            logger.error(
                "tiingo_quote_http_error",
                symbol=symbol,
                status_code=e.response.status_code,
                error=str(e)
            )
            raise
        except Exception as e:
            duration = time.time() - start_time
            self._track_api_call("quote", duration, "error")
            logger.error(
                "tiingo_quote_error",
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
        Get historical candle data from Tiingo.
        
        For intraday (1m–4h): Uses IEX historical prices endpoint
        For daily+: Uses EOD daily prices endpoint
        
        IEX historical response:
        [
            {
                "date": "2024-01-15T14:30:00+00:00",
                "open": 178.00,
                "high": 178.50,
                "low": 177.80,
                "close": 178.30,
                "volume": 12345
            }
        ]
        
        EOD response:
        [
            {
                "date": "2024-01-15T00:00:00+00:00",
                "close": 178.45,
                "high": 179.20,
                "low": 177.80,
                "open": 178.00,
                "volume": 54321234,
                "adjClose": 178.45,
                "adjHigh": 179.20,
                "adjLow": 177.80,
                "adjOpen": 178.00,
                "adjVolume": 54321234
            }
        ]
        """
        if asset_class not in (AssetClass.STOCKS, AssetClass.CRYPTO):
            raise ValueError(f"Tiingo does not support {asset_class}. Use OANDA for forex.")
        
        normalized_symbol = self.normalize_symbol(symbol, asset_class)
        resample_freq = self._get_resample_freq(timeframe)
        
        if resample_freq:
            # Intraday: use IEX endpoint
            return await self._get_intraday_candles(
                normalized_symbol, symbol, resample_freq, count
            )
        else:
            # Daily/Weekly/Monthly: use EOD endpoint
            return await self._get_eod_candles(
                normalized_symbol, symbol, timeframe, count
            )
    
    async def _get_intraday_candles(
        self,
        normalized_symbol: str,
        original_symbol: str,
        resample_freq: str,
        count: int
    ) -> List[Dict]:
        """Fetch intraday candles from Tiingo IEX historical endpoint."""
        # Calculate lookback based on resample frequency and count
        lookback_days = self._estimate_lookback_days(resample_freq, count)
        start_date = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        
        url = f"{self.BASE_URL}/iex/{normalized_symbol}/prices"
        params = {
            "startDate": start_date,
            "resampleFreq": resample_freq,
            "columns": "open,high,low,close,volume",
        }
        
        start_time = time.time()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers=self.headers,
                    params=params,
                    timeout=15.0
                )
                duration = time.time() - start_time
                
                response.raise_for_status()
                data = response.json()
                
                self._track_api_call("candles_intraday", duration, "success")
                
                if not data:
                    logger.warning(
                        "tiingo_no_intraday_data",
                        symbol=original_symbol,
                        resample_freq=resample_freq
                    )
                    return []
                
                # Convert to standard candle format, take last `count` candles
                candles = []
                for item in data[-count:]:
                    date_str = item.get("date", "")
                    try:
                        dt = datetime.fromisoformat(
                            date_str.replace("Z", "+00:00")
                        )
                    except (ValueError, AttributeError):
                        continue
                    
                    candles.append({
                        "time": dt.isoformat(),
                        "open": item.get("open", 0.0) or 0.0,
                        "high": item.get("high", 0.0) or 0.0,
                        "low": item.get("low", 0.0) or 0.0,
                        "close": item.get("close", 0.0) or 0.0,
                        "volume": item.get("volume", 0) or 0,
                    })
                
                logger.info(
                    "tiingo_intraday_candles_fetched",
                    symbol=original_symbol,
                    resample_freq=resample_freq,
                    count=len(candles)
                )
                
                return candles
        
        except httpx.HTTPStatusError as e:
            duration = time.time() - start_time
            self._track_api_call("candles_intraday", duration, "error")
            logger.error(
                "tiingo_intraday_http_error",
                symbol=original_symbol,
                status_code=e.response.status_code,
                error=str(e)
            )
            raise
        except Exception as e:
            duration = time.time() - start_time
            self._track_api_call("candles_intraday", duration, "error")
            logger.error(
                "tiingo_intraday_error",
                symbol=original_symbol,
                error=str(e),
                exc_info=True
            )
            raise
    
    async def _get_eod_candles(
        self,
        normalized_symbol: str,
        original_symbol: str,
        timeframe: str,
        count: int
    ) -> List[Dict]:
        """Fetch end-of-day candles from Tiingo EOD endpoint."""
        # Calculate start date based on count and timeframe
        if timeframe == "W":
            lookback_days = count * 7
        elif timeframe == "M":
            lookback_days = count * 30
        else:
            # Daily — account for weekends/holidays
            lookback_days = int(count * 1.5)
        
        start_date = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        end_date = datetime.utcnow().strftime("%Y-%m-%d")
        
        # Tiingo EOD supports resampleFreq for weekly/monthly
        resample = None
        if timeframe == "W":
            resample = "weekly"
        elif timeframe == "M":
            resample = "monthly"
        
        url = f"{self.BASE_URL}/tiingo/daily/{normalized_symbol}/prices"
        params = {
            "startDate": start_date,
            "endDate": end_date,
        }
        if resample:
            params["resampleFreq"] = resample
        
        start_time = time.time()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers=self.headers,
                    params=params,
                    timeout=15.0
                )
                duration = time.time() - start_time
                
                response.raise_for_status()
                data = response.json()
                
                self._track_api_call("candles_eod", duration, "success")
                
                if not data:
                    logger.warning(
                        "tiingo_no_eod_data",
                        symbol=original_symbol,
                        timeframe=timeframe
                    )
                    return []
                
                # Convert to standard candle format, take last `count`
                candles = []
                for item in data[-count:]:
                    date_str = item.get("date", "")
                    try:
                        dt = datetime.fromisoformat(
                            date_str.replace("Z", "+00:00")
                        )
                    except (ValueError, AttributeError):
                        continue
                    
                    # Use adjusted prices if available (more accurate for stocks)
                    candles.append({
                        "time": dt.isoformat(),
                        "open": item.get("adjOpen") or item.get("open", 0.0) or 0.0,
                        "high": item.get("adjHigh") or item.get("high", 0.0) or 0.0,
                        "low": item.get("adjLow") or item.get("low", 0.0) or 0.0,
                        "close": item.get("adjClose") or item.get("close", 0.0) or 0.0,
                        "volume": item.get("adjVolume") or item.get("volume", 0) or 0,
                    })
                
                logger.info(
                    "tiingo_eod_candles_fetched",
                    symbol=original_symbol,
                    timeframe=timeframe,
                    count=len(candles)
                )
                
                return candles
        
        except httpx.HTTPStatusError as e:
            duration = time.time() - start_time
            self._track_api_call("candles_eod", duration, "error")
            logger.error(
                "tiingo_eod_http_error",
                symbol=original_symbol,
                status_code=e.response.status_code,
                error=str(e)
            )
            raise
        except Exception as e:
            duration = time.time() - start_time
            self._track_api_call("candles_eod", duration, "error")
            logger.error(
                "tiingo_eod_error",
                symbol=original_symbol,
                error=str(e),
                exc_info=True
            )
            raise
    
    def normalize_symbol(self, symbol: str, asset_class: AssetClass) -> str:
        """
        Normalize symbol to Tiingo format.
        
        Stocks: "AAPL" → "aapl" (Tiingo prefers lowercase but accepts both)
        Crypto: "BTC/USD" → "btcusd"
        
        Args:
            symbol: User-provided symbol
            asset_class: Asset class
        
        Returns:
            Tiingo-format symbol
        """
        if asset_class == AssetClass.CRYPTO:
            # Convert BTC/USD → btcusd
            return symbol.replace("/", "").replace("-", "").lower()
        else:
            # Stocks: Tiingo accepts both cases but lowercase is canonical
            return symbol.upper().strip()
    
    def normalize_timeframe(self, timeframe: str) -> str:
        """
        Normalize timeframe to Tiingo resample frequency.
        
        Args:
            timeframe: Standard format (1m, 5m, 15m, 1h, 4h, D, W, M)
        
        Returns:
            Tiingo resampleFreq or original for EOD timeframes
        """
        resample = self._get_resample_freq(timeframe)
        return resample if resample else timeframe
    
    def _get_resample_freq(self, timeframe: str) -> str:
        """
        Convert timeframe to Tiingo resampleFreq for IEX endpoint.
        
        Returns None for EOD timeframes (D, W, M) which use a different endpoint.
        """
        # Check string mapping first
        if timeframe in TIMEFRAME_TO_RESAMPLE:
            return TIMEFRAME_TO_RESAMPLE[timeframe]
        
        # Try numeric (minutes) interpretation
        try:
            minutes = int(timeframe)
            return NUMERIC_TO_RESAMPLE.get(minutes)
        except ValueError:
            pass
        
        # Unknown timeframe, default to EOD
        return None
    
    def _estimate_lookback_days(self, resample_freq: str, count: int) -> int:
        """
        Estimate how many calendar days to look back for intraday data.
        
        Trading hours are ~6.5h/day (9:30-16:00 ET), so we need more calendar
        days than trading days.
        """
        # Minutes per candle
        freq_minutes = {
            "1min": 1,
            "5min": 5,
            "15min": 15,
            "30min": 30,
            "1hour": 60,
            "4hour": 240,
        }
        
        minutes_per_candle = freq_minutes.get(resample_freq, 5)
        total_minutes_needed = count * minutes_per_candle
        
        # ~390 trading minutes per day (6.5 hours)
        trading_days = max(1, total_minutes_needed // 390 + 1)
        
        # Add buffer for weekends/holidays (roughly 1.5x)
        calendar_days = int(trading_days * 1.5) + 2
        
        return max(1, calendar_days)
    
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
            "M": 2592000,
        }
        return mapping.get(timeframe, 86400)
