"""
Execution model for tracking pipeline execution runs.
"""
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Float, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

from ..database import Base


class ExecutionStatus(str, PyEnum):
    """Execution status enum."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"  # When trigger not met or budget exceeded


class Execution(Base):
    """
    Execution model representing a single execution run of a pipeline.
    
    Attributes:
        id: UUID primary key
        pipeline_id: Foreign key to the pipeline being executed
        user_id: Foreign key to the user who owns this execution
        status: Current status of the execution
        symbol: Trading symbol (e.g., "AAPL")
        result: JSONB storing the execution results and agent outputs
        error_message: Error message if execution failed
        cost: Total cost incurred during execution
        started_at: Timestamp when execution started
        completed_at: Timestamp when execution completed
        created_at: Timestamp of execution record creation
    """
    __tablename__ = "executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    pipeline_id = Column(UUID(as_uuid=True), ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(Enum(ExecutionStatus), default=ExecutionStatus.PENDING, nullable=False, index=True)
    symbol = Column(String(20), nullable=True)
    result = Column(JSONB, nullable=True, default=dict)
    error_message = Column(Text, nullable=True)
    cost = Column(Float, default=0.0, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    pipeline = relationship("Pipeline", back_populates="executions")
    user = relationship("User", back_populates="executions")
    cost_tracking = relationship("CostTracking", back_populates="execution")

    def __repr__(self):
        return f"<Execution(id={self.id}, pipeline_id={self.pipeline_id}, status={self.status})>"

