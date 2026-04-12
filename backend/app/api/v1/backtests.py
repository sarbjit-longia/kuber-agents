"""
Backtesting API endpoints.
"""
import os
from typing import Annotated
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.backtesting.snapshot import build_backtest_runtime_snapshot
from app.core.deps import get_current_active_user
from app.database import get_db
from app.models.backtest_run import BacktestRun, BacktestRunStatus
from app.models.pipeline import Pipeline
from app.models.user import User
from app.backtesting.runtime_launcher import get_backtest_runtime_launcher
from app.schemas.backtest import (
    BacktestCreate,
    BacktestRunList,
    BacktestRunResult,
    BacktestRunSummary,
    BacktestStartResponse,
)
from app.orchestration.tasks.launch_backtest_runtime import launch_backtest_runtime

router = APIRouter(prefix="/backtests", tags=["backtests"])

ACTIVE_BACKTEST_STATUSES = (
    BacktestRunStatus.PENDING,
    BacktestRunStatus.RUNNING,
)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _estimate_cost_usd(symbol_count: int, start_date, end_date) -> float:
    days = max((end_date - start_date).days, 1)
    # Heuristic from proposal doc: ~100 executions / symbol / month at mid-case cost.
    est_executions = symbol_count * max(1, round(days / 30 * 100))
    return round(est_executions * 0.075, 2)


def _snapshot_pipeline(pipeline: Pipeline) -> dict:
    return {
        "id": str(pipeline.id),
        "user_id": str(pipeline.user_id),
        "name": pipeline.name,
        "description": pipeline.description,
        "config": pipeline.config or {},
        "trigger_mode": pipeline.trigger_mode.value if pipeline.trigger_mode else None,
        "scanner_id": str(pipeline.scanner_id) if pipeline.scanner_id else None,
        "signal_subscriptions": pipeline.signal_subscriptions or [],
        "scanner_tickers": pipeline.scanner_tickers or [],
        "require_approval": pipeline.require_approval,
        "approval_modes": pipeline.approval_modes or [],
        "schedule_enabled": pipeline.schedule_enabled,
        "schedule_start_time": pipeline.schedule_start_time,
        "schedule_end_time": pipeline.schedule_end_time,
        "schedule_days": pipeline.schedule_days or [],
        "snapshot_created_at": datetime.utcnow().isoformat(),
    }


