"""
Pydantic schemas for Pipeline model.
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel, Field
from enum import Enum

from app.schemas.scanner import SignalSubscription


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
    
    # Scanner configuration (for signal-based pipelines)
    scanner_id: Optional[UUID] = Field(None, description="Scanner to use for ticker selection")
    signal_subscriptions: Optional[List[SignalSubscription]] = Field(default=None, description="Signal types to subscribe to")
    
    # DEPRECATED: Kept for backward compatibility
    scanner_tickers: Optional[List[str]] = Field(default=None, description="(Deprecated) Use scanner_id instead")


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
    scanner_id: Optional[UUID] = None
    signal_subscriptions: Optional[List[SignalSubscription]] = None
    scanner_tickers: Optional[List[str]] = None  # Deprecated


class PipelineInDB(PipelineBase):
    """Schema for pipeline in database."""
    id: UUID
    user_id: UUID
    is_active: bool
    trigger_mode: TriggerMode
    scanner_id: Optional[UUID]
    signal_subscriptions: Optional[List[SignalSubscription]]
    scanner_tickers: Optional[List[str]]  # Deprecated
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

