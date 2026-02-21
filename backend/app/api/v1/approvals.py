"""
Approval API Endpoints

Provides both JWT-authenticated (web UI) and token-authenticated (SMS link)
endpoints for trade approval.

JWT-authenticated:
- POST /executions/{id}/approve
- POST /executions/{id}/reject
- GET  /executions/{id}/pre-trade-report

Token-authenticated (no JWT):
- GET  /approvals/{token}
- POST /approvals/{token}/approve
- POST /approvals/{token}/reject
"""
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
import structlog

from app.database import get_db
from app.models.user import User
from app.models.execution import Execution, ExecutionStatus
from app.models.pipeline import Pipeline
from app.schemas.approval import ApprovalResponse, ApprovalTokenResponse
from app.api.dependencies import get_current_user

logger = structlog.get_logger()

# ──────────────────────────────────────────────────────────────────────────────
# JWT-authenticated endpoints (used by web UI)
# These are mounted under /executions prefix by the executions router
# ──────────────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/executions", tags=["Approvals"])


@router.post("/{execution_id}/approve")
async def approve_execution(
    execution_id: UUID,
    body: ApprovalResponse = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve a trade execution (JWT-authenticated)."""
    result = await db.execute(
        select(Execution).where(
            Execution.id == execution_id,
            Execution.user_id == current_user.id,
        )
    )
    execution = result.scalar_one_or_none()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    if execution.status != ExecutionStatus.AWAITING_APPROVAL:
        raise HTTPException(
            status_code=400,
            detail=f"Execution is not awaiting approval (status: {execution.status.value})",
        )
    if execution.approval_status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Approval already resolved (status: {execution.approval_status})",
        )

    # Check expiry
    if execution.approval_expires_at and datetime.utcnow() > execution.approval_expires_at:
        raise HTTPException(status_code=400, detail="Approval has expired")

    execution.approval_status = "approved"
    execution.approval_responded_at = datetime.utcnow()
    execution.version += 1
    await db.commit()

    # Trigger resume task
    from app.orchestration.tasks.approval import resume_approved_execution
    resume_approved_execution.delay(str(execution_id))

    logger.info("execution_approved_via_web", execution_id=str(execution_id))
    return {"status": "approved", "execution_id": str(execution_id)}


@router.post("/{execution_id}/reject")
async def reject_execution(
    execution_id: UUID,
    body: ApprovalResponse = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reject a trade execution (JWT-authenticated)."""
    result = await db.execute(
        select(Execution).where(
            Execution.id == execution_id,
            Execution.user_id == current_user.id,
        )
    )
    execution = result.scalar_one_or_none()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    if execution.status != ExecutionStatus.AWAITING_APPROVAL:
        raise HTTPException(
            status_code=400,
            detail=f"Execution is not awaiting approval (status: {execution.status.value})",
        )
    if execution.approval_status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Approval already resolved (status: {execution.approval_status})",
        )

    reason = body.reason if body else None
    execution.approval_status = "rejected"
    execution.approval_responded_at = datetime.utcnow()
    execution.status = ExecutionStatus.COMPLETED
    execution.completed_at = datetime.utcnow()

    # Update result
    exec_result = execution.result or {}
    exec_result["trade_outcome"] = "rejected"
    exec_result["exit_reason"] = reason or "User rejected trade"
    execution.result = exec_result
    flag_modified(execution, "result")

    # Mark trade manager as skipped
    agent_states = execution.agent_states or []
    for i, ast in enumerate(agent_states):
        if ast.get("agent_type") == "trade_manager_agent":
            agent_states[i]["status"] = "skipped"
            agent_states[i]["completed_at"] = datetime.utcnow().isoformat()
            agent_states[i]["error"] = reason or "User rejected trade"
            break
    execution.agent_states = agent_states
    flag_modified(execution, "agent_states")

    execution.version += 1
    await db.commit()

    logger.info("execution_rejected_via_web", execution_id=str(execution_id), reason=reason)
    return {"status": "rejected", "execution_id": str(execution_id)}


