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
    result: Dict[str, Any]
    error_message: Optional[str] = None
    cost: float
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

