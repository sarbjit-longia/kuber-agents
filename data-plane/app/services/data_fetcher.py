"""Data Fetcher - Fetches data from multiple providers and caches in Redis"""
import structlog
from typing import List, Dict, Optional, Tuple
import redis.asyncio as aioredis
import json
from datetime import datetime, timedelta
from opentelemetry import metrics
import asyncio

from app.providers.base import BaseProvider
from app.services.indicator_calculator import IndicatorCalculator

logger = structlog.get_logger()

# TTLs per timeframe (seconds) — longer for slower timeframes
CANDLE_TTL = {
    "1m": 120,
    "5m": 360,
    "15m": 960,
    "1h": 3900,
    "4h": 14700,
    "D": 3600,
    "W": 7200,
    "M": 14400,
}


class DataFetcher:
    """Fetches data from market data providers and caches in Redis"""

    def __init__(
        self,
        provider: BaseProvider,
        redis: aioredis.Redis,
        meter: Optional[metrics.Meter] = None
    ):
        self.provider = provider
        self.redis = redis
        self.meter = meter
        self.indicator_calculator = IndicatorCalculator()

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

    @staticmethod
    def _get_candle_ttl(timeframe: str) -> int:
        """Return cache TTL in seconds for a given candle timeframe."""
        return CANDLE_TTL.get(timeframe, 3600)

    async def fetch_quotes_batch(self, tickers: List[str], ttl: int = 60):
        """Fetch quotes for multiple tickers and cache"""
        if not tickers:
            return

        logger.info("fetching_quotes_batch", count=len(tickers), ttl=ttl)

        for ticker in tickers:
            try:
                # Provider API call (async) - returns standardized format per BaseProvider interface
                quote = await self.provider.get_quote(ticker)

                # Cache in standardized format with backward compatibility keys
                quote_data = {
                    "ticker": ticker,
                    "current_price": quote.get("current_price"),
                    "c": quote.get("current_price"),  # Backward compatibility
                    "bid": quote.get("bid"),
                    "b": quote.get("bid"),  # Backward compatibility
                    "ask": quote.get("ask"),
                    "a": quote.get("ask"),  # Backward compatibility
                    "spread": quote.get("spread"),
                    "high": quote.get("high"),
                    "h": quote.get("high"),  # Backward compatibility
                    "low": quote.get("low"),
                    "l": quote.get("low"),  # Backward compatibility
                    "open": quote.get("open"),
                    "o": quote.get("open"),  # Backward compatibility
                    "previous_close": quote.get("previous_close"),
                    "pc": quote.get("previous_close"),  # Backward compatibility
                    "volume": quote.get("volume", 0),
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
        """
        Fetch OHLCV candles with Redis caching.

        Lookup order:
        1. Redis cache hit (populated by prefetch Celery tasks from
           TimescaleDB continuous aggregates) → return cached
        2. Fetch from provider → cache & return
        """
        cache_key = f"candles:{timeframe}:{ticker}"

        try:
            # 1. Check Redis cache
            cached = await self.redis.get(cache_key)
            if cached:
                from app.telemetry import candle_cache_hits_total
                candle_cache_hits_total.labels(timeframe=timeframe).inc()
                candles = json.loads(cached)
                logger.debug(
                    "candles_cache_hit",
                    ticker=ticker,
                    timeframe=timeframe,
                    count=len(candles),
                )
                return candles[-limit:] if len(candles) > limit else candles

            # 2. Fetch from provider (fallback when cache is empty)
            from app.telemetry import candle_cache_misses_total
            candle_cache_misses_total.labels(timeframe=timeframe).inc()
            candles = await self.provider.get_candles(ticker, timeframe, limit)

            if candles:
                ttl = self._get_candle_ttl(timeframe)
                await self.redis.setex(cache_key, ttl, json.dumps(candles))

                self._increment_counter(
                    self.candles_fetched_counter,
                    len(candles),
                    {"ticker": ticker, "timeframe": timeframe},
                )
                logger.info(
                    "candles_fetched",
                    ticker=ticker,
                    timeframe=timeframe,
                    count=len(candles),
                )
                return candles
            else:
                logger.warning("candles_not_found", ticker=ticker, timeframe=timeframe)
                return []

        except Exception as e:
            logger.error(
                "candles_fetch_failed",
                ticker=ticker,
                timeframe=timeframe,
                error=str(e),
            )
            return []

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
        indicators: List[str],
        params: Optional[Dict] = None
    ) -> Dict:
        """
        Calculate technical indicators locally from candle data.

        Supported indicators:
        - rsi: Relative Strength Index (rsi_period: 14)
        - macd: MACD (macd_fast: 12, macd_slow: 26, macd_signal: 9)
        - sma: Simple Moving Average (sma_period: 20)
        - ema: Exponential Moving Average (ema_period: 12)
        - bbands: Bollinger Bands (bbands_period: 20)
        - stoch: Stochastic Oscillator (stoch_k: 14, stoch_d: 3)
        - atr: Average True Range (atr_period: 14)
        - adx: Average Directional Index (adx_period: 14)

        Args:
            ticker: Stock/forex symbol
            timeframe: Timeframe (1m, 5m, 15m, 1h, 4h, D)
            indicators: List of indicator names to calculate
            params: Optional parameters for indicators

        Returns:
            Dictionary with all calculated indicator values
        """
        # Create cache key with params
        indicators_str = ",".join(sorted(indicators))
        params_str = json.dumps(params or {}, sort_keys=True)
        cache_key = f"indicators:{ticker}:{timeframe}:{indicators_str}:{params_str}"

        try:
            # Check cache first (5 minute TTL)
            cached = await self.redis.get(cache_key)
            if cached:
                logger.debug(
                    "indicators_cache_hit",
                    ticker=ticker,
                    indicators=indicators,
                    timeframe=timeframe
                )
                return json.loads(cached)

            # Cache miss - calculate locally
            logger.info(
                "calculating_indicators",
                ticker=ticker,
                indicators=indicators,
                timeframe=timeframe,
                params=params
            )

            # Fetch candles (now hits Redis cache first)
            candles = await self.fetch_candles(ticker, timeframe, limit=200)

            if not candles:
                logger.warning(
                    "no_candles_for_indicators",
                    ticker=ticker,
                    timeframe=timeframe
                )
                return {}

            # Calculate indicators locally (runs in thread pool to avoid blocking)
            loop = asyncio.get_event_loop()
            indicator_values = await loop.run_in_executor(
                None,
                self.indicator_calculator.calculate_indicators,
                candles,
                indicators,
                params or {}
            )

            if not indicator_values:
                logger.warning(
                    "indicator_calculation_failed",
                    ticker=ticker,
                    indicators=indicators
                )
                return {}

            # Format result
            result = {
                "ticker": ticker,
                "timeframe": timeframe,
                "timestamp": datetime.utcnow().isoformat(),
                "indicators": indicator_values
            }

            # Cache for 5 minutes
            await self.redis.setex(
                cache_key,
                300,  # 5 minutes
                json.dumps(result)
            )

            # Metrics
            if self.meter:
                indicators_counter = self.meter.create_counter(
                    name="indicators_calculated_total",
                    description="Total indicators calculated locally"
                )
                indicators_counter.add(len(indicators), {
                    "ticker": ticker,
                    "timeframe": timeframe
                })

            logger.info(
                "indicators_calculated",
                ticker=ticker,
                indicators=list(indicator_values.keys()),
                timeframe=timeframe
            )

            return result

        except Exception as e:
            logger.error(
                "indicator_calculation_failed",
                ticker=ticker,
                indicators=indicators,
                timeframe=timeframe,
                error=str(e)
            )

            # Metrics
            if self.meter:
                failures_counter = self.meter.create_counter(
                    name="indicator_calculation_failures_total",
                    description="Total indicator calculation failures"
                )
                failures_counter.add(1, {
                    "ticker": ticker,
                    "timeframe": timeframe
                })

            return {}

    async def fetch_all_indicators(
        self,
        ticker: str,
        timeframe: str,
        indicator_configs: List[Tuple[str, Dict]],
    ) -> Dict:
        """
        Fetch candles once and calculate ALL requested indicators in one pass.

        This avoids repeated candle fetches when computing multiple indicators
        for the same ticker+timeframe. Each indicator result is cached
        individually for compatibility with fetch_indicators() cache reads.

        Args:
            ticker: Stock/forex symbol
            timeframe: Candle timeframe (1m, 5m, 1h, D, ...)
            indicator_configs: List of (indicator_name, params) tuples,
                e.g. [("sma", {"timeperiod": 20}), ("rsi", {"timeperiod": 14})]

        Returns:
            Combined dict with all indicator values.
        """
        if not indicator_configs:
            return {}

        # Fetch candles once (hits Redis cache from prefetch_candles_task)
        candles = await self.fetch_candles(ticker, timeframe, limit=200)
        if not candles:
            logger.warning(
                "no_candles_for_batch_indicators",
                ticker=ticker,
                timeframe=timeframe,
            )
            return {}

        combined_indicators: Dict = {}
        loop = asyncio.get_event_loop()

        for indicator_name, params in indicator_configs:
            # Build per-indicator cache key (matches fetch_indicators format)
            indicators_str = indicator_name  # single indicator
            params_str = json.dumps(params or {}, sort_keys=True)
            cache_key = (
                f"indicators:{ticker}:{timeframe}:{indicators_str}:{params_str}"
            )

            # Check if already cached
            cached = await self.redis.get(cache_key)
            if cached:
                cached_data = json.loads(cached)
                combined_indicators.update(cached_data.get("indicators", {}))
                continue

            # Calculate this indicator
            try:
                indicator_values = await loop.run_in_executor(
                    None,
                    self.indicator_calculator.calculate_indicators,
                    candles,
                    [indicator_name],
                    params or {},
                )
            except Exception as e:
                logger.warning(
                    "batch_indicator_calc_failed",
                    ticker=ticker,
                    indicator=indicator_name,
                    error=str(e),
                )
                continue

            if not indicator_values:
                continue

            combined_indicators.update(indicator_values)

            # Cache individual indicator result (compatible with fetch_indicators)
            result = {
                "ticker": ticker,
                "timeframe": timeframe,
                "timestamp": datetime.utcnow().isoformat(),
                "indicators": indicator_values,
            }
            await self.redis.setex(cache_key, 300, json.dumps(result))

        logger.info(
            "batch_indicators_calculated",
            ticker=ticker,
            timeframe=timeframe,
            indicator_count=len(combined_indicators),
        )

        return {
            "ticker": ticker,
            "timeframe": timeframe,
            "timestamp": datetime.utcnow().isoformat(),
            "indicators": combined_indicators,
        }
