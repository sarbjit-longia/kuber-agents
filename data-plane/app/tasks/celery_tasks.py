"""Celery tasks for Data Plane"""
from celery import Celery
from celery.signals import worker_process_init
import structlog
import asyncio
import time as _time

logger = structlog.get_logger()

celery_app = Celery("data-plane")
celery_app.config_from_object("app.config:CeleryConfig")

# Initialize telemetry when worker starts
_telemetry_initialized = False


@worker_process_init.connect
def init_worker_process(**kwargs):
    """Initialize telemetry and trigger EOD backfill when worker process starts"""
    global _telemetry_initialized
    if not _telemetry_initialized:
        from app.telemetry import setup_telemetry
        from app.config import settings
        try:
            setup_telemetry(
                app=None,
                service_name="data-plane-worker",
                metrics_port=settings.METRICS_PORT
            )
            _telemetry_initialized = True
            logger.info("worker_telemetry_initialized")
        except Exception as e:
            # If port is already in use (multiple workers), that's okay
            logger.warning("worker_telemetry_init_failed", error=str(e))
            _telemetry_initialized = True  # Set to True to avoid retrying

    # Trigger one-time EOD backfill on worker startup (idempotent)
    try:
        celery_app.send_task("data_plane.seed_eod_candles", countdown=30)
        logger.info("seed_eod_candles_task_scheduled_on_startup")
    except Exception as e:
        logger.warning("seed_eod_task_schedule_failed", error=str(e))


