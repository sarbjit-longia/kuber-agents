"""
Structured backtest event model for monitoring and reporting.
"""
from datetime import datetime
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from ..database import Base


class BacktestEvent(Base):
    __tablename__ = "backtest_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("backtest_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pipeline_id = Column(UUID(as_uuid=True), ForeignKey("pipelines.id", ondelete="SET NULL"), nullable=True, index=True)
    execution_id = Column(UUID(as_uuid=True), ForeignKey("executions.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    level = Column(String(16), nullable=False, default="info")
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    symbol = Column(String(32), nullable=True, index=True)
    data = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        return f"<BacktestEvent(id={self.id}, run_id={self.run_id}, event_type={self.event_type})>"
