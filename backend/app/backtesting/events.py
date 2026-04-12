"""
Helpers for persisting structured backtest events.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.backtest_event import BacktestEvent
from app.models.backtest_run import BacktestRun


def create_backtest_event(
    *,
    run: BacktestRun,
    event_type: str,
    title: str,
    message: str,
    level: str = "info",
    symbol: str | None = None,
    execution_id: str | UUID | None = None,
    data: dict[str, Any] | None = None,
) -> BacktestEvent:
    normalized_execution_id = None
    if execution_id:
        normalized_execution_id = UUID(str(execution_id))

    return BacktestEvent(
        run_id=run.id,
        user_id=run.user_id,
        pipeline_id=run.pipeline_id,
        execution_id=normalized_execution_id,
        event_type=event_type,
        level=level,
        title=title,
        message=message,
        symbol=symbol,
        data=data or {},
    )
