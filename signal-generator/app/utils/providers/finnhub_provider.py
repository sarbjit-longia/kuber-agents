"""
Finnhub Market Data Provider

Implementation of MarketDataProvider for Finnhub API.
Uses the official finnhub-python SDK: https://github.com/Finnhub-Stock-API/finnhub-python

Finnhub provides:
- 160 calls/minute (Basic tier)
- 80+ technical indicators
- Real-time and historical data
- Global coverage (stocks, forex, crypto)
"""
from typing import Optional, Dict, List
from datetime import datetime, timedelta
import pandas as pd
import finnhub
import asyncio
from functools import partial
import structlog

from app.utils.market_data_provider import MarketDataProvider
from app.telemetry import get_meter

logger = structlog.get_logger()


class FinnhubProvider(MarketDataProvider):
    """
    Finnhub API implementation using official Python SDK.
    
    All API calls are run in thread pool to avoid blocking the async event loop.
    Tracks metrics for monitoring and rate limiting.
    """
    
    def __init__(self, api_key: str):
        """
        Initialize Finnhub provider.
        
        Args:
            api_key: Finnhub API key
        """
        self.api_key = api_key
        self.client = finnhub.Client(api_key=api_key)
        
        # Initialize metrics
        try:
            meter = get_meter()
            
            # API call tracking
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
            
            self.rate_limit_remaining = meter.create_gauge(
                "provider_rate_limit_remaining",
                description="Estimated API calls remaining before rate limit"
            )
            
            self.rate_limit_usage_percent = meter.create_gauge(
                "provider_rate_limit_usage_percent",
                description="Percentage of rate limit used"
            )
            
            logger.info("finnhub_provider_metrics_initialized")
        except Exception as e:
            logger.warning("finnhub_provider_metrics_failed", error=str(e))
            self.api_calls_total = None
        
        # Rate limiting tracking
        self._call_timestamps = []  # Track recent API calls
        self._rate_limit_window = 60  # 1 minute window
        
        logger.info("finnhub_provider_initialized", api_key_present=bool(api_key))
    
    def _track_api_call(self, endpoint: str, duration: float, success: bool = True):
        """
        Track API call for metrics and rate limiting.
        
        Args:
            endpoint: API endpoint called (e.g., 'candles', 'indicator', 'quote')
            duration: Call duration in seconds
            success: Whether the call succeeded
        """
        if not self.api_calls_total:
            return
        
        # Track call
        self.api_calls_total.add(1, {
            "provider": "finnhub",
            "endpoint": endpoint,
            "status": "success" if success else "error"
        })
        
        # Track duration
        self.api_call_duration.record(duration, {
            "provider": "finnhub",
            "endpoint": endpoint
        })
        
        # Update rate limit tracking
        now = datetime.utcnow()
        self._call_timestamps.append(now)
        
        # Remove old timestamps outside the window
        cutoff = now - timedelta(seconds=self._rate_limit_window)
        self._call_timestamps = [ts for ts in self._call_timestamps if ts > cutoff]
        
        # Calculate rate limit metrics
        calls_in_window = len(self._call_timestamps)
        rate_limit = self.rate_limit_per_minute
        remaining = max(0, rate_limit - calls_in_window)
        usage_percent = (calls_in_window / rate_limit) * 100
        
        # Update gauges
        self.rate_limit_remaining.set(remaining, {"provider": "finnhub"})
        self.rate_limit_usage_percent.set(usage_percent, {"provider": "finnhub"})
    
    def _track_api_error(self, endpoint: str, error_type: str):
        """Track API error."""
        if self.api_errors_total:
            self.api_errors_total.add(1, {
                "provider": "finnhub",
                "endpoint": endpoint,
                "error_type": error_type
            })
    
    async def fetch_candles(
        self,
        symbol: str,
        resolution: str = "D",
        lookback_days: int = 365
    ) -> Optional[pd.DataFrame]:
        """
        Fetch historical candle data from Finnhub.
        
        Finnhub resolutions: 1, 5, 15, 30, 60, D, W, M
        """
        end_ts = int(datetime.utcnow().timestamp())
        start_ts = int((datetime.utcnow() - timedelta(days=lookback_days)).timestamp())
        
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Run blocking SDK call in thread pool
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                None,
                partial(
                    self.client.stock_candles,
                    symbol,
                    resolution,
                    start_ts,
                    end_ts
                )
            )
            
            duration = asyncio.get_event_loop().time() - start_time
            
            if not data or data.get("s") != "ok":
                self._track_api_call("candles", duration, success=False)
                self._track_api_error("candles", "no_data")
                logger.warning(
                    "finnhub_candles_failed",
                    symbol=symbol,
                    status=data.get("s") if data else "no_response",
                    resolution=resolution
                )
                return None
            
            # Track successful call
            self._track_api_call("candles", duration, success=True)
            
            # Convert to standardized DataFrame
            df = pd.DataFrame({
                "timestamp": pd.to_datetime(data["t"], unit="s"),
                "open": data["o"],
                "high": data["h"],
                "low": data["l"],
                "close": data["c"],
                "volume": data["v"]
            })
            
            df = df.sort_values("timestamp").reset_index(drop=True)
            
            logger.info(
                "finnhub_candles_fetched",
                symbol=symbol,
                resolution=resolution,
                candles=len(df)
            )
            
            return df
        
        except Exception as e:
            duration = asyncio.get_event_loop().time() - start_time
            self._track_api_call("candles", duration, success=False)
            self._track_api_error("candles", type(e).__name__)
            logger.error(
                "finnhub_candles_error",
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
        Fetch technical indicator from Finnhub.
        
        Finnhub supports 80+ indicators via /stock/candle endpoint with indicator parameter.
        Reference: https://docs.google.com/spreadsheets/d/1ylUvKHVYN2E87WdwIza8ROaCpd48ggEl1k5i5SgA29k
        """
        end_ts = int(datetime.utcnow().timestamp())
        start_ts = int((datetime.utcnow() - timedelta(days=lookback_days)).timestamp())
        
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Run blocking SDK call in thread pool
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                None,
                partial(
                    self.client.technical_indicator,
                    symbol,
                    resolution,
                    start_ts,
                    end_ts,
                    indicator,
                    indicator_params
                )
            )
            
            duration = asyncio.get_event_loop().time() - start_time
            
            if not data or data.get("s") != "ok":
                self._track_api_call("indicator", duration, success=False)
                self._track_api_error("indicator", "no_data")
                logger.warning(
                    "finnhub_indicator_failed",
                    symbol=symbol,
                    indicator=indicator,
                    status=data.get("s") if data else "no_response",
                    resolution=resolution
                )
                return None
            
            # Track successful call
            self._track_api_call("indicator", duration, success=True)
            
            # Convert to standardized format
            timestamps = [datetime.fromtimestamp(ts) for ts in data.get("t", [])]
            
            # Extract indicator values (key varies by indicator)
            values = {}
            for key, value in data.items():
                if key not in ["s", "t", "o", "h", "l", "c", "v"]:
                    values[key] = value
            
            # Include OHLCV if present
            ohlcv = {}
            if "o" in data:
                ohlcv = {
                    "open": data["o"],
                    "high": data["h"],
                    "low": data["l"],
                    "close": data["c"],
                    "volume": data["v"]
                }
            
            result = {
                "timestamps": timestamps,
                "values": values,
                "ohlcv": ohlcv
            }
            
            logger.info(
                "finnhub_indicator_fetched",
                symbol=symbol,
                indicator=indicator,
                resolution=resolution,
                data_points=len(timestamps)
            )
            
            return result
            
        except Exception as e:
            duration = asyncio.get_event_loop().time() - start_time
            self._track_api_call("indicator", duration, success=False)
            self._track_api_error("indicator", type(e).__name__)
            logger.error(
                "finnhub_indicator_error",
                symbol=symbol,
                indicator=indicator,
                error=str(e),
                exc_info=True
            )
            return None
    
    async def get_latest_price(self, symbol: str) -> Optional[float]:
        """Get latest price quote from Finnhub."""
        start_time = asyncio.get_event_loop().time()
        
        try:
            loop = asyncio.get_event_loop()
            quote = await loop.run_in_executor(
                None,
                self.client.quote,
                symbol
            )
            
            duration = asyncio.get_event_loop().time() - start_time
            
            if quote and "c" in quote:
                self._track_api_call("quote", duration, success=True)
                price = quote["c"]
                logger.info("finnhub_price_fetched", symbol=symbol, price=price)
                return price
            
            self._track_api_call("quote", duration, success=False)
            self._track_api_error("quote", "no_price")
            logger.warning("finnhub_price_unavailable", symbol=symbol)
            return None
            
        except Exception as e:
            duration = asyncio.get_event_loop().time() - start_time
            self._track_api_call("quote", duration, success=False)
            self._track_api_error("quote", type(e).__name__)
            logger.error(
                "finnhub_price_error",
                symbol=symbol,
                error=str(e),
                exc_info=True
            )
            return None
    
    async def search_symbol(self, query: str) -> List[Dict[str, str]]:
        """Search for symbols using Finnhub symbol lookup."""
        try:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                self.client.symbol_lookup,
                query
            )
            
            if not results or "result" not in results:
                return []
            
            # Convert to standardized format
            symbols = []
            for item in results["result"]:
                symbols.append({
                    "symbol": item.get("symbol", ""),
                    "name": item.get("description", ""),
                    "exchange": item.get("type", ""),
                    "type": item.get("displaySymbol", "")
                })
            
            logger.info("finnhub_symbol_search", query=query, results=len(symbols))
            return symbols
            
        except Exception as e:
            logger.error(
                "finnhub_search_error",
                query=query,
                error=str(e),
                exc_info=True
            )
            return []
    
    @property
    def provider_name(self) -> str:
        """Return provider name."""
        return "Finnhub"
    
    @property
    def rate_limit_per_minute(self) -> int:
        """Finnhub Basic tier: 160 calls/minute."""
        return 160
    
    @property
    def supported_resolutions(self) -> List[str]:
        """
        Finnhub supported resolutions.
        
        Minutes: 1, 5, 15, 30, 60
        Others: D (daily), W (weekly), M (monthly)
        """
        return ["1", "5", "15", "30", "60", "D", "W", "M"]
    
    @property
    def supported_indicators(self) -> List[str]:
        """
        Finnhub supports 80+ indicators.
        
        Reference: https://docs.google.com/spreadsheets/d/1ylUvKHVYN2E87WdwIza8ROaCpd48ggEl1k5i5SgA29k
        """
        return [
            # Moving Averages
            "sma", "ema", "wma", "dema", "tema", "trima", "kama", "mama", "t3",
            # Momentum Indicators
            "rsi", "macd", "stoch", "stochrsi", "willr", "cci", "mfi", "roc", "mom",
            # Volatility Indicators
            "bbands", "atr", "natr",
            # Volume Indicators
            "obv", "ad", "adosc",
            # Trend Indicators
            "adx", "adxr", "aroon", "aroonosc", "dx", "plus_di", "minus_di",
            # Overlap Studies
            "sar", "midpoint", "midprice", "ht_trendline",
            # Pattern Recognition
            "cdl2crows", "cdl3blackcrows", "cdl3inside", "cdl3linestrike",
            # And 50+ more...
        ]

