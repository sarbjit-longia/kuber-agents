"""
Tiingo Market Data Provider for Signal Generator

Implementation of MarketDataProvider for Tiingo API.
Uses httpx for async HTTP requests.

Tiingo provides:
- Free tier: Real-time & historical stock data (suitable for dev/testing)
- Paid ($30/mo): Higher rate limits for commercial use
- 50 requests/hour (free), 1000+ (paid)

Documentation: https://api.tiingo.com/docs/tiingo/daily
"""
from typing import Optional, Dict, List
from datetime import datetime, timedelta
import pandas as pd
import httpx
import asyncio
import structlog

from app.utils.market_data_provider import MarketDataProvider
from app.telemetry import get_meter

logger = structlog.get_logger()


class TiingoProvider(MarketDataProvider):
    """
    Tiingo API implementation using httpx async client.
    
    Supports stock quotes, historical candles, and technical indicators
    (calculated locally from candle data since Tiingo doesn't provide
    server-side indicator calculation).
    
    Tracks metrics for monitoring and rate limiting.
    """
    
    def __init__(self, api_key: str):
        """
        Initialize Tiingo provider.
        
        Args:
            api_key: Tiingo API key
        """
        self.api_key = api_key
        self.base_url = "https://api.tiingo.com"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Token {self.api_key}"
        }
        
        # Initialize metrics
        try:
            meter = get_meter()
            
            self.api_calls_total = meter.create_counter(
                "provider_api_calls_total",
                description="Total API calls by provider and endpoint"
            )
            
            self.api_call_duration = meter.create_histogram(
                "provider_api_call_duration_seconds",
                description="API call duration by provider and endpoint"
            )
            
            self.api_errors_total = meter.create_counter(
                "provider_api_errors_total",
                description="Total API errors by provider and error type"
            )
            
            logger.info("tiingo_provider_metrics_initialized")
        except Exception as e:
            logger.warning("tiingo_provider_metrics_failed", error=str(e))
            self.api_calls_total = None
        
        # Rate limiting tracking
        self._call_timestamps = []
        self._rate_limit_window = 3600  # 1 hour window (Tiingo uses hourly rate limits)
        
        logger.info("tiingo_provider_initialized", api_key_present=bool(api_key))
    
    def _track_api_call(self, endpoint: str, duration: float, success: bool = True):
        """Track API call for metrics and rate limiting."""
        if not self.api_calls_total:
            return
        
        self.api_calls_total.add(1, {
            "provider": "tiingo",
            "endpoint": endpoint,
            "status": "success" if success else "error"
        })
        
        self.api_call_duration.record(duration, {
            "provider": "tiingo",
            "endpoint": endpoint
        })
        
        # Update rate limit tracking
        now = datetime.utcnow()
        self._call_timestamps.append(now)
        
        # Remove old timestamps outside the window
        cutoff = now - timedelta(seconds=self._rate_limit_window)
        self._call_timestamps = [ts for ts in self._call_timestamps if ts > cutoff]
    
    def _track_api_error(self, endpoint: str, error_type: str):
        """Track API error."""
        if self.api_errors_total:
            self.api_errors_total.add(1, {
                "provider": "tiingo",
                "endpoint": endpoint,
                "error_type": error_type
            })
    
    def _normalize_resolution(self, resolution: str) -> str:
        """
        Convert standard resolution format to Tiingo's resampleFreq format.
        
        Tiingo supports: 1min, 5min, 10min, 15min, 30min, 1hour, 1day, 1week, 1month
        """
        mapping = {
            "1": "1min",
            "1m": "1min",
            "5": "5min",
            "5m": "5min",
            "15": "15min",
            "15m": "15min",
            "30": "30min",
            "30m": "30min",
            "60": "1hour",
            "1h": "1hour",
            "4h": "1day",   # Tiingo doesn't support 4h, fallback to daily
            "D": "1day",
            "W": "1week",
            "M": "1month",
        }
        return mapping.get(resolution, "1day")
    
    def _is_intraday(self, resolution: str) -> bool:
        """Check if the resolution is intraday (requires IEX endpoint)."""
        intraday = {"1", "1m", "5", "5m", "15", "15m", "30", "30m", "60", "1h"}
        return resolution in intraday
    
    async def fetch_candles(
        self,
        symbol: str,
        resolution: str = "D",
        lookback_days: int = 365
    ) -> Optional[pd.DataFrame]:
        """
        Fetch historical candle data from Tiingo.
        
        Uses:
        - Daily endpoint for D, W, M resolutions
        - IEX endpoint for intraday resolutions (1m, 5m, 15m, 30m, 1h)
        """
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=lookback_days)
        tiingo_freq = self._normalize_resolution(resolution)
        
        start_time = asyncio.get_event_loop().time()
        
        try:
            async with httpx.AsyncClient() as client:
                if self._is_intraday(resolution):
                    # Use IEX endpoint for intraday data
                    url = f"{self.base_url}/iex/{symbol}/prices"
                    params = {
                        "token": self.api_key,
                        "startDate": start_date.strftime("%Y-%m-%d"),
                        "endDate": end_date.strftime("%Y-%m-%d"),
                        "resampleFreq": tiingo_freq,
                        "columns": "date,open,high,low,close,volume",
                    }
                else:
                    # Use daily endpoint for D, W, M
                    url = f"{self.base_url}/tiingo/daily/{symbol}/prices"
                    params = {
                        "token": self.api_key,
                        "startDate": start_date.strftime("%Y-%m-%d"),
                        "endDate": end_date.strftime("%Y-%m-%d"),
                        "resampleFreq": tiingo_freq,
                        "format": "json",
                    }
                
                response = await client.get(
                    url, headers=self.headers, params=params, timeout=15.0
                )
                
                duration = asyncio.get_event_loop().time() - start_time
                
                response.raise_for_status()
                data = response.json()
                
                if not data:
                    self._track_api_call("candles", duration, success=False)
                    self._track_api_error("candles", "no_data")
                    logger.warning(
                        "tiingo_candles_empty",
                        symbol=symbol,
                        resolution=resolution
                    )
                    return None
                
                self._track_api_call("candles", duration, success=True)
                
                # Convert to standardized DataFrame
                df = pd.DataFrame(data)
                
                # Tiingo uses "date" for timestamp
                if "date" in df.columns:
                    df["timestamp"] = pd.to_datetime(df["date"])
                elif "datetime" in df.columns:
                    df["timestamp"] = pd.to_datetime(df["datetime"])
                else:
                    logger.error("tiingo_candles_no_date_column", columns=list(df.columns))
                    return None
                
                # Standardize columns
                df = df.rename(columns={
                    "adjOpen": "open",
                    "adjHigh": "high",
                    "adjLow": "low",
                    "adjClose": "close",
                    "adjVolume": "volume",
                })
                
                # Ensure required columns exist
                required_cols = ["timestamp", "open", "high", "low", "close", "volume"]
                for col in required_cols:
                    if col not in df.columns:
                        logger.warning(
                            "tiingo_candles_missing_column",
                            column=col,
                            available=list(df.columns)
                        )
                        if col == "volume":
                            df[col] = 0
                        else:
                            return None
                
                df = df[required_cols].sort_values("timestamp").reset_index(drop=True)
                
                logger.info(
                    "tiingo_candles_fetched",
                    symbol=symbol,
                    resolution=resolution,
                    candles=len(df)
                )
                
                return df
        
        except httpx.HTTPStatusError as e:
            duration = asyncio.get_event_loop().time() - start_time
            self._track_api_call("candles", duration, success=False)
            self._track_api_error("candles", f"http_{e.response.status_code}")
            logger.error(
                "tiingo_candles_http_error",
                symbol=symbol,
                status_code=e.response.status_code,
                error=str(e)
            )
            return None
        except Exception as e:
            duration = asyncio.get_event_loop().time() - start_time
            self._track_api_call("candles", duration, success=False)
            self._track_api_error("candles", type(e).__name__)
            logger.error(
                "tiingo_candles_error",
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
        Fetch technical indicator data.
        
        Tiingo does not provide server-side indicator calculation,
        so we fetch candle data and calculate indicators locally
        using the same approach as the DataPlane provider.
        
        For direct Tiingo usage in signal-generator, it's recommended
        to use the DATA_PLANE provider type which handles indicator
        calculation via TA-Lib.
        """
        # Fetch candle data first
        df = await self.fetch_candles(symbol, resolution, lookback_days)
        if df is None or df.empty:
            return None
        
        # Return raw OHLCV data - indicator calculation should be done
        # by the caller or via the DataPlane provider
        timestamps = df["timestamp"].tolist()
        
        result = {
            "timestamps": timestamps,
            "values": {},
            "ohlcv": {
                "open": df["open"].tolist(),
                "high": df["high"].tolist(),
                "low": df["low"].tolist(),
                "close": df["close"].tolist(),
                "volume": df["volume"].tolist(),
            }
        }
        
        logger.info(
            "tiingo_indicator_data_prepared",
            symbol=symbol,
            indicator=indicator,
            resolution=resolution,
            data_points=len(timestamps),
            note="Tiingo returns raw OHLCV; use DataPlane for server-side indicators"
        )
        
        return result
    
    async def get_latest_price(self, symbol: str) -> Optional[float]:
        """Get latest price from Tiingo IEX endpoint."""
        start_time = asyncio.get_event_loop().time()
        
        try:
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}/iex/{symbol}"
                params = {"token": self.api_key}
                
                response = await client.get(
                    url, headers=self.headers, params=params, timeout=10.0
                )
                
                duration = asyncio.get_event_loop().time() - start_time
                
                response.raise_for_status()
                data = response.json()
                
                if data and len(data) > 0:
                    self._track_api_call("quote", duration, success=True)
                    price = data[0].get("last") or data[0].get("tngoLast")
                    logger.info("tiingo_price_fetched", symbol=symbol, price=price)
                    return price
                
                self._track_api_call("quote", duration, success=False)
                self._track_api_error("quote", "no_price")
                logger.warning("tiingo_price_unavailable", symbol=symbol)
                return None
        
        except httpx.HTTPStatusError as e:
            duration = asyncio.get_event_loop().time() - start_time
            self._track_api_call("quote", duration, success=False)
            self._track_api_error("quote", f"http_{e.response.status_code}")
            logger.error(
                "tiingo_price_http_error",
                symbol=symbol,
                status_code=e.response.status_code,
                error=str(e)
            )
            return None
        except Exception as e:
            duration = asyncio.get_event_loop().time() - start_time
            self._track_api_call("quote", duration, success=False)
            self._track_api_error("quote", type(e).__name__)
            logger.error(
                "tiingo_price_error",
                symbol=symbol,
                error=str(e),
                exc_info=True
            )
            return None
    
    async def search_symbol(self, query: str) -> List[Dict[str, str]]:
        """
        Search for symbols using Tiingo supported tickers endpoint.
        
        Note: Tiingo doesn't have a real-time search API like Finnhub.
        This queries the supported tickers list filtered by the query.
        """
        try:
            async with httpx.AsyncClient() as client:
                # Tiingo doesn't have a search endpoint, but we can use
                # the supported tickers endpoint and filter
                url = f"{self.base_url}/tiingo/utilities/search"
                params = {
                    "token": self.api_key,
                    "query": query,
                }
                
                response = await client.get(
                    url, headers=self.headers, params=params, timeout=10.0
                )
                
                response.raise_for_status()
                data = response.json()
                
                symbols = []
                for item in data[:20]:  # Limit results
                    symbols.append({
                        "symbol": item.get("ticker", ""),
                        "name": item.get("name", ""),
                        "exchange": item.get("exchange", ""),
                        "type": item.get("assetType", "Stock"),
                    })
                
                logger.info("tiingo_symbol_search", query=query, results=len(symbols))
                return symbols
        
        except Exception as e:
            logger.error(
                "tiingo_search_error",
                query=query,
                error=str(e),
                exc_info=True
            )
            return []
    
    @property
    def provider_name(self) -> str:
        """Return provider name."""
        return "Tiingo"
    
    @property
    def rate_limit_per_minute(self) -> int:
        """
        Tiingo rate limits (approximate per-minute equivalent):
        - Free: ~50 requests/hour ≈ 1/min
        - Paid ($30/mo): ~1000+ requests/hour ≈ 17/min
        """
        return 17  # Conservative estimate for paid tier
    
    @property
    def supported_resolutions(self) -> List[str]:
        """
        Tiingo supported resolutions.
        
        Intraday (via IEX): 1min, 5min, 15min, 30min, 1hour
        EOD: daily, weekly, monthly
        """
        return ["1", "5", "15", "30", "60", "D", "W", "M"]
    
    @property
    def supported_indicators(self) -> List[str]:
        """
        Tiingo doesn't provide server-side indicators.
        
        Indicators should be calculated locally from OHLCV data,
        or use the DataPlane provider which handles this via TA-Lib.
        
        Returns the list of indicators that can be calculated from
        the OHLCV data Tiingo provides.
        """
        return [
            "sma", "ema", "wma", "dema", "tema",
            "rsi", "macd", "stoch", "stochrsi", "willr", "cci", "mfi", "roc", "mom",
            "bbands", "atr", "natr",
            "obv", "ad", "adosc",
            "adx", "aroon", "dx",
            "sar",
        ]
