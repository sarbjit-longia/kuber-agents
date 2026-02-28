"""
Pydantic schemas for user device registration (push notifications).
"""
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class DeviceRegistrationRequest(BaseModel):
    """Schema for registering a device for push notifications."""
    device_token: str = Field(
        ...,
        min_length=10,
        max_length=512,
        description="Push notification device token from APNs or FCM"
    )
    platform: str = Field(
        ...,
        description="Device platform: 'ios' or 'android'"
    )

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, v: str) -> str:
        v = v.lower()
        if v not in ("ios", "android"):
            raise ValueError("platform must be 'ios' or 'android'")
        return v


class DeviceRegistrationResponse(BaseModel):
    """Schema for device registration response."""
    id: UUID
    device_token: str
    platform: str
    is_active: bool
    created_at: datetime
    last_used_at: datetime

    model_config = ConfigDict(from_attributes=True)
