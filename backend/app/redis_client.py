"""
Redis Client Configuration

This module sets up Redis connection for caching and Celery.
"""

import redis.asyncio as redis
from app.config import settings
import structlog

logger = structlog.get_logger()

# Redis client instance
redis_client: redis.Redis = None


async def init_redis():
    """
    Initialize Redis connection.
    
    Called during application startup.
    """
    global redis_client
    
    redis_client = await redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )
    
    logger.info("redis_connected", url=settings.REDIS_URL)


async def close_redis():
    """
    Close Redis connection.
    
    Called during application shutdown.
    """
    global redis_client
    
    if redis_client:
        await redis_client.close()
        logger.info("redis_disconnected")


async def get_redis() -> redis.Redis:
    """
    Dependency for getting Redis client.
    
    Usage in FastAPI endpoints:
        @app.get("/cache")
        async def get_cache(redis: Redis = Depends(get_redis)):
            ...
    """
    return redis_client

