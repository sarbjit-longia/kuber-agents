"""
Pipeline model for storing user-created trading pipelines.
"""
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid
import enum

from ..database import Base


class TriggerMode(str, enum.Enum):
    """
    Trigger mode for pipeline execution.
    
    - SIGNAL: Pipeline is triggered by external signals (e.g., from signal generators)
    - PERIODIC: Pipeline runs on a fixed schedule (e.g., every 5 minutes)
    """
    SIGNAL = "signal"
    PERIODIC = "periodic"


class Pipeline(Base):
    """
    Pipeline model representing a trading pipeline configuration.
    
    A pipeline is a visual workflow of connected agents that execute
    a trading strategy.
    
    Attributes:
        id: UUID primary key
        user_id: Foreign key to the user who owns this pipeline
        name: Pipeline name
        description: Pipeline description
        config: JSONB storing the pipeline configuration (nodes, edges, etc.)
        is_active: Whether the pipeline is currently active/running
        trigger_mode: How the pipeline is triggered (signal or periodic)
        scanner_tickers: List of ticker symbols for signal-based pipelines
        created_at: Timestamp of pipeline creation
        updated_at: Timestamp of last update
    """
    __tablename__ = "pipelines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    config = Column(JSONB, nullable=False, default=dict)
    is_active = Column(Boolean, default=False, nullable=False)
    trigger_mode = Column(
        SQLEnum(
            TriggerMode,
            name='triggermode',
            create_type=False,
            values_callable=lambda x: [e.value for e in x]
        ),
        default=TriggerMode.PERIODIC,
        nullable=False,
        index=True
    )
    
    # Scanner configuration (signal-based pipelines)
    scanner_id = Column(UUID(as_uuid=True), ForeignKey("scanners.id"), nullable=True, index=True)
    signal_subscriptions = Column(JSONB, nullable=True, default=list)
    # Example signal_subscriptions:
    # [
    #   {"signal_type": "golden_cross", "min_confidence": 80},
    #   {"signal_type": "news_sentiment", "min_confidence": 70}
    # ]
    
    # DEPRECATED: Use scanner_id instead
    scanner_tickers = Column(JSONB, nullable=True, default=list)  # Kept for backward compatibility
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="pipelines")
    scanner = relationship("Scanner", foreign_keys=[scanner_id])
    executions = relationship("Execution", back_populates="pipeline", cascade="all, delete-orphan")
    cost_tracking = relationship("CostTracking", back_populates="pipeline")

    def __repr__(self):
        return f"<Pipeline(id={self.id}, name={self.name}, user_id={self.user_id})>"