@router.get("/{execution_id}/pre-trade-report")
async def get_pre_trade_report(
    execution_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the pre-trade report for an execution awaiting approval."""
    result = await db.execute(
        select(Execution).where(
            Execution.id == execution_id,
            Execution.user_id == current_user.id,
        )
    )
    execution = result.scalar_one_or_none()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    # Build report from stored results
    report = {
        "execution_id": str(execution.id),
        "symbol": execution.symbol,
        "status": execution.status.value,
        "approval_status": execution.approval_status,
        "approval_expires_at": execution.approval_expires_at.isoformat() if execution.approval_expires_at else None,
        "result": execution.result,
        "reports": execution.reports,
        "agent_states": execution.agent_states,
    }

    return report


# ──────────────────────────────────────────────────────────────────────────────
# Token-authenticated endpoints (used by SMS approval link)
# These do NOT require JWT — authentication is via the unique token
# ──────────────────────────────────────────────────────────────────────────────

token_router = APIRouter(prefix="/approvals", tags=["Approvals (Token)"])


@token_router.get("/{token}")
async def get_approval_by_token(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Get approval details by token (for SMS link page)."""
    result = await db.execute(
        select(Execution).where(Execution.approval_token == token)
    )
    execution = result.scalar_one_or_none()
    if not execution:
        raise HTTPException(status_code=404, detail="Approval not found or invalid token")

    # Get pipeline name
    pipeline_result = await db.execute(
        select(Pipeline.name).where(Pipeline.id == execution.pipeline_id)
    )
    pipeline_name = pipeline_result.scalar_one_or_none() or "Unknown Pipeline"

    is_expired = (
        execution.approval_expires_at is not None
        and datetime.utcnow() > execution.approval_expires_at
    )

    # Extract trade details from result
    strategy = (execution.result or {}).get("strategy", {})
    risk = (execution.result or {}).get("risk_assessment", {})

    return ApprovalTokenResponse(
        execution_id=execution.id,
        pipeline_name=pipeline_name,
        symbol=execution.symbol or "N/A",
        action=strategy.get("action", "N/A") if isinstance(strategy, dict) else "N/A",
        entry_price=strategy.get("entry_price") if isinstance(strategy, dict) else None,
        take_profit=strategy.get("take_profit") if isinstance(strategy, dict) else None,
        stop_loss=strategy.get("stop_loss") if isinstance(strategy, dict) else None,
        position_size=risk.get("position_size") if isinstance(risk, dict) else None,
        confidence=strategy.get("confidence") if isinstance(strategy, dict) else None,
        agent_reports=execution.reports,
        expires_at=execution.approval_expires_at or datetime.utcnow(),
        is_expired=is_expired,
        approval_status=execution.approval_status or "unknown",
    )


@token_router.post("/{token}/approve")
async def approve_by_token(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Approve a trade via token (SMS link)."""
    result = await db.execute(
        select(Execution).where(Execution.approval_token == token)
    )
    execution = result.scalar_one_or_none()
    if not execution:
        raise HTTPException(status_code=404, detail="Approval not found or invalid token")

    if execution.status != ExecutionStatus.AWAITING_APPROVAL:
        raise HTTPException(status_code=400, detail="Execution is not awaiting approval")
    if execution.approval_status != "pending":
        raise HTTPException(status_code=400, detail=f"Already resolved: {execution.approval_status}")
    if execution.approval_expires_at and datetime.utcnow() > execution.approval_expires_at:
        raise HTTPException(status_code=400, detail="Approval has expired")

    execution.approval_status = "approved"
    execution.approval_responded_at = datetime.utcnow()
    execution.version += 1
    await db.commit()

    from app.orchestration.tasks.approval import resume_approved_execution
    resume_approved_execution.delay(str(execution.id))

    logger.info("execution_approved_via_token", execution_id=str(execution.id))
    return {"status": "approved", "execution_id": str(execution.id)}


@token_router.post("/{token}/reject")
async def reject_by_token(
    token: str,
    body: ApprovalResponse = None,
    db: AsyncSession = Depends(get_db),
):
    """Reject a trade via token (SMS link)."""
    result = await db.execute(
        select(Execution).where(Execution.approval_token == token)
    )
    execution = result.scalar_one_or_none()
    if not execution:
        raise HTTPException(status_code=404, detail="Approval not found or invalid token")

    if execution.status != ExecutionStatus.AWAITING_APPROVAL:
        raise HTTPException(status_code=400, detail="Execution is not awaiting approval")
    if execution.approval_status != "pending":
        raise HTTPException(status_code=400, detail=f"Already resolved: {execution.approval_status}")

    reason = body.reason if body else None
    execution.approval_status = "rejected"
    execution.approval_responded_at = datetime.utcnow()
    execution.status = ExecutionStatus.COMPLETED
    execution.completed_at = datetime.utcnow()

    exec_result = execution.result or {}
    exec_result["trade_outcome"] = "rejected"
    exec_result["exit_reason"] = reason or "User rejected trade (via SMS)"
    execution.result = exec_result
    flag_modified(execution, "result")

    agent_states = execution.agent_states or []
    for i, ast in enumerate(agent_states):
        if ast.get("agent_type") == "trade_manager_agent":
            agent_states[i]["status"] = "skipped"
            agent_states[i]["completed_at"] = datetime.utcnow().isoformat()
            agent_states[i]["error"] = reason or "User rejected trade (via SMS)"
            break
    execution.agent_states = agent_states
    flag_modified(execution, "agent_states")

    execution.version += 1
    await db.commit()

    logger.info("execution_rejected_via_token", execution_id=str(execution.id), reason=reason)
    return {"status": "rejected", "execution_id": str(execution.id)}
