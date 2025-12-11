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

