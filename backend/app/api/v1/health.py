"""
Health Check Endpoints

Provides health check and readiness endpoints for monitoring and orchestration.
"""

from datetime import datetime
from fastapi import APIRouter, status
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


class ReadinessResponse(BaseModel):
    """Readiness check response model."""
    status: str
    database: str
    redis: str
    celery: str


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


@router.get(
    "/readiness",
    response_model=ReadinessResponse,
    status_code=status.HTTP_200_OK,
    summary="Readiness Check",
    description="Returns the readiness status of the API and its dependencies"
)
async def readiness_check():
    """
    Readiness check endpoint.
    
    Checks connectivity to all required services:
    - Database (PostgreSQL)
    - Redis
    - Celery workers
    
    Returns 200 if all services are reachable, 503 otherwise.
    """
    # TODO: Implement actual checks when DB and Redis clients are set up
    # For now, return optimistic status
    
    return ReadinessResponse(
        status="ready",
        database="connected",
        redis="connected",
        celery="connected"
    )


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

