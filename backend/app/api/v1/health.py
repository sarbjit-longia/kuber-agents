"""
Health Check Endpoints

Provides health check and readiness endpoints for monitoring and orchestration.
"""

import asyncio
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import structlog

from app.config import settings

logger = structlog.get_logger()

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    timestamp: datetime
    environment: str
    version: str


class DependencyStatus(BaseModel):
    """Status of a single dependency."""
    status: str
    latency_ms: float
    error: Optional[str] = None


class ReadinessResponse(BaseModel):
    """Readiness check response model."""
    status: str
    database: DependencyStatus
    redis: DependencyStatus
    celery: DependencyStatus


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health Check",
    description="Returns the health status of the API service"
)
async def health_check():
    """
    Health check endpoint.

    Returns basic health information about the service.
    Used by Docker healthcheck and load balancers.
    """
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        environment=settings.ENV,
        version="0.1.0"
    )


async def _check_database() -> DependencyStatus:
    """Check database connectivity with SELECT 1."""
    start = time.monotonic()
    try:
        from sqlalchemy import text
        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        latency = (time.monotonic() - start) * 1000
        return DependencyStatus(status="ok", latency_ms=round(latency, 2))
    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        logger.error("readiness_db_check_failed", error=str(e))
        return DependencyStatus(status="down", latency_ms=round(latency, 2), error=str(e))


async def _check_redis() -> DependencyStatus:
    """Check Redis connectivity with PING."""
    start = time.monotonic()
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=3, socket_timeout=3)
        try:
            await r.ping()
        finally:
            await r.aclose()
        latency = (time.monotonic() - start) * 1000
        return DependencyStatus(status="ok", latency_ms=round(latency, 2))
    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        logger.error("readiness_redis_check_failed", error=str(e))
        return DependencyStatus(status="down", latency_ms=round(latency, 2), error=str(e))


async def _check_celery() -> DependencyStatus:
    """Check Celery worker availability with inspect ping."""
    start = time.monotonic()
    try:
        from app.orchestration.celery_app import celery_app

        result = await asyncio.to_thread(
            lambda: celery_app.control.inspect(timeout=3).ping()
        )
        latency = (time.monotonic() - start) * 1000
        if result:
            return DependencyStatus(status="ok", latency_ms=round(latency, 2))
        return DependencyStatus(
            status="down", latency_ms=round(latency, 2), error="no workers responded"
        )
    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        logger.error("readiness_celery_check_failed", error=str(e))
        return DependencyStatus(status="down", latency_ms=round(latency, 2), error=str(e))


@router.get(
    "/readiness",
    response_model=ReadinessResponse,
    summary="Readiness Check",
    description="Returns the readiness status of the API and its dependencies"
)
async def readiness_check():
    """
    Readiness check endpoint.

    Checks connectivity to all required services concurrently:
    - Database (PostgreSQL)
    - Redis
    - Celery workers

    Returns 200 if all services are reachable, 503 otherwise.
    """
    db_status, redis_status, celery_status = await asyncio.gather(
        _check_database(),
        _check_redis(),
        _check_celery(),
    )

    all_ok = all(s.status == "ok" for s in [db_status, redis_status, celery_status])

    response = ReadinessResponse(
        status="ready" if all_ok else "degraded",
        database=db_status,
        redis=redis_status,
        celery=celery_status,
    )

    status_code = status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(content=response.model_dump(), status_code=status_code)


@router.get(
    "/ping",
    status_code=status.HTTP_200_OK,
    summary="Ping",
    description="Simple ping endpoint"
)
async def ping():
    """
    Simple ping endpoint.

    Returns pong - used for basic connectivity testing.
    """
    return {"message": "pong"}
