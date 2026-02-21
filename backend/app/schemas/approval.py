"""
Pydantic schemas for Trade Approval flow.
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel, Field


class ApprovalRequest(BaseModel):
    """Pre-trade report sent to the user for approval."""
    execution_id: UUID
    pipeline_name: str
    symbol: str
    action: str  # BUY / SELL
    entry_price: Optional[float] = None
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    position_size: Optional[float] = None
    confidence: Optional[float] = None
    agent_reports: Optional[Dict[str, Any]] = None
    expires_at: datetime


class ApprovalResponse(BaseModel):
    """User's approval decision."""
    decision: str = Field(..., pattern="^(approve|reject)$")
    reason: Optional[str] = None


class ApprovalTokenResponse(BaseModel):
    """Response for SMS-link token-based approval page."""
    execution_id: UUID
    pipeline_name: str
    symbol: str
    action: str
    entry_price: Optional[float] = None
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    position_size: Optional[float] = None
    confidence: Optional[float] = None
    agent_reports: Optional[Dict[str, Any]] = None
    expires_at: datetime
    is_expired: bool = False
    approval_status: str  # pending, approved, rejected, timed_out
