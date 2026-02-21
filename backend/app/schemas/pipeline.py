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
    
    # Notification settings
    notification_enabled: bool = Field(default=False, description="Enable Telegram notifications for this pipeline")
    notification_events: Optional[List[str]] = Field(
        default=None,
        description="Events to notify: trade_executed, position_closed, pipeline_failed, risk_rejected"
    )

    # Trade approval settings
    require_approval: bool = Field(default=False, description="Require manual approval before trades")
    approval_modes: Optional[List[str]] = Field(default=None, description="Modes requiring approval, e.g. ['live', 'paper']")
    approval_timeout_minutes: int = Field(default=15, ge=1, le=1440, description="Minutes before auto-reject")
    approval_channels: Optional[List[str]] = Field(default=None, description="Notification channels: ['web', 'sms']")
    approval_phone: Optional[str] = Field(default=None, max_length=20, description="E.164 phone number for SMS approval")


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
    notification_enabled: Optional[bool] = None
    notification_events: Optional[List[str]] = None
    require_approval: Optional[bool] = None
    approval_modes: Optional[List[str]] = None
    approval_timeout_minutes: Optional[int] = None
    approval_channels: Optional[List[str]] = None
    approval_phone: Optional[str] = None


class PipelineInDB(PipelineBase):
    """Schema for pipeline in database."""
    id: UUID
    user_id: UUID
    is_active: bool
    trigger_mode: TriggerMode
    scanner_id: Optional[UUID]
    signal_subscriptions: Optional[List[SignalSubscription]]
    scanner_tickers: Optional[List[str]]  # Deprecated
    notification_enabled: bool
    notification_events: Optional[List[str]]
    require_approval: bool
    approval_modes: Optional[List[str]]
    approval_timeout_minutes: int
    approval_channels: Optional[List[str]]
    approval_phone: Optional[str]
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

