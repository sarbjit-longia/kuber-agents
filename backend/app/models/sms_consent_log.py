"""
SMS Consent Log model for audit trail of consent events.
"""
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
import uuid

from ..database import Base


class SmsConsentLog(Base):
    """Audit log for SMS consent opt-in and revocation events."""

    __tablename__ = "sms_consent_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone_number = Column(String(20), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    consent_given = Column(Boolean, nullable=False)
    consent_method = Column(String(50), nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
