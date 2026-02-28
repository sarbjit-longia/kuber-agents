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
    ALLOWED_ORIGINS: List[str] = Field(
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
    JWT_EXPIRATION_MINUTES: int = Field(default=60, description="JWT token expiration in minutes")
    
    # OpenAI
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="OpenAI API key")
    OPENAI_BASE_URL: Optional[str] = Field(
        default=None, 
        description="OpenAI API base URL (use http://host.docker.internal:1234/v1 for LM Studio)"
    )
    OPENAI_MODEL: str = Field(default="gpt-4", description="Default OpenAI model")
    OPENAI_TEMPERATURE: float = Field(default=0.7, description="OpenAI temperature")
    
    # Langfuse (Tracing & Observability)
    LANGFUSE_SECRET_KEY: Optional[str] = Field(default=None, description="Langfuse secret key")
    LANGFUSE_PUBLIC_KEY: Optional[str] = Field(default=None, description="Langfuse public key")
    LANGFUSE_BASE_URL: Optional[str] = Field(
        default="https://cloud.langfuse.com",
        description="Langfuse API base URL"
    )
    LANGFUSE_ENABLED: bool = Field(default=False, description="Enable Langfuse tracing")
    
    # Market Data (Finnhub)
    FINNHUB_API_KEY: Optional[str] = Field(default=None, description="Finnhub API key")
    
    # Data Plane
    DATA_PLANE_URL: str = Field(
        default="http://data-plane:8000",
        description="Data Plane service URL"
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
        default="com.kubertrading.app",
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
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Global settings instance
settings = Settings()

