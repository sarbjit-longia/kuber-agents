"""
Pydantic schemas for User model.
"""
from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    """Base user schema with common fields."""
    email: EmailStr
    full_name: Optional[str] = None


class UserCreate(UserBase):
    """Schema for creating a new user."""
    password: str = Field(..., min_length=8, max_length=72)


class UserUpdate(BaseModel):
    """Schema for updating a user."""
    full_name: Optional[str] = None
    password: Optional[str] = Field(None, min_length=8, max_length=72)


class UserInDB(UserBase):
    """Schema for user in database."""
    id: UUID
    is_active: bool
    is_superuser: bool
    subscription_tier: str
    max_active_pipelines: int
    subscription_expires_at: Optional[datetime] = None
    telegram_enabled: bool = False
    telegram_chat_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class User(UserInDB):
    """Schema for user response."""
    pass


class UserSubscriptionInfo(BaseModel):
    """Detailed subscription information for a user."""
    tier: str
    max_active_pipelines: int
    current_active_pipelines: int
    total_pipelines: int
    pipelines_remaining: int
    available_signals: List[str]
    subscription_expires_at: Optional[str] = None
    is_limit_enforced: bool


class UserLogin(BaseModel):
    """Schema for user login."""
    email: EmailStr
    password: str


class Token(BaseModel):
    """Schema for JWT token response."""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Schema for JWT token payload."""
    user_id: Optional[UUID] = None
    email: Optional[str] = None


class TelegramConfigUpdate(BaseModel):
    """Schema for updating Telegram configuration."""
    bot_token: str = Field(..., min_length=10, max_length=200, description="Telegram bot token from @BotFather")
    chat_id: str = Field(..., min_length=1, max_length=50, description="Telegram chat ID from @userinfobot")
    enabled: bool = True


class TelegramConfigResponse(BaseModel):
    """Schema for Telegram configuration response."""
    enabled: bool
    chat_id: Optional[str] = None
    is_configured: bool


class TelegramTestRequest(BaseModel):
    """Schema for testing Telegram connection."""
    bot_token: str
    chat_id: str


