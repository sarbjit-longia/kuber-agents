"""
Backtest run model for parity backtesting jobs.
"""
from datetime import datetime
from enum import Enum as PyEnum
import uuid

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum, Integer, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB

from ..database import Base


class BacktestRunStatus(str, PyEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    pipeline_id = Column(UUID(as_uuid=True), ForeignKey("pipelines.id", ondelete="SET NULL"), nullable=True, index=True)
    pipeline_name = Column(String(255), nullable=True)
    status = Column(Enum(BacktestRunStatus), nullable=False, default=BacktestRunStatus.PENDING, index=True)
    config = Column(JSONB, nullable=False, default=dict)
    progress = Column(JSONB, nullable=False, default=dict)
    metrics = Column(JSONB, nullable=True, default=dict)
    equity_curve = Column(JSONB, nullable=True, default=list)
    trades = Column(JSONB, nullable=True, default=list)
    trades_count = Column(Integer, nullable=False, default=0)
    estimated_cost = Column(Float, nullable=True)
    actual_cost = Column(Float, nullable=False, default=0.0)
    failure_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<BacktestRun(id={self.id}, status={self.status}, pipeline_id={self.pipeline_id})>"
