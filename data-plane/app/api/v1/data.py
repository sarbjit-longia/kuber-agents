"""Data Plane API endpoints"""
from fastapi import APIRouter, HTTPException, Query, Response
from typing import List, Optional
import json
import structlog

logger = structlog.get_logger()

router = APIRouter(prefix="/data", tags=["data"])


def _get_stock_provider():
    """
    Get the configured stock data provider (Tiingo or Finnhub).
    
    Uses STOCK_PROVIDER setting to determine which provider to use:
    - "tiingo": Uses Tiingo API (better rate limits, recommended)
    - "finnhub": Uses Finnhub API (legacy default)
    
    Falls back to whichever API key is available if the configured provider
    is not available.
    """
    from app.providers.tiingo import TiingoProvider
    from app.providers.finnhub import FinnhubProvider
    from app.config import settings
    
    stock_provider = getattr(settings, "STOCK_PROVIDER", "finnhub").lower()
    
    if stock_provider == "tiingo":
        if settings.TIINGO_API_KEY:
            logger.debug("using_tiingo_provider")
            return TiingoProvider(api_key=settings.TIINGO_API_KEY)
        elif settings.FINNHUB_API_KEY:
            logger.warning("tiingo_configured_but_no_key_falling_back_to_finnhub")
            return FinnhubProvider(api_key=settings.FINNHUB_API_KEY)
        else:
            raise HTTPException(
                status_code=500,
                detail="No stock data provider API key configured (TIINGO_API_KEY or FINNHUB_API_KEY)"
            )
    else:
        # Default: Finnhub
        if settings.FINNHUB_API_KEY:
            logger.debug("using_finnhub_provider")
            return FinnhubProvider(api_key=settings.FINNHUB_API_KEY)
        elif settings.TIINGO_API_KEY:
            logger.warning("finnhub_configured_but_no_key_falling_back_to_tiingo")
            return TiingoProvider(api_key=settings.TIINGO_API_KEY)
        else:
            raise HTTPException(
                status_code=500,
                detail="No stock data provider API key configured (FINNHUB_API_KEY or TIINGO_API_KEY)"
            )


