"""
Pydantic schemas for strategies.
"""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


StrategyVisibility = Literal["private", "public"]
StrategyPublicationStatus = Literal["draft", "pending_review", "published", "rejected"]


class StrategyBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    summary: Optional[str] = None
    visibility: StrategyVisibility = "private"
    category: Optional[str] = None
    style: Optional[str] = None
    difficulty: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    markets: List[str] = Field(default_factory=list)
    timeframes: List[str] = Field(default_factory=list)
    risk_notes: Optional[str] = None
    markdown_content: Optional[str] = None
    body_markdown: Optional[str] = None
    normalized_spec: Optional[Dict[str, Any]] = None
    source_pipeline_id: Optional[UUID] = None


class StrategyCreate(StrategyBase):
    pass


class StrategyUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    summary: Optional[str] = None
    visibility: Optional[StrategyVisibility] = None
    category: Optional[str] = None
    style: Optional[str] = None
    difficulty: Optional[str] = None
    tags: Optional[List[str]] = None
    markets: Optional[List[str]] = None
    timeframes: Optional[List[str]] = None
    risk_notes: Optional[str] = None
    markdown_content: Optional[str] = None
    body_markdown: Optional[str] = None
    normalized_spec: Optional[Dict[str, Any]] = None
    source_pipeline_id: Optional[UUID] = None


class StrategyReviewRequest(BaseModel):
    approved: bool
    review_notes: Optional[str] = None


class StrategyVoteResponse(BaseModel):
    vote_count: int
    has_voted: bool


class StrategyPipelineCreateResponse(BaseModel):
    pipeline_id: UUID


class StrategyRead(BaseModel):
    id: UUID
    user_id: UUID
    source_pipeline_id: Optional[UUID]
    title: str
    slug: str
    summary: Optional[str]
    visibility: StrategyVisibility
    publication_status: StrategyPublicationStatus
    category: Optional[str]
    style: Optional[str]
    difficulty: Optional[str]
    tags: List[str]
    markets: List[str]
    timeframes: List[str]
    risk_notes: Optional[str]
    markdown_content: str
    body_markdown: str
    frontmatter: Dict[str, Any]
    normalized_spec: Dict[str, Any]
    current_version: int
    published_version: int
    use_count: int
    vote_count: int
    review_notes: Optional[str]
    submitted_at: Optional[datetime]
    published_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    has_voted: bool = False
    is_runnable: bool = False

    class Config:
        from_attributes = True


class StrategyListResponse(BaseModel):
    strategies: List[StrategyRead]
    total: int