def run_async(coro):
    """
    Helper to run async coroutines in Celery workers.
    Creates a new event loop for each task to avoid conflicts with multiprocessing.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        return loop.run_until_complete(coro)
    finally:
        # Don't close the loop, reuse it for subsequent tasks
        pass


def _get_stock_provider_instance():
    """Get configured stock data provider instance.

    Returns a BaseProvider based on the STOCK_PROVIDER setting
    (either 'tiingo' or 'finnhub').
    """
    from app.config import settings
    from app.providers import TiingoProvider, FinnhubProvider

    provider_name = getattr(settings, "STOCK_PROVIDER", "finnhub").lower()
    if provider_name == "tiingo" and settings.TIINGO_API_KEY:
        return TiingoProvider(api_key=settings.TIINGO_API_KEY)
    elif settings.FINNHUB_API_KEY:
        return FinnhubProvider(api_key=settings.FINNHUB_API_KEY)
    else:
        raise RuntimeError(
            "No stock provider API key configured. "
            "Set TIINGO_API_KEY or FINNHUB_API_KEY."
        )


# ---------------------------------------------------------------------------
# Existing tasks (fixed provider instantiation)
# ---------------------------------------------------------------------------


@celery_app.task(name="data_plane.refresh_universe")
def refresh_universe_task():
    """Refresh universe every 5 minutes"""
    logger.info("task_refresh_universe_starting")

    try:
        from app.services.universe_manager import UniverseManager
        from app.database import get_redis, BackendSessionLocal
        from app.telemetry import get_meter

        async def _refresh():
            redis = await get_redis()
            async with BackendSessionLocal() as backend_db:
                meter = get_meter()
                manager = UniverseManager(backend_db, redis, meter)
                return await manager.refresh_universe()

        result = run_async(_refresh())

        logger.info(
            "task_refresh_universe_completed",
            hot=len(result.get("hot", [])),
            warm=len(result.get("warm", []))
        )

        return result

    except Exception as e:
        logger.error("task_refresh_universe_failed", error=str(e))
        raise


@celery_app.task(name="data_plane.fetch_hot_tickers")
def fetch_hot_tickers_task():
    """Fetch hot tickers every 1 minute"""
    logger.info("task_fetch_hot_tickers_starting")

    try:
        from app.services.data_fetcher import DataFetcher
        from app.database import get_redis
        from app.telemetry import get_meter

        async def _fetch():
            redis = await get_redis()

            # Get hot tickers from Redis
            tickers = await redis.smembers("tickers:hot")
            ticker_list = list(tickers) if tickers else []

            if ticker_list:
                meter = get_meter()
                provider = _get_stock_provider_instance()
                fetcher = DataFetcher(provider, redis, meter)
                await fetcher.fetch_quotes_batch(ticker_list, ttl=60)

            return {"tickers_fetched": len(ticker_list)}

        result = run_async(_fetch())

        logger.info(
            "task_fetch_hot_tickers_completed",
            count=result["tickers_fetched"]
        )

        return result

    except Exception as e:
        logger.error("task_fetch_hot_tickers_failed", error=str(e))
        raise


@celery_app.task(name="data_plane.fetch_warm_tickers")
def fetch_warm_tickers_task():
    """Fetch warm tickers every 5 minutes"""
    logger.info("task_fetch_warm_tickers_starting")

    try:
        from app.services.data_fetcher import DataFetcher
        from app.database import get_redis
        from app.telemetry import get_meter

        async def _fetch():
            redis = await get_redis()

            # Get warm tickers from Redis
            tickers = await redis.smembers("tickers:warm")
            ticker_list = list(tickers) if tickers else []

            if ticker_list:
                meter = get_meter()
                provider = _get_stock_provider_instance()
                fetcher = DataFetcher(provider, redis, meter)
                await fetcher.fetch_quotes_batch(ticker_list, ttl=300)

            return {"tickers_fetched": len(ticker_list)}

        result = run_async(_fetch())

        logger.info(
            "task_fetch_warm_tickers_completed",
            count=result["tickers_fetched"]
        )

        return result

    except Exception as e:
        logger.error("task_fetch_warm_tickers_failed", error=str(e))
        raise


# ---------------------------------------------------------------------------
# New prefetch tasks
# ---------------------------------------------------------------------------


@celery_app.task(name="data_plane.prefetch_candles")
def prefetch_candles_task():
    """
    Prefetch candles for all universe tickers every 60 seconds.

    Flow per ticker:
    1. Fetch 500 1m candles from Tiingo (single API call)
    2. Write 1m candles to TimescaleDB hypertable
    3. Cache 1m candles in Redis
    4. Refresh TimescaleDB continuous aggregates (incremental, DB-side)
    5. Read pre-aggregated 5m/15m/1h/4h/D from continuous aggregates → Redis
    """
    logger.info("task_prefetch_candles_starting")
    task_start = _time.time()

    try:
        from app.services.data_fetcher import DataFetcher
        from app.services.timescale_writer import (
            write_candles,
            refresh_aggregates,
            read_aggregated_candles,
            CONTINUOUS_AGGREGATES,
        )
        from app.database import get_redis
        from app.telemetry import get_meter
        import json

        DERIVED_TIMEFRAMES = list(CONTINUOUS_AGGREGATES.keys())  # 5m, 15m, 1h, 4h

        async def _prefetch():
            redis = await get_redis()

            # Get all tickers (hot + warm)
            hot = await redis.smembers("tickers:hot")
            warm = await redis.smembers("tickers:warm")
            tickers = list((hot or set()) | (warm or set()))

            if not tickers:
                logger.info("no_tickers_to_prefetch_candles")
                return {"tickers": 0, "candles_cached": 0}

            provider = _get_stock_provider_instance()

            total_cached = 0

            # ---- Step 1-3: Fetch 1m → TimescaleDB + Redis ----
            for ticker in tickers:
                try:
                    candles_1m = await provider.get_candles(ticker, "1m", 500)
                    if not candles_1m:
                        continue

                    # Write to TimescaleDB (non-blocking, don't fail task)
                    try:
                        await write_candles(candles_1m, ticker, "1m")
                    except Exception as e:
                        logger.warning(
                            "timescale_write_failed",
                            ticker=ticker,
                            error=str(e),
                        )

                    # Cache 1m in Redis
                    ttl_1m = DataFetcher._get_candle_ttl("1m")
                    await redis.setex(
                        f"candles:1m:{ticker}",
                        ttl_1m,
                        json.dumps(candles_1m),
                    )
                    total_cached += 1

                except Exception as e:
                    logger.error(
                        "prefetch_candles_ticker_failed",
                        ticker=ticker,
                        error=str(e),
                    )

            # ---- Step 4: Refresh continuous aggregates (one call, DB-side) ----
            try:
                await refresh_aggregates()
            except Exception as e:
                logger.warning("aggregate_refresh_failed", error=str(e))

            # ---- Step 5: Read aggregated candles → Redis ----
            for ticker in tickers:
                for tf in DERIVED_TIMEFRAMES:
                    try:
                        candles = await read_aggregated_candles(ticker, tf, limit=200)
                        if candles:
                            ttl = DataFetcher._get_candle_ttl(tf)
                            await redis.setex(
                                f"candles:{tf}:{ticker}",
                                ttl,
                                json.dumps(candles),
                            )
                    except Exception as e:
                        logger.warning(
                            "aggregate_read_cache_failed",
                            ticker=ticker,
                            timeframe=tf,
                            error=str(e),
                        )

            return {"tickers": len(tickers), "candles_cached": total_cached}

        result = run_async(_prefetch())

        try:
            from app.telemetry import prefetch_task_duration_seconds
            prefetch_task_duration_seconds.labels(task="prefetch_candles").observe(_time.time() - task_start)
        except Exception:
            pass

        logger.info(
            "task_prefetch_candles_completed",
            tickers=result["tickers"],
            candles_cached=result["candles_cached"],
        )

        return result

    except Exception as e:
        logger.error("task_prefetch_candles_failed", error=str(e))
        raise


@celery_app.task(name="data_plane.seed_eod_candles")
def seed_eod_candles_task():
    """
    Seed historical daily (EOD) candles into TimescaleDB.

    Runs once on worker startup and then once daily to pick up newly closed days.
    After seeding, the daily continuous aggregate (ohlcv_daily) handles the
    current forming day from 1m data — no frequent EOD polling needed.

    For each ticker:
    1. Fetch 400 adjusted daily candles from Tiingo EOD endpoint
    2. Persist to TimescaleDB with timeframe='D' (ON CONFLICT DO NOTHING)
    """
    logger.info("task_seed_eod_candles_starting")
    task_start = _time.time()

    try:
        from app.services.timescale_writer import write_candles
        from app.database import get_redis

        async def _seed():
            redis = await get_redis()

            # Get all tickers (hot + warm)
            hot = await redis.smembers("tickers:hot")
            warm = await redis.smembers("tickers:warm")
            tickers = list((hot or set()) | (warm or set()))

            if not tickers:
                logger.info("no_tickers_to_seed_eod")
                return {"tickers": 0, "eod_seeded": 0}

            provider = _get_stock_provider_instance()

            eod_seeded = 0

            for ticker in tickers:
                try:
                    # Fetch 400 daily candles (headroom for SMA(200))
                    candles_d = await provider.get_candles(ticker, "D", 400)
                    if not candles_d:
                        continue

                    # Persist to TimescaleDB (ON CONFLICT DO NOTHING — idempotent)
                    await write_candles(candles_d, ticker, "D")
                    eod_seeded += 1

                except Exception as e:
                    logger.warning(
                        "eod_seed_failed",
                        ticker=ticker,
                        error=str(e),
                    )

            return {"tickers": len(tickers), "eod_seeded": eod_seeded}

        result = run_async(_seed())

        try:
            from app.telemetry import prefetch_task_duration_seconds
            prefetch_task_duration_seconds.labels(task="seed_eod_candles").observe(_time.time() - task_start)
        except Exception:
            pass

        logger.info(
            "task_seed_eod_candles_completed",
            tickers=result["tickers"],
            eod_seeded=result["eod_seeded"],
        )

        return result

    except Exception as e:
        logger.error("task_seed_eod_candles_failed", error=str(e))
        raise


@celery_app.task(name="data_plane.prefetch_indicators")
def prefetch_indicators_task():
    """
    Pre-fetch key indicators for universe tickers (batch mode).

    Fetches candles once per ticker+timeframe (cache hit from prefetch_candles_task),
    then calculates all 8 indicators in one pass via fetch_all_indicators().

    Runs every 5 minutes (indicators change slowly).
    """
    logger.info("task_prefetch_indicators_starting")
    task_start = _time.time()

    try:
        from app.services.data_fetcher import DataFetcher
        from app.database import get_redis
        from app.telemetry import get_meter

        # Tier 1 indicators with their default params
        INDICATORS = [
            ("sma", {"timeperiod": 20}),
            ("sma", {"timeperiod": 50}),
            ("sma", {"timeperiod": 200}),
            ("ema", {"timeperiod": 12}),
            ("ema", {"timeperiod": 26}),
            ("rsi", {"timeperiod": 14}),
            ("macd", {}),
            ("bbands", {"timeperiod": 20}),
        ]

        # Key timeframes (skip 5m and 15m to reduce API calls)
        TIMEFRAMES = ["1h", "4h", "D"]

        async def _prefetch():
            redis = await get_redis()

            # Get all tickers (hot + warm)
            hot = await redis.smembers("tickers:hot")
            warm = await redis.smembers("tickers:warm")
            tickers = list((hot or set()) | (warm or set()))

            if not tickers:
                logger.info("no_tickers_to_prefetch")
                return {"tickers": 0, "indicators": 0}

            meter = get_meter()
            provider = _get_stock_provider_instance()
            fetcher = DataFetcher(provider, redis, meter)

            total_fetched = 0

            # Batch: one candle fetch per ticker+timeframe, all indicators at once
            for ticker in tickers:
                for timeframe in TIMEFRAMES:
                    try:
                        result = await fetcher.fetch_all_indicators(
                            ticker=ticker,
                            timeframe=timeframe,
                            indicator_configs=INDICATORS,
                        )
                        if result and result.get("indicators"):
                            total_fetched += len(result["indicators"])
                    except Exception as e:
                        logger.warning(
                            "indicator_prefetch_failed",
                            ticker=ticker,
                            timeframe=timeframe,
                            error=str(e),
                        )
                        continue

            return {
                "tickers": len(tickers),
                "indicators": total_fetched,
            }

        result = run_async(_prefetch())

        try:
            from app.telemetry import prefetch_task_duration_seconds
            prefetch_task_duration_seconds.labels(task="prefetch_indicators").observe(_time.time() - task_start)
        except Exception:
            pass

        logger.info(
            "task_prefetch_indicators_completed",
            tickers=result["tickers"],
            indicators_fetched=result["indicators"]
        )

        return result

    except Exception as e:
        logger.error("task_prefetch_indicators_failed", error=str(e))
        raise


# Celery Beat Schedule
celery_app.conf.beat_schedule = {
    "refresh-universe": {
        "task": "data_plane.refresh_universe",
        "schedule": 300.0,  # Every 5 minutes
    },
    "fetch-hot-tickers": {
        "task": "data_plane.fetch_hot_tickers",
        "schedule": 60.0,  # Every 1 minute
    },
    "fetch-warm-tickers": {
        "task": "data_plane.fetch_warm_tickers",
        "schedule": 300.0,  # Every 5 minutes
    },
    "prefetch-candles": {
        "task": "data_plane.prefetch_candles",
        "schedule": 60.0,  # Every 1 minute — fetch 1m + derive 5m/15m/1h/4h
    },
    "seed-eod-candles": {
        "task": "data_plane.seed_eod_candles",
        "schedule": 86400.0,  # Once daily — refresh to pick up newly closed day
    },
    "prefetch-indicators": {
        "task": "data_plane.prefetch_indicators",
        "schedule": 300.0,  # Every 5 minutes
    },
}

celery_app.conf.timezone = "UTC"
