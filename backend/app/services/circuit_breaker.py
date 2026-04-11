"""
Kill-Switches and Emergency Circuit Breakers (TP-029)

Provides user-level and platform-level emergency controls:
  - Close all live positions immediately
  - Halt all active pipelines (stop new executions)
  - Halt a single pipeline

These are the fastest path to stopping live trading activity.
All operations are best-effort: broker failures are logged but
do not prevent the pipeline halt from completing.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution import Execution, ExecutionStatus
from app.models.pipeline import Pipeline

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def halt_all_pipelines(
    db: AsyncSession,
    user_id: UUID,
    reason: str = "emergency_halt",
) -> Dict[str, Any]:
    """
    Deactivate all active pipelines for a user.

    Sets is_active=False on every pipeline; the periodic scheduler will
    stop triggering them.  Does NOT close open positions — use
    close_all_positions for that.

    Returns a summary dict.
    """
    result = await db.execute(
        select(Pipeline).where(
            Pipeline.user_id == user_id,
            Pipeline.is_active.is_(True),
        )
    )
    pipelines = result.scalars().all()

    halted = []
    for p in pipelines:
        p.is_active = False
        p.updated_at = datetime.utcnow()
        halted.append(str(p.id))
        logger.warning(
            "pipeline_halted_by_circuit_breaker",
            pipeline_id=str(p.id),
            user_id=str(user_id),
            reason=reason,
        )

    await db.commit()
    return {"halted_pipelines": halted, "count": len(halted), "reason": reason}


async def halt_pipeline(
    db: AsyncSession,
    user_id: UUID,
    pipeline_id: UUID,
    reason: str = "manual_halt",
) -> bool:
    """
    Deactivate a single pipeline.  Returns True if found and halted.
    """
    result = await db.execute(
        select(Pipeline).where(
            Pipeline.id == pipeline_id,
            Pipeline.user_id == user_id,
        )
    )
    pipeline = result.scalar_one_or_none()
    if not pipeline:
        return False

    pipeline.is_active = False
    pipeline.updated_at = datetime.utcnow()
    await db.commit()
    logger.warning(
        "pipeline_halted_by_circuit_breaker",
        pipeline_id=str(pipeline_id),
        user_id=str(user_id),
        reason=reason,
    )
    return True


async def close_all_positions(
    db: AsyncSession,
    user_id: UUID,
    reason: str = "emergency_close",
) -> Dict[str, Any]:
    """
    Close all live positions for a user by issuing market close orders.

    Iterates over all MONITORING executions, extracts broker config from
    pipeline_state, and calls the broker close_position API.

    Returns a summary of close attempts.
    """
    result = await db.execute(
        select(Execution).where(
            Execution.user_id == user_id,
            Execution.status == ExecutionStatus.MONITORING,
        )
    )
    monitoring = result.scalars().all()

    closed: List[str] = []
    failed: List[Dict[str, str]] = []

    for execution in monitoring:
        try:
            closed_ok = await _close_execution_position(execution, reason)
            if closed_ok:
                execution.status = ExecutionStatus.COMPLETED
                closed.append(str(execution.id))
            else:
                failed.append({"execution_id": str(execution.id), "reason": "close_failed"})
        except Exception as exc:
            logger.error(
                "circuit_breaker_close_failed",
                execution_id=str(execution.id),
                error=str(exc),
            )
            failed.append({"execution_id": str(execution.id), "reason": str(exc)})

    await db.commit()
    return {
        "closed": closed,
        "failed": failed,
        "total_monitoring": len(monitoring),
        "reason": reason,
    }


async def kill_all(
    db: AsyncSession,
    user_id: UUID,
    reason: str = "emergency_kill_all",
) -> Dict[str, Any]:
    """
    Atomic kill-all: halt all pipelines AND close all positions.
    """
    halt_result  = await halt_all_pipelines(db, user_id, reason=reason)
    close_result = await close_all_positions(db, user_id, reason=reason)
    return {"halt": halt_result, "close": close_result}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _close_execution_position(execution: Execution, reason: str) -> bool:
    """
    Extract broker config from execution pipeline_state and close the position.

    Returns True if the close order was placed successfully.
    """
    state_dict = execution.pipeline_state or {}

    # Find broker tool config — stored in agent config or top-level broker_tool
    broker_tool = _extract_broker_tool(state_dict)
    if not broker_tool:
        logger.warning(
            "circuit_breaker_no_broker_tool",
            execution_id=str(execution.id),
        )
        return False

    symbol = execution.symbol or state_dict.get("symbol")
    if not symbol:
        return False

    try:
        from app.services.brokers.factory import broker_factory
        broker = broker_factory.from_tool_config(broker_tool)
        result = broker.close_position(symbol)
        success = bool(result.get("success", False))
        logger.info(
            "circuit_breaker_position_closed",
            execution_id=str(execution.id),
            symbol=symbol,
            success=success,
            reason=reason,
        )
        return success
    except Exception as exc:
        logger.error(
            "circuit_breaker_broker_error",
            execution_id=str(execution.id),
            symbol=symbol,
            error=str(exc),
        )
        return False


def _extract_broker_tool(state_dict: dict) -> Optional[dict]:
    """Pull the broker_tool config from a serialised PipelineState dict."""
    # Top-level broker_tool (guided builder)
    broker_tool = state_dict.get("broker_tool")
    if broker_tool:
        return broker_tool

    # Scan agent execution states / nested configs
    for agent_state in state_dict.get("agent_execution_states", []):
        cfg = agent_state.get("config", {})
        for tool in cfg.get("tools", []):
            if tool.get("tool_type", "").endswith("_broker"):
                return tool

    return None
