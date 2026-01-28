"""Celery tasks for Data Plane"""
from celery import Celery
from celery.signals import worker_process_init
import structlog
import asyncio

logger = structlog.get_logger()

celery_app = Celery("data-plane")
celery_app.config_from_object("app.config:CeleryConfig")

# Initialize telemetry when worker starts
_telemetry_initialized = False

@worker_process_init.connect
def init_worker_process(**kwargs):
    """Initialize telemetry when worker process starts"""
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
        from app.config import settings
        from app.database import get_redis
        from app.telemetry import get_meter
        
        async def _fetch():
            redis = await get_redis()
            
            # Get hot tickers from Redis
            tickers = await redis.smembers("tickers:hot")
            ticker_list = list(tickers) if tickers else []
            
            if ticker_list:
                meter = get_meter()
                fetcher = DataFetcher(settings.FINNHUB_API_KEY, redis, meter)
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
        from app.config import settings
        from app.database import get_redis
        from app.telemetry import get_meter
        
        async def _fetch():
            redis = await get_redis()
            
            # Get warm tickers from Redis
            tickers = await redis.smembers("tickers:warm")
            ticker_list = list(tickers) if tickers else []
            
            if ticker_list:
                meter = get_meter()
                fetcher = DataFetcher(settings.FINNHUB_API_KEY, redis, meter)
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


@celery_app.task(name="data_plane.prefetch_indicators")
def prefetch_indicators_task():
    """
    Pre-fetch key indicators for universe tickers.
    
    Fetches Tier 1 indicators for all hot + warm tickers across key timeframes.
    This reduces on-demand fetching latency for agents.
    
    Runs every 5 minutes (indicators change slowly).
    """
    logger.info("task_prefetch_indicators_starting")
    
    try:
        from app.services.data_fetcher import DataFetcher
        from app.config import settings
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
            fetcher = DataFetcher(settings.FINNHUB_API_KEY, redis, meter)
            
            total_fetched = 0
            
            # Fetch indicators for each ticker/timeframe combination
            for ticker in tickers:
                for timeframe in TIMEFRAMES:
                    for indicator, params in INDICATORS:
                        try:
                            await fetcher.fetch_indicators(
                                ticker=ticker,
                                timeframe=timeframe,
                                indicators=[indicator],  # Pass as list, not string
                                params=params
                            )
                            total_fetched += 1
                            
                            # Small delay to avoid rate limits
                            await asyncio.sleep(0.1)
                            
                        except Exception as e:
                            logger.warning(
                                "indicator_prefetch_failed",
                                ticker=ticker,
                                timeframe=timeframe,
                                indicator=indicator,
                                error=str(e)
                            )
                            continue
            
            return {
                "tickers": len(tickers),
                "indicators": total_fetched
            }
        
        result = run_async(_prefetch())
        
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
    "prefetch-indicators": {
        "task": "data_plane.prefetch_indicators",
        "schedule": 300.0,  # Every 5 minutes
    },
}

celery_app.conf.timezone = "UTC"

