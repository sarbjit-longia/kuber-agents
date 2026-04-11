"""
Circuit Breaker API (TP-029)

Emergency kill-switch endpoints for halting pipelines and closing positions.
These are the fastest user-facing controls for stopping live trading activity.
"""
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.core.deps import get_current_active_user
from app.services.circuit_breaker import (
    halt_all_pipelines,
    halt_pipeline,
    close_all_positions,
    kill_all,
)

router = APIRouter(prefix="/circuit-breaker", tags=["Circuit Breaker"])


@router.post("/kill-all", summary="Halt all pipelines and close all live positions")
async def kill_all_endpoint(
    reason: str = "user_emergency_stop",
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    """
    **Emergency kill-switch.** Halts all active pipelines AND closes all live
    positions in a single atomic call.

    - Deactivates every active pipeline (`is_active = False`)
    - Issues market close orders for every position in MONITORING status
    - Returns a summary of what was halted and closed

    Use when you need to stop all trading activity immediately.
    """
    result = await kill_all(db, current_user.id, reason=reason)
    return result


@router.post("/halt-all", summary="Stop all active pipelines (no position closure)")
async def halt_all_endpoint(
    reason: str = "user_halt",
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    """
    Deactivate all active pipelines.

    Stops the scheduler from triggering new executions but does NOT close
    existing open positions.  Use `kill-all` if you also want positions closed.
    """
    result = await halt_all_pipelines(db, current_user.id, reason=reason)
    return result


@router.post("/close-all-positions", summary="Close all live positions")
async def close_all_endpoint(
    reason: str = "user_close_all",
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    """
    Issue market close orders for all positions currently in MONITORING status.

    Does NOT deactivate pipelines — they will continue triggering new entries.
    Use `kill-all` if you want to stop both existing positions and new entries.
    """
    result = await close_all_positions(db, current_user.id, reason=reason)
    return result


@router.post("/halt-pipeline/{pipeline_id}", summary="Halt a single pipeline")
async def halt_single_pipeline(
    pipeline_id: UUID,
    reason: str = "user_halt",
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    """
    Deactivate a single pipeline by ID.

    The pipeline will stop triggering new executions immediately.
    Open positions from this pipeline are NOT automatically closed.
    """
    found = await halt_pipeline(db, current_user.id, pipeline_id, reason=reason)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline not found or already inactive",
        )
    return {"halted": True, "pipeline_id": str(pipeline_id), "reason": reason}
