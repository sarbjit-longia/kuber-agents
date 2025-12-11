"""Configuration for Data Plane service"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """Application settings"""
    
    # Service
    SERVICE_NAME: str = "data-plane"
    LOG_LEVEL: str = "INFO"
    
    # Finnhub
    FINNHUB_API_KEY: str
    
    # Redis
    REDIS_URL: str = "redis://redis:6379/1"
    
    # TimescaleDB (Data Plane database)
    TIMESCALE_URL: str = "postgresql+asyncpg://dev:devpass@timescaledb:5432/trading_data_plane"
    
    # Backend DB (to query scanners/pipelines)
    BACKEND_DB_URL: str = "postgresql+asyncpg://dev:devpass@postgres:5432/trading_platform"
    
    # Celery
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"
    
    # Metrics
    METRICS_PORT: int = 8001
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class CeleryConfig:
    """Celery configuration"""
    broker_url = "redis://redis:6379/1"
    result_backend = "redis://redis:6379/1"
    task_serializer = "json"
    result_serializer = "json"
    accept_content = ["json"]
    timezone = "UTC"
    enable_utc = True


settings = Settings()

