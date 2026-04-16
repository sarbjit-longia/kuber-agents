"""
Application Configuration

This module defines all configuration settings for the application using
Pydantic Settings for validation and environment variable loading.
"""

from typing import List, Optional
from pydantic import Field, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    All settings can be overridden via environment variables.
    """
    
    # Application
    ENV: str = Field(default="development", description="Environment (development, staging, production)")
    DEBUG: bool = Field(default=True, description="Debug mode")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    ALLOWED_ORIGINS: str | List[str] = Field(
        default=["http://localhost:4200", "http://localhost:3000"],
        description="CORS allowed origins"
    )
    
    # Database
    DATABASE_URL: str = Field(
        default="postgresql://dev:devpass@localhost:5432/trading_platform",
        description="PostgreSQL connection string"
    )
    
    # Redis
    REDIS_URL: str = Field(
        default="redis://localhost:6379",
        description="Redis connection string"
    )
    
    # Celery
    CELERY_BROKER_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Celery broker URL"
    )
    CELERY_RESULT_BACKEND: str = Field(
        default="redis://localhost:6379/0",
        description="Celery result backend URL"
    )
    
    # JWT Authentication
    JWT_SECRET: str = Field(
        default="your-super-secret-jwt-key-change-in-production",
        description="JWT secret key"
    )
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT algorithm")
    JWT_EXPIRATION_MINUTES: int = Field(default=1440, description="JWT token expiration in minutes (24h)")
    
    # LLM Provider
    LLM_PROVIDER: str = Field(
        default="openai",
        description="Active OpenAI-compatible provider: openai or openrouter"
    )

    # OpenAI
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="OpenAI API key")
    OPENAI_BASE_URL: Optional[str] = Field(
        default=None, 
        description="Optional OpenAI-compatible API base URL override"
    )
    OPENAI_MODEL: str = Field(default="gpt-4", description="Default OpenAI model")
    OPENAI_TEMPERATURE: float = Field(default=0.7, description="OpenAI temperature")
    OPENROUTER_API_KEY: Optional[str] = Field(default=None, description="OpenRouter API key")
    OPENROUTER_BASE_URL: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API base URL"
    )
    OPENROUTER_HTTP_REFERER: Optional[str] = Field(
        default=None,
        description="Optional HTTP-Referer header for OpenRouter requests"
    )
    OPENROUTER_APP_NAME: Optional[str] = Field(
        default="CloverCharts",
        description="Optional X-Title header for OpenRouter requests"
    )
    
    # Langfuse (Tracing & Observability)
    LANGFUSE_SECRET_KEY: Optional[str] = Field(default=None, description="Langfuse secret key")
    LANGFUSE_PUBLIC_KEY: Optional[str] = Field(default=None, description="Langfuse public key")
    LANGFUSE_BASE_URL: Optional[str] = Field(
        default=None,
        description="Langfuse API base URL (v2 compat)"
    )
    LANGFUSE_HOST: Optional[str] = Field(
        default=None,
        description="Langfuse host URL (v4 SDK reads this from env automatically)"
    )
    LANGFUSE_ENABLED: bool = Field(default=False, description="Enable Langfuse tracing")
    
    # Market Data (Finnhub)
    FINNHUB_API_KEY: Optional[str] = Field(default=None, description="Finnhub API key")
    
    # Data Plane
    DATA_PLANE_URL: str = Field(
        default="http://data-plane:8000",
        description="Data Plane service URL"
    )
    SIGNAL_GENERATOR_URL: str = Field(
        default="http://signal-generator:8000",
        description="Signal Generator service URL"
    )
    BACKTEST_KAFKA_BOOTSTRAP_SERVERS: str = Field(
        default="kafka:9092",
        description="Kafka bootstrap servers for backtest signal publication"
    )
    BACKTEST_KAFKA_SIGNAL_TOPIC: str = Field(
        default="trading-signals-backtest",
        description="Kafka topic for backtest signal publication"
    )
    BACKTEST_RUNTIME_MODE: str = Field(
        default="legacy_shared",
        description="Backtest launcher mode: legacy_shared, docker_container, or kubernetes_job"
    )
    BACKTEST_RUNTIME_IMAGE: Optional[str] = Field(
        default=None,
        description="Image used by the ephemeral backtest runtime launcher"
    )
    BACKTEST_RUNTIME_NAMESPACE: str = Field(
        default="backtest",
        description="Logical namespace used for backtest runtime isolation"
    )
    BACKTEST_RUNTIME_DOCKER_NETWORK: Optional[str] = Field(
        default=None,
        description="Docker network for ephemeral backtest runtime containers"
    )
    BACKTEST_RUNTIME_K8S_NAMESPACE: Optional[str] = Field(
        default=None,
        description="Kubernetes namespace used for ephemeral backtest runtime jobs"
    )
    BACKTEST_RUNTIME_K8S_SERVICE_ACCOUNT: Optional[str] = Field(
        default=None,
        description="Optional Kubernetes service account for backtest runtime jobs"
    )
    BACKTEST_RUNTIME_K8S_IMAGE_PULL_POLICY: str = Field(
        default="IfNotPresent",
        description="Image pull policy for Kubernetes backtest runtime jobs"
    )
    BACKTEST_RUNTIME_K8S_IMAGE_PULL_SECRETS: str | List[str] = Field(
        default=[],
        description="Image pull secrets for Kubernetes backtest runtime jobs"
    )
    BACKTEST_RUNTIME_K8S_JOB_TTL_SECONDS: int = Field(
        default=3600,
        description="TTL after Kubernetes backtest job completion"
    )
    BACKTEST_RUNTIME_K8S_ACTIVE_DEADLINE_SECONDS: int = Field(
        default=21600,
        description="Active deadline for Kubernetes backtest jobs"
    )
    BACKTEST_RUNTIME_ENV_PASSTHROUGH: str | List[str] = Field(
        default=[
            "DATABASE_URL",
            "REDIS_URL",
            "DATA_PLANE_URL",
            "SIGNAL_GENERATOR_URL",
            "BACKTEST_KAFKA_BOOTSTRAP_SERVERS",
            "BACKTEST_KAFKA_SIGNAL_TOPIC",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "OPENAI_MODEL",
            "OPENAI_TEMPERATURE",
            "LLM_PROVIDER",
            "OPENROUTER_API_KEY",
            "OPENROUTER_BASE_URL",
            "OPENROUTER_HTTP_REFERER",
            "OPENROUTER_APP_NAME",
            "LANGFUSE_SECRET_KEY",
            "LANGFUSE_PUBLIC_KEY",
            "LANGFUSE_BASE_URL",
            "LANGFUSE_ENABLED",
            "FINNHUB_API_KEY",
            "TIINGO_API_KEY",
            "ALPACA_API_KEY",
            "ALPACA_SECRET_KEY",
            "ALPACA_BASE_URL",
            "OANDA_API_KEY",
            "OANDA_ACCOUNT_TYPE",
            "OANDA_ACCOUNT_ID",
            "ENV",
            "ENVIRONMENT",
            "LOG_LEVEL",
        ],
        description="Environment variables forwarded into ephemeral backtest runtime containers"
    )
    BACKTEST_RUNTIME_EMBED_SIGNAL_GENERATOR: bool = Field(
        default=True,
        description="Run a sandbox-local signal-generator replay API inside the backtest runtime"
    )
    BACKTEST_RUNTIME_SIGNAL_GENERATOR_PORT: int = Field(
        default=18007,
        description="Port used by the sandbox-local signal-generator replay API"
    )
    
    # PDF Reports
    PDF_STORAGE_PATH: str = Field(
        default="/app/data/reports",
        description="Path to store generated PDF reports"
    )
    
    # Broker (Alpaca)
    ALPACA_API_KEY: Optional[str] = Field(default=None, description="Alpaca API key")
    ALPACA_SECRET_KEY: Optional[str] = Field(default=None, description="Alpaca secret key")
    ALPACA_BASE_URL: str = Field(
        default="https://paper-api.alpaca.markets",
        description="Alpaca base URL (paper or live)"
    )
    
    # AWS (for production)
    AWS_REGION: str = Field(default="us-east-1", description="AWS region")
    AWS_ACCESS_KEY_ID: Optional[str] = Field(default=None, description="AWS access key ID")
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(default=None, description="AWS secret access key")
    
    # Email (SES)
    SES_FROM_EMAIL: Optional[str] = Field(default=None, description="SES from email address")
    
    # Twilio (SMS Approval)
    TWILIO_ACCOUNT_SID: Optional[str] = Field(default=None, description="Twilio Account SID")
    TWILIO_AUTH_TOKEN: Optional[str] = Field(default=None, description="Twilio Auth Token")
    TWILIO_FROM_NUMBER: Optional[str] = Field(default=None, description="Twilio sender phone number (E.164)")
    APPROVAL_BASE_URL: Optional[str] = Field(
        default=None,
        description="Base URL for approval SMS links. Auto-derived from ALLOWED_ORIGINS if not set."
    )

    @validator("APPROVAL_BASE_URL", always=True)
    def derive_approval_base_url(cls, v, values):
        """Default to first ALLOWED_ORIGINS entry (the frontend URL)."""
        if v:
            return v.rstrip("/")
        origins = values.get("ALLOWED_ORIGINS", [])
        if origins:
            return origins[0].rstrip("/")
        return "http://localhost:4200"

    # Apple Push Notification Service (APNs)
    APNS_KEY_ID: str = Field(default="", description="APNs auth key ID from Apple Developer portal")
    APNS_TEAM_ID: str = Field(default="", description="Apple Developer Team ID")
    APNS_BUNDLE_ID: str = Field(
        default="com.clovercharts.app",
        description="iOS app bundle identifier"
    )
    APNS_AUTH_KEY_PATH: str = Field(
        default="./AuthKey.p8",
        description="Path to APNs auth key (.p8 file)"
    )

    # Subscription & Billing
    ENFORCE_SUBSCRIPTION_LIMITS: bool = Field(
        default=False,
        description="Enforce subscription tier limits (set to True in production)"
    )
    DEFAULT_SUBSCRIPTION_TIER: str = Field(
        default="enterprise",
        description="Default subscription tier for all users in dev mode"
    )
    
    @validator("ALLOWED_ORIGINS", pre=True)
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @validator("BACKTEST_RUNTIME_ENV_PASSTHROUGH", pre=True)
    def parse_backtest_runtime_env_passthrough(cls, v):
        """Parse runtime env passthrough from a comma-separated string or list."""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @validator("BACKTEST_RUNTIME_K8S_IMAGE_PULL_SECRETS", pre=True)
    def parse_backtest_runtime_k8s_pull_secrets(cls, v):
        """Parse Kubernetes image pull secrets from a comma-separated string or list."""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"


# Global settings instance
settings = Settings()
