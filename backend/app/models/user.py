"""
User model for authentication and user management.
"""
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Boolean, Integer, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
import enum

from ..database import Base


class SubscriptionTier(str, enum.Enum):
    """
    Subscription tier for user billing.
    
    - FREE: External signals only, 2 active pipelines
    - BASIC: Basic signal bucket, 5 active pipelines ($29/month)
    - PRO: Pro signal bucket, 20 active pipelines ($99/month)
    - ENTERPRISE: All signals, unlimited pipelines ($299/month)
    """
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class User(Base):
    """
    User model representing a registered user in the system.
    
    Attributes:
        id: UUID primary key
        email: User's email address (unique)
        hashed_password: Bcrypt hashed password
        full_name: User's full name
        is_active: Whether the user account is active
        is_superuser: Whether the user has admin privileges
        created_at: Timestamp of account creation
        updated_at: Timestamp of last update
    """
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    
    # Subscription fields
    subscription_tier = Column(
        SQLEnum(
            SubscriptionTier,
            name='subscriptiontier',
            create_type=False,
            values_callable=lambda x: [e.value for e in x]
        ),
        default=SubscriptionTier.FREE,
        nullable=False,
        index=True
    )
    max_active_pipelines = Column(Integer, default=2, nullable=False)
    subscription_expires_at = Column(DateTime, nullable=True)
    
    # Telegram notification fields
    telegram_bot_token = Column(String(200), nullable=True)
    telegram_chat_id = Column(String(50), nullable=True)
    telegram_enabled = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    pipelines = relationship("Pipeline", back_populates="user", cascade="all, delete-orphan")
    executions = relationship("Execution", back_populates="user", cascade="all, delete-orphan")
    cost_tracking = relationship("CostTracking", back_populates="user", cascade="all, delete-orphan")
    budget = relationship("UserBudget", back_populates="user", uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email})>"

