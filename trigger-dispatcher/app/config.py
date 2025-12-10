"""
Trigger Dispatcher Service - Configuration
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """Settings for the Trigger Dispatcher service."""
    
    SERVICE_NAME: str = "trigger-dispatcher"
    LOG_LEVEL: str = "INFO"
    
    # Kafka Configuration
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    KAFKA_SIGNAL_TOPIC: str = "trading-signals"
    KAFKA_CONSUMER_GROUP: str = "trigger-dispatcher"
    KAFKA_AUTO_OFFSET_RESET: str = "latest"  # 'earliest' or 'latest'
    
    # Batch Processing Configuration
    BATCH_SIZE: int = 20  # Process up to 20 signals at once
    BATCH_TIMEOUT_SECONDS: float = 0.5  # Process batch every 500ms
    
    # Cache Configuration
    CACHE_REFRESH_INTERVAL_SECONDS: int = 30  # Refresh pipeline cache every 30s
    
    # Database Configuration
    POSTGRES_USER: str = "dev"
    POSTGRES_PASSWORD: str = "devpass"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "trading_platform"
    
    # Celery Configuration
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/0"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True
    )
    
    @property
    def database_url(self) -> str:
        """Construct PostgreSQL database URL."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


settings = Settings()