@router.post("", response_model=BacktestStartResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_backtest(
    payload: BacktestCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Pipeline).where(Pipeline.id == payload.pipeline_id)
    )
    pipeline = result.scalar_one_or_none()
    if not pipeline:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")
    if pipeline.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Pipeline does not belong to user")

    per_user_limit = max(1, _env_int("BACKTEST_MAX_ACTIVE_RUNS_PER_USER", 2))
    per_pipeline_limit = max(1, _env_int("BACKTEST_MAX_ACTIVE_RUNS_PER_PIPELINE", 1))
    global_limit = max(1, _env_int("BACKTEST_MAX_ACTIVE_RUNS_GLOBAL", 100))

    active_for_user = await db.scalar(
        select(func.count())
        .select_from(BacktestRun)
        .where(
            BacktestRun.user_id == current_user.id,
            BacktestRun.status.in_(ACTIVE_BACKTEST_STATUSES),
        )
    )
    if (active_for_user or 0) >= per_user_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"User backtest concurrency limit reached ({per_user_limit} active runs)",
        )

    active_for_pipeline = await db.scalar(
        select(func.count())
        .select_from(BacktestRun)
        .where(
            BacktestRun.pipeline_id == pipeline.id,
            BacktestRun.status.in_(ACTIVE_BACKTEST_STATUSES),
        )
    )
    if (active_for_pipeline or 0) >= per_pipeline_limit:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This pipeline already has an active backtest run",
        )

    global_active = await db.scalar(
        select(func.count())
        .select_from(BacktestRun)
        .where(BacktestRun.status.in_(ACTIVE_BACKTEST_STATUSES))
    )
    if (global_active or 0) >= global_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Backtest capacity is currently full, try again shortly",
        )

    estimated_cost = _estimate_cost_usd(len(payload.symbols), payload.start_date, payload.end_date)
    if payload.max_cost_usd is not None and estimated_cost > payload.max_cost_usd:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Estimated run cost ${estimated_cost:.2f} exceeds max_cost_usd ${payload.max_cost_usd:.2f}",
        )

    run_config = payload.model_dump(mode="json")
    run_config["pipeline_snapshot"] = _snapshot_pipeline(pipeline)
    run_config["runtime_snapshot"] = build_backtest_runtime_snapshot(pipeline)
    run_config["runtime"] = {
        "mode": "ephemeral_sandbox",
        "launcher_mode": settings.BACKTEST_RUNTIME_MODE,
        "namespace": settings.BACKTEST_RUNTIME_NAMESPACE,
        "image": settings.BACKTEST_RUNTIME_IMAGE,
    }

    run = BacktestRun(
        user_id=current_user.id,
        pipeline_id=pipeline.id,
        pipeline_name=pipeline.name,
        status=BacktestRunStatus.PENDING,
        config=run_config,
        progress={"current_bar": 0, "total_bars": 0, "percent_complete": 0.0},
        estimated_cost=estimated_cost,
        created_at=datetime.utcnow(),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    launch_backtest_runtime.apply_async(
        kwargs={"backtest_run_id": str(run.id)},
        expires=60 * 60 * 6,
    )

    return BacktestStartResponse(run_id=run.id, status=run.status)


@router.get("", response_model=BacktestRunList)
async def list_backtests(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status_filter: Annotated[BacktestRunStatus | None, Query(alias="status")] = None,
):
    base_query = select(BacktestRun).where(BacktestRun.user_id == current_user.id)
    count_query = select(func.count()).select_from(BacktestRun).where(BacktestRun.user_id == current_user.id)
    if status_filter is not None:
        base_query = base_query.where(BacktestRun.status == status_filter)
        count_query = count_query.where(BacktestRun.status == status_filter)

    total = await db.scalar(count_query)
    result = await db.execute(
        base_query
        .order_by(BacktestRun.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return BacktestRunList(backtests=result.scalars().all(), total=total or 0)


@router.get("/{run_id}", response_model=BacktestRunSummary)
async def get_backtest(
    run_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(BacktestRun).where(BacktestRun.id == run_id, BacktestRun.user_id == current_user.id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest run not found")
    return run


@router.get("/{run_id}/results", response_model=BacktestRunResult)
async def get_backtest_results(
    run_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(BacktestRun).where(BacktestRun.id == run_id, BacktestRun.user_id == current_user.id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest run not found")
    return run


@router.post("/{run_id}/cancel", response_model=BacktestRunSummary)
async def cancel_backtest(
    run_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(BacktestRun).where(BacktestRun.id == run_id, BacktestRun.user_id == current_user.id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest run not found")

    if run.status in (BacktestRunStatus.COMPLETED, BacktestRunStatus.FAILED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Backtest run is already {run.status.value.lower()}",
        )

    if run.status != BacktestRunStatus.CANCELLED:
        previous_status = run.status
        run.status = BacktestRunStatus.CANCELLED
        run.failure_reason = "Cancelled by user"
        run_config = dict(run.config or {})
        runtime_config = dict(run_config.get("runtime") or {})
        runtime_config["cancel_requested_at"] = datetime.utcnow().isoformat()
        run_config["runtime"] = runtime_config
        run.config = run_config
        run.completed_at = datetime.utcnow()
        if previous_status == BacktestRunStatus.RUNNING:
            try:
                launcher = get_backtest_runtime_launcher()
                launcher.stop(runtime_config.get("launch_details"))
            except Exception:
                pass
        await db.commit()
        await db.refresh(run)

    return run
