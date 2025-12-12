"""Data Fetcher - Fetches data from Finnhub and caches in Redis"""
import finnhub
import structlog
from typing import List, Dict, Optional
import redis.asyncio as aioredis
import json
from datetime import datetime, timedelta
from opentelemetry import metrics
import asyncio

logger = structlog.get_logger()


class DataFetcher:
    """Fetches data from Finnhub and caches in Redis"""
    
    def __init__(self, api_key: str, redis: aioredis.Redis, meter: Optional[metrics.Meter] = None):
        self.client = finnhub.Client(api_key=api_key)
        self.redis = redis
        self.meter = meter
        
        # Metrics (optional, only if meter provided)
        if meter:
            self.quotes_fetched_counter = meter.create_counter(
                name="quotes_fetched_total",
                description="Total quotes fetched from Finnhub"
            )
            
            self.quotes_cached_counter = meter.create_counter(
                name="quotes_cached_total",
                description="Total quotes cached in Redis"
            )
            
            self.quotes_fetch_failures_counter = meter.create_counter(
                name="quotes_fetch_failures_total",
                description="Total quote fetch failures"
            )
            
            self.candles_fetched_counter = meter.create_counter(
                name="candles_fetched_total",
                description="Total candles fetched from Finnhub"
            )
        else:
            # Dummy counters if no meter
            self.quotes_fetched_counter = None
            self.quotes_cached_counter = None
            self.quotes_fetch_failures_counter = None
            self.candles_fetched_counter = None
    
    def _increment_counter(self, counter, value=1, attributes=None):
        """Safely increment a counter if it exists"""
        if counter:
            counter.add(value, attributes or {})
    
    async def fetch_quotes_batch(self, tickers: List[str], ttl: int = 60):
        """Fetch quotes for multiple tickers and cache"""
        if not tickers:
            return
        
        logger.info("fetching_quotes_batch", count=len(tickers), ttl=ttl)
        
        for ticker in tickers:
            try:
                # Finnhub API call (synchronous, so run in executor)
                loop = asyncio.get_event_loop()
                quote = await loop.run_in_executor(None, self.client.quote, ticker)
                
                # Add metadata
                quote_data = {
                    "ticker": ticker,
                    "current_price": quote.get("c"),
                    "change": quote.get("d"),
                    "percent_change": quote.get("dp"),
                    "high": quote.get("h"),
                    "low": quote.get("l"),
                    "open": quote.get("o"),
                    "previous_close": quote.get("pc"),
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                # Cache in Redis
                await self.redis.setex(
                    f"quote:{ticker}",
                    ttl,
                    json.dumps(quote_data)
                )
                
                # Metrics
                self._increment_counter(self.quotes_fetched_counter, 1, {"ticker": ticker})
                self._increment_counter(self.quotes_cached_counter, 1, {"tier": "hot" if ttl == 60 else "warm"})
                
                logger.debug(
                    "quote_cached",
                    ticker=ticker,
                    price=quote_data.get("current_price"),
                    ttl=ttl
                )
                
            except Exception as e:
                self._increment_counter(self.quotes_fetch_failures_counter, 1, {"ticker": ticker})
                logger.error("quote_fetch_failed", ticker=ticker, error=str(e))
    
    async def fetch_candles(
        self,
        ticker: str,
        timeframe: str,
        limit: int = 100
    ) -> List[Dict]:
        """Fetch OHLCV candles from Finnhub"""
        
        # Map timeframe to Finnhub resolution
        resolution_map = {
            "1m": "1",
            "5m": "5",
            "15m": "15",
            "30m": "30",
            "1h": "60",
            "1d": "D",
            "1w": "W",
            "1M": "M"
        }
        
        resolution = resolution_map.get(timeframe, "D")
        
        try:
            # Calculate time range (last N periods)
            to_timestamp = int(datetime.utcnow().timestamp())
            period_seconds = self._get_period_seconds(timeframe)
            from_timestamp = to_timestamp - (period_seconds * limit)
            
            # Finnhub API call
            loop = asyncio.get_event_loop()
            candles = await loop.run_in_executor(
                None,
                self.client.stock_candles,
                ticker,
                resolution,
                from_timestamp,
                to_timestamp
            )
            
            if candles.get('s') == 'ok':
                formatted = self._format_candles(ticker, timeframe, candles)
                
                # Metrics
                self._increment_counter(
                    self.candles_fetched_counter,
                    len(formatted),
                    {"ticker": ticker, "timeframe": timeframe}
                )
                
                logger.info(
                    "candles_fetched",
                    ticker=ticker,
                    timeframe=timeframe,
                    count=len(formatted)
                )
                
                return formatted
            else:
                logger.warning("candles_not_found", ticker=ticker, timeframe=timeframe)
                return []
                
        except Exception as e:
            logger.error(
                "candles_fetch_failed",
                ticker=ticker,
                timeframe=timeframe,
                error=str(e)
            )
            return []
    
    def _format_candles(self, ticker: str, timeframe: str, candles: Dict) -> List[Dict]:
        """Format Finnhub candles response"""
        formatted = []
        for i in range(len(candles['t'])):
            formatted.append({
                "ticker": ticker,
                "timeframe": timeframe,
                "timestamp": datetime.fromtimestamp(candles['t'][i]).isoformat(),
                "open": candles['o'][i],
                "high": candles['h'][i],
                "low": candles['l'][i],
                "close": candles['c'][i],
                "volume": candles['v'][i]
            })
        return formatted
    
    def _get_period_seconds(self, timeframe: str) -> int:
        """Get seconds per period for timeframe"""
        periods = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "30m": 1800,
            "1h": 3600,
            "4h": 14400,
            "1d": 86400,
            "1w": 604800,
            "1M": 2592000,  # Approximate
        }
        return periods.get(timeframe, 86400)
    
    async def fetch_indicators(
        self,
        ticker: str,
        timeframe: str,
        indicator: str,
        params: Optional[Dict] = None
    ) -> Dict:
        """
        Fetch technical indicators from Finnhub and cache in Redis.
        
        Supported indicators (Tier 1):
        - sma: Simple Moving Average (timeperiod: 20, 50, 200)
        - ema: Exponential Moving Average (timeperiod: 12, 26)
        - rsi: Relative Strength Index (timeperiod: 14)
        - macd: MACD (default params)
        - bbands: Bollinger Bands (timeperiod: 20)
        
        Args:
            ticker: Stock symbol
            timeframe: Timeframe (5m, 15m, 1h, 4h, D)
            indicator: Indicator name (sma, ema, rsi, macd, bbands)
            params: Optional parameters for the indicator
            
        Returns:
            Dictionary with indicator values and metadata
        """
        # Create cache key with params
        params_str = json.dumps(params or {}, sort_keys=True)
        cache_key = f"indicator:{ticker}:{timeframe}:{indicator}:{params_str}"
        
        try:
            # Check cache first (5 minute TTL)
            cached = await self.redis.get(cache_key)
            if cached:
                logger.debug(
                    "indicator_cache_hit",
                    ticker=ticker,
                    indicator=indicator,
                    timeframe=timeframe
                )
                return json.loads(cached)
            
            # Cache miss - fetch from Finnhub
            logger.info(
                "fetching_indicator",
                ticker=ticker,
                indicator=indicator,
                timeframe=timeframe,
                params=params
            )
            
            # Convert timeframe to Finnhub resolution
            resolution_map = {
                "5m": "5",
                "15m": "15",
                "1h": "60",
                "4h": "240",
                "D": "D",
            }
            resolution = resolution_map.get(timeframe, "D")
            
            # Calculate time range (need enough history for indicators)
            to_timestamp = int(datetime.utcnow().timestamp())
            # Use 1 year of data for daily, 90 days for intraday
            lookback = 365 * 86400 if timeframe == "D" else 90 * 86400
            from_timestamp = to_timestamp - lookback
            
            # Fetch from Finnhub (synchronous call, use executor)
            loop = asyncio.get_event_loop()
            indicator_data = await loop.run_in_executor(
                None,
                self.client.technical_indicator,
                ticker,
                resolution,
                from_timestamp,
                to_timestamp,
                indicator,
                params or {}
            )
            
            if not indicator_data or indicator_data.get("s") != "ok":
                logger.warning(
                    "indicator_not_found",
                    ticker=ticker,
                    indicator=indicator,
                    response=indicator_data
                )
                return {}
            
            # Extract indicator values (exclude OHLCV keys)
            result = {
                "indicator": indicator,
                "timeframe": timeframe,
                "ticker": ticker,
                "timestamp": datetime.utcnow().isoformat(),
                "values": {}
            }
            
            excluded_keys = {"s", "t", "o", "h", "l", "c", "v"}
            
            for key, values in indicator_data.items():
                if key not in excluded_keys and values:
                    # Get latest value
                    if isinstance(values, list) and len(values) > 0:
                        result["values"][key] = values[-1]
                        # Also store last 50 values for charting
                        result["values"][f"{key}_history"] = values[-50:]
                    else:
                        result["values"][key] = values
            
            # Cache for 5 minutes (indicators don't change frequently)
            await self.redis.setex(
                cache_key,
                300,  # 5 minutes
                json.dumps(result)
            )
            
            # Metrics
            if self.meter:
                indicators_counter = self.meter.create_counter(
                    name="indicators_fetched_total",
                    description="Total indicators fetched from Finnhub"
                )
                indicators_counter.add(1, {
                    "ticker": ticker,
                    "timeframe": timeframe,
                    "indicator": indicator
                })
            
            logger.info(
                "indicator_fetched",
                ticker=ticker,
                indicator=indicator,
                timeframe=timeframe,
                keys=list(result["values"].keys())
            )
            
            return result
            
        except Exception as e:
            logger.error(
                "indicator_fetch_failed",
                ticker=ticker,
                indicator=indicator,
                timeframe=timeframe,
                error=str(e)
            )
            
            # Metrics
            if self.meter:
                failures_counter = self.meter.create_counter(
                    name="indicator_fetch_failures_total",
                    description="Total indicator fetch failures"
                )
                failures_counter.add(1, {
                    "ticker": ticker,
                    "timeframe": timeframe,
                    "indicator": indicator
                })
            
            return {}

