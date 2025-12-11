"""Data Plane FastAPI application"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog
import logging

from app.config import settings
from app.telemetry import setup_telemetry
from app.api.v1 import data

# Configure structured logging
log_level = getattr(logging, settings.LOG_LEVEL, logging.INFO)
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(log_level),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False
)

logger = structlog.get_logger()

# Create FastAPI app
app = FastAPI(
    title="Data Plane API",
    description="Centralized market data service with caching and aggregation",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup OpenTelemetry
meter = setup_telemetry(app, service_name=settings.SERVICE_NAME, metrics_port=settings.METRICS_PORT)

# Include routers
app.include_router(data.router, prefix="/api/v1")


@app.on_event("startup")
async def startup_event():
    """Startup tasks"""
    logger.info(
        "data_plane_starting",
        service=settings.SERVICE_NAME,
        metrics_port=settings.METRICS_PORT
    )


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown tasks"""
    logger.info("data_plane_shutting_down")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Data Plane",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health")
async def health():
    """Health check"""
    from app.database import get_redis
    
    try:
        redis = await get_redis()
        await redis.ping()
        redis_status = "ok"
    except:
        redis_status = "down"
    
    return {
        "status": "ok" if redis_status == "ok" else "degraded",
        "service": "data-plane",
        "redis": redis_status
    }

