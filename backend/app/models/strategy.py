"""
Strategy marketplace models.
"""
from datetime import datetime
import uuid

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB

from ..database import Base


class Strategy(Base):
    """User-authored strategy document plus normalized pipeline snapshot."""

    __tablename__ = "strategies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source_pipeline_id = Column(UUID(as_uuid=True), ForeignKey("pipelines.id", ondelete="SET NULL"), nullable=True, index=True)

    title = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False, index=True)
    summary = Column(Text, nullable=True)
    visibility = Column(String(20), nullable=False, default="private", index=True)
    publication_status = Column(String(20), nullable=False, default="draft", index=True)
    category = Column(String(64), nullable=True, index=True)
    style = Column(String(64), nullable=True, index=True)
    difficulty = Column(String(32), nullable=True)

    tags = Column(JSONB, nullable=False, default=list)
    markets = Column(JSONB, nullable=False, default=list)
    timeframes = Column(JSONB, nullable=False, default=list)
    risk_notes = Column(Text, nullable=True)

    markdown_content = Column(Text, nullable=False, default="")
    body_markdown = Column(Text, nullable=False, default="")
    frontmatter = Column(JSONB, nullable=False, default=dict)
    normalized_spec = Column(JSONB, nullable=False, default=dict)

    current_version = Column(Integer, nullable=False, default=1)
    published_version = Column(Integer, nullable=False, default=0)
    published_markdown_content = Column(Text, nullable=True)
    published_frontmatter = Column(JSONB, nullable=True)
    published_normalized_spec = Column(JSONB, nullable=True)

    use_count = Column(Integer, nullable=False, default=0)
    vote_count = Column(Integer, nullable=False, default=0)
    review_notes = Column(Text, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class StrategyVote(Base):
    """One vote per user per strategy."""

    __tablename__ = "strategy_votes"
    __table_args__ = (
        UniqueConstraint("strategy_id", "user_id", name="uq_strategy_votes_strategy_user"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    strategy_id = Column(UUID(as_uuid=True), ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
