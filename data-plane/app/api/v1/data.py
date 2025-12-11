"""Data Plane API endpoints"""
from fastapi import APIRouter, HTTPException, Query, Response
from typing import List, Optional
import json
import structlog

logger = structlog.get_logger()

router = APIRouter(prefix="/data", tags=["data"])


@router.get("/quote/{ticker}")
async def get_quote(ticker: str):
    """
    Get latest quote for a ticker (cached).
    
    Returns quote from Redis cache if available (< 60s for hot, < 5min for warm).
    If not cached, fetches on-demand from Finnhub.
    """
    from app.database import get_redis
    from app.services.data_fetcher import DataFetcher
    from app.config import settings
    from app.telemetry import get_meter
    
    redis = await get_redis()
    
    # Try cache first
    cached = await redis.get(f"quote:{ticker}")
    if cached:
        logger.debug("quote_cache_hit", ticker=ticker)
        return json.loads(cached)
    
    # Cache miss - fetch on-demand
    logger.info("quote_cache_miss_fetching_on_demand", ticker=ticker)
    
    meter = get_meter()
    fetcher = DataFetcher(settings.FINNHUB_API_KEY, redis, meter)
    await fetcher.fetch_quotes_batch([ticker], ttl=60)
    
    # Try again
    cached = await redis.get(f"quote:{ticker}")
    if cached:
        return json.loads(cached)
    
    raise HTTPException(status_code=404, detail=f"Quote not found for {ticker}")


@router.get("/candles/{ticker}")
async def get_candles(
    ticker: str,
    timeframe: str = Query("5m", description="Timeframe: 1m, 5m, 15m, 1h, 1d, etc."),
    limit: int = Query(100, description="Number of candles to return", ge=1, le=500)
):
    """
    Get OHLCV candles for a ticker.
    
    For Phase 1, fetches on-demand from Finnhub.
    Phase 3 will add TimescaleDB storage for historical data.
    """
    from app.services.data_fetcher import DataFetcher
    from app.config import settings
    from app.database import get_redis
    from app.telemetry import get_meter
    
    logger.info("fetching_candles", ticker=ticker, timeframe=timeframe, limit=limit)
    
    redis = await get_redis()
    meter = get_meter()
    fetcher = DataFetcher(settings.FINNHUB_API_KEY, redis, meter)
    
    candles = await fetcher.fetch_candles(ticker, timeframe, limit)
    
    return {
        "ticker": ticker,
        "timeframe": timeframe,
        "count": len(candles),
        "candles": candles
    }


@router.get("/batch")
async def get_batch_data(
    tickers: str = Query(..., description="Comma-separated list of tickers"),
    data_types: str = Query("quote", description="Comma-separated list: quote, candles")
):
    """
    Batch endpoint for fetching multiple tickers at once.
    
    Example: /data/batch?tickers=AAPL,GOOGL,MSFT&data_types=quote
    """
    from app.database import get_redis
    from app.services.data_fetcher import DataFetcher
    from app.config import settings
    from app.telemetry import get_meter
    
    ticker_list = [t.strip() for t in tickers.split(",")]
    types = [t.strip() for t in data_types.split(",")]
    
    logger.info("batch_request", tickers=ticker_list, types=types)
    
    redis = await get_redis()
    meter = get_meter()
    fetcher = DataFetcher(settings.FINNHUB_API_KEY, redis, meter)
    
    results = {}
    
    for ticker in ticker_list:
        results[ticker] = {}
        
        if "quote" in types:
            # Try cache first
            cached = await redis.get(f"quote:{ticker}")
            if cached:
                results[ticker]["quote"] = json.loads(cached)
            else:
                # Fetch on-demand
                await fetcher.fetch_quotes_batch([ticker], ttl=60)
                cached = await redis.get(f"quote:{ticker}")
                if cached:
                    results[ticker]["quote"] = json.loads(cached)
        
        if "candles" in types:
            candles = await fetcher.fetch_candles(ticker, "5m", 100)
            results[ticker]["candles"] = candles
    
    return results


@router.get("/universe")
async def get_universe():
    """
    Get current universe of tracked tickers.
    
    Returns hot and warm tickers.
    """
    from app.database import get_redis
    
    redis = await get_redis()
    
    hot_tickers = await redis.smembers("tickers:hot")
    warm_tickers = await redis.smembers("tickers:warm")
    
    return {
        "hot": sorted(list(hot_tickers)) if hot_tickers else [],
        "warm": sorted(list(warm_tickers)) if warm_tickers else [],
        "total": len(hot_tickers or []) + len(warm_tickers or [])
    }


@router.get("/health")
async def health():
    """Health check endpoint"""
    from app.database import get_redis
    
    try:
        redis = await get_redis()
        await redis.ping()
        redis_status = "ok"
    except:
        redis_status = "down"
    
    return {
        "status": "ok",
        "service": "data-plane",
        "redis": redis_status
    }


@router.get("/metrics-universe")
async def metrics_universe(response: Response):
    """
    Expose universe metrics in Prometheus format.
    This supplements the OpenTelemetry metrics with gauge values from Redis.
    """
    from app.database import get_redis
    
    redis = await get_redis()
    
    try:
        hot = await redis.get("metrics:universe:hot") or "0"
        warm = await redis.get("metrics:universe:warm") or "0"
        total = await redis.get("metrics:universe:total") or "0"
        
        # Prometheus format
        metrics_text = f"""# HELP universe_size Total number of tickers in universe
# TYPE universe_size gauge
universe_size {total}

# HELP universe_hot_tickers Number of hot tickers
# TYPE universe_hot_tickers gauge
universe_hot_tickers {hot}

# HELP universe_warm_tickers Number of warm tickers
# TYPE universe_warm_tickers gauge
universe_warm_tickers {warm}
"""
        response.headers["Content-Type"] = "text/plain; version=0.0.4"
        return Response(content=metrics_text, media_type="text/plain; version=0.0.4")
        
    except Exception as e:
        logger.error("metrics_universe_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch universe metrics")
