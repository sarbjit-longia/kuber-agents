"""
Pipeline model for storing user-created trading pipelines.
"""
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

from ..database import Base


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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", backref="pipelines")
    executions = relationship("Execution", back_populates="pipeline", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Pipeline(id={self.id}, name={self.name}, user_id={self.user_id})>"

