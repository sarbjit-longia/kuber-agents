"""
Pydantic schemas for Pipeline model.
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel, Field
from enum import Enum


class TriggerMode(str, Enum):
    """
    Trigger mode for pipeline execution.
    
    - SIGNAL: Pipeline is triggered by external signals (e.g., from signal generators)
    - PERIODIC: Pipeline runs on a fixed schedule (e.g., every 5 minutes)
    """
    SIGNAL = "signal"
    PERIODIC = "periodic"


class PipelineBase(BaseModel):
    """Base pipeline schema with common fields."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    trigger_mode: TriggerMode = Field(default=TriggerMode.PERIODIC)
    scanner_tickers: Optional[List[str]] = Field(default=None, description="Ticker symbols for signal-based pipelines")


class PipelineCreate(PipelineBase):
    """Schema for creating a new pipeline."""
    pass


class PipelineUpdate(BaseModel):
    """Schema for updating a pipeline."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    trigger_mode: Optional[TriggerMode] = None
    scanner_tickers: Optional[List[str]] = None


class PipelineInDB(PipelineBase):
    """Schema for pipeline in database."""
    id: UUID
    user_id: UUID
    is_active: bool
    trigger_mode: TriggerMode
    scanner_tickers: Optional[List[str]]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class Pipeline(PipelineInDB):
    """Schema for pipeline response."""
    pass


class PipelineList(BaseModel):
    """Schema for list of pipelines."""
    pipelines: List[Pipeline]
    total: int