@router.get("/quote/{ticker}")
async def get_quote(ticker: str):
    """
    Get latest quote for a ticker (cached).
    
    Supports both stocks (via Tiingo/Finnhub) and forex (via OANDA).
    Returns quote from Redis cache if available (< 60s for hot, < 5min for warm).
    """
    from app.database import get_redis
    from app.services.data_fetcher import DataFetcher
    from app.providers.oanda import OANDAProvider
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
    
    # Determine provider based on ticker (forex pairs have underscore)
    if "_" in ticker:
        # Forex pair (e.g., EUR_USD)
        if not settings.OANDA_API_KEY:
            raise HTTPException(status_code=500, detail="OANDA API key not configured")
        provider = OANDAProvider(
            api_key=settings.OANDA_API_KEY,
            account_type=settings.OANDA_ACCOUNT_TYPE
        )
    else:
        # Stock ticker - uses configured stock provider (Tiingo or Finnhub)
        provider = _get_stock_provider()
    
    meter = get_meter()
    fetcher = DataFetcher(provider, redis, meter)
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
    
    Supports both stocks (via Tiingo/Finnhub) and forex (via OANDA).
    Automatically routes based on ticker format (underscore = forex).
    """
    from app.services.data_fetcher import DataFetcher
    from app.providers.oanda import OANDAProvider
    from app.config import settings
    from app.database import get_redis
    from app.telemetry import get_meter
    
    logger.info("fetching_candles", ticker=ticker, timeframe=timeframe, limit=limit)
    
    # Determine provider based on ticker (forex pairs have underscore)
    if "_" in ticker:
        # Forex pair (e.g., EUR_USD)
        if not settings.OANDA_API_KEY:
            raise HTTPException(status_code=500, detail="OANDA API key not configured")
        provider = OANDAProvider(
            api_key=settings.OANDA_API_KEY,
            account_type=settings.OANDA_ACCOUNT_TYPE
        )
        logger.debug("using_oanda_provider", ticker=ticker)
    else:
        # Stock ticker - uses configured stock provider (Tiingo or Finnhub)
        provider = _get_stock_provider()
    
    redis = await get_redis()
    meter = get_meter()
    fetcher = DataFetcher(provider, redis, meter)
    
    candles = await fetcher.fetch_candles(ticker, timeframe, limit)
    
    return {
        "ticker": ticker,
        "timeframe": timeframe,
        "count": len(candles),
        "candles": candles
    }


@router.get("/indicators/{ticker}")
async def get_indicators(
    ticker: str,
    timeframe: str = Query("D", description="Timeframe: 5m, 15m, 1h, 4h, D"),
    indicators: str = Query("sma,rsi", description="Comma-separated list of indicators"),
    sma_period: Optional[int] = Query(20, description="SMA period (20, 50, 200)"),
    ema_period: Optional[int] = Query(12, description="EMA period (12, 26)"),
    rsi_period: Optional[int] = Query(14, description="RSI period"),
    bbands_period: Optional[int] = Query(20, description="Bollinger Bands period")
):
    """
    Get technical indicators for a ticker (calculated locally from candle data).
    
    Supports both stocks (via Tiingo/Finnhub) and forex (via OANDA).
    Indicators are calculated locally using TA-Lib (300x faster than API calls).
    
    Supported indicators:
    - sma: Simple Moving Average (default: 20)
    - ema: Exponential Moving Average (default: 12)
    - rsi: Relative Strength Index (default: 14)
    - macd: MACD (fixed params: 12/26/9)
    - bbands: Bollinger Bands (default: 20)
    
    Example:
        /data/indicators/AAPL?timeframe=D&indicators=sma,rsi,macd&sma_period=50
        /data/indicators/EUR_USD?timeframe=5m&indicators=rsi&rsi_period=14
    
    Returns:
        Dictionary with indicator results for each requested indicator
    """
    from app.services.data_fetcher import DataFetcher
    from app.providers.oanda import OANDAProvider
    from app.config import settings
    from app.database import get_redis
    from app.telemetry import get_meter
    
    indicator_list = [i.strip() for i in indicators.split(",")]
    
    logger.info(
        "fetching_indicators",
        ticker=ticker,
        timeframe=timeframe,
        indicators=indicator_list
    )
    
    # Determine provider based on ticker (forex pairs have underscore)
    if "_" in ticker:
        # Forex pair (e.g., EUR_USD)
        if not settings.OANDA_API_KEY:
            raise HTTPException(status_code=500, detail="OANDA API key not configured")
        provider = OANDAProvider(
            api_key=settings.OANDA_API_KEY,
            account_type=settings.OANDA_ACCOUNT_TYPE
        )
        logger.debug("using_oanda_provider", ticker=ticker)
    else:
        # Stock ticker - uses configured stock provider (Tiingo or Finnhub)
        provider = _get_stock_provider()
    
    redis = await get_redis()
    meter = get_meter()
    fetcher = DataFetcher(provider, redis, meter)
    
    # Build params dict for all indicators at once
    params = {
        "sma_period": sma_period,
        "ema_period": ema_period,
        "rsi_period": rsi_period,
        "bbands_period": bbands_period
    }
    
    try:
        # Fetch all indicators at once (more efficient)
        indicator_data = await fetcher.fetch_indicators(
            ticker=ticker,
            timeframe=timeframe,
            indicators=indicator_list,
            params=params
        )
        
        if indicator_data:
            return indicator_data
        else:
            raise HTTPException(
                status_code=404,
                detail=f"No indicator data available for {ticker}"
            )
            
    except Exception as e:
        logger.error(
            "indicator_fetch_error",
            ticker=ticker,
            timeframe=timeframe,
            indicators=indicator_list,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch indicators: {str(e)}"
        )


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
