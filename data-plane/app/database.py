"""Database connections for Data Plane"""
import structlog
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
import redis.asyncio as aioredis
from app.config import settings

logger = structlog.get_logger()

# TimescaleDB (our data plane database)
timescale_engine = create_async_engine(
    settings.TIMESCALE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
)

TimescaleSessionLocal = async_sessionmaker(
    timescale_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Backend DB (to query scanners/pipelines) - READ ONLY
backend_engine = create_async_engine(
    settings.BACKEND_DB_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
)

BackendSessionLocal = async_sessionmaker(
    backend_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()

# Redis connection
_redis_client = None


async def get_redis() -> aioredis.Redis:
    """Get Redis client"""
    global _redis_client
    if _redis_client is None:
        _redis_client = await aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True
        )
    return _redis_client


async def get_timescale_db() -> AsyncSession:
    """Get TimescaleDB session"""
    async with TimescaleSessionLocal() as session:
        yield session


async def get_backend_db() -> AsyncSession:
    """Get Backend DB session (read-only)"""
    async with BackendSessionLocal() as session:
        yield session

