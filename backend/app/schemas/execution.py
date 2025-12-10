"""
Pydantic schemas for Execution model.
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel

from app.models.execution import ExecutionStatus


class ExecutionBase(BaseModel):
    """Base execution schema with common fields."""
    symbol: Optional[str] = None


class ExecutionCreate(ExecutionBase):
    """Schema for creating a new execution."""
    pipeline_id: UUID
    mode: Optional[str] = "paper"  # "live", "paper", "simulation", "validation"


class ExecutionUpdate(BaseModel):
    """Schema for updating an execution."""
    status: Optional[ExecutionStatus] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    cost: Optional[float] = None


class ExecutionInDB(ExecutionBase):
    """Schema for execution in database."""
    id: UUID
    pipeline_id: UUID
    user_id: UUID
    status: ExecutionStatus
    mode: str
    result: Dict[str, Any]
    error_message: Optional[str] = None
    cost: float
    logs: Optional[List[Dict[str, Any]]] = None
    agent_states: Optional[List[Dict[str, Any]]] = None
    reports: Optional[Dict[str, Any]] = None
    cost_breakdown: Optional[Dict[str, Any]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class Execution(ExecutionInDB):
    """Schema for execution response."""
    pass


class ExecutionList(BaseModel):
    """Schema for list of executions."""
    executions: List[Execution]
    total: int


class ExecutionSummary(BaseModel):
    """Schema for execution summary (list view)."""
    id: UUID
    pipeline_id: UUID
    pipeline_name: str
    status: ExecutionStatus
    mode: str
    symbol: Optional[str] = None
    trigger_mode: Optional[str] = None  # "signal" or "periodic"
    scanner_name: Optional[str] = None  # Scanner name for signal-based pipelines
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    total_cost: float
    agent_count: int
    agents_completed: int
    error_message: Optional[str] = None


class ExecutionStats(BaseModel):
    """Schema for execution statistics."""
    total_executions: int
    running_executions: int
    completed_executions: int
    failed_executions: int
    total_cost: float
    avg_duration_seconds: float
    success_rate: float

