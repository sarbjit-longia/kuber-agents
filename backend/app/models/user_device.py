"""
User Device model for push notification device registration.
"""
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from ..database import Base


class UserDevice(Base):
    """
    User device model for push notification registration.

    Stores device tokens for APNs (iOS) and FCM (Android) push notifications.
    Each device token is unique; re-registering an existing token updates the
    associated user and last_used_at timestamp.

    Attributes:
        id: UUID primary key
        user_id: Foreign key to users table
        device_token: Unique push notification token from the device
        platform: Device platform ("ios" or "android")
        is_active: Whether the device is active for notifications
        created_at: Timestamp of device registration
        last_used_at: Timestamp of last token refresh or re-registration
    """
    __tablename__ = "user_devices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    device_token = Column(String(512), unique=True, nullable=False, index=True)
    platform = Column(String(10), nullable=False)  # "ios" or "android"
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="devices")

    def __repr__(self):
        return f"<UserDevice(id={self.id}, user_id={self.user_id}, platform={self.platform})>"
