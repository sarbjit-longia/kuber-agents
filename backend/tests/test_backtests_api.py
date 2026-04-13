from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.backtests import cancel_backtest, start_backtest
from app.models.backtest_run import BacktestRunStatus
from app.schemas.backtest import BacktestCreate


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        if self._value is None:
            return []
        if isinstance(self._value, list):
            return self._value
        return [self._value]


class FakeAsyncSession:
    def __init__(self, *, pipeline=None, run=None, executions=None, scalar_values=None):
        self.pipeline = pipeline
        self.run = run
        self.executions = executions or []
        self.scalar_values = list(scalar_values or [])
        self.added = []
        self.committed = 0
        self.refreshed = 0

    async def execute(self, _query):
        if self.pipeline is not None:
            pipeline = self.pipeline
            self.pipeline = None
            return _ScalarResult(pipeline)
        if self.run is not None:
            run = self.run
            self.run = None
            return _ScalarResult(run)
        return _ScalarResult(self.executions)

    async def scalar(self, _query):
        if not self.scalar_values:
            return 0
        return self.scalar_values.pop(0)

    def add(self, obj):
        self.added.append(obj)
        self.run = obj

    async def commit(self):
        self.committed += 1

    async def refresh(self, obj):
        self.refreshed += 1
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()


@pytest.mark.asyncio
@pytest.mark.no_tool_mocks
async def test_start_backtest_creates_run_snapshot_and_launches(monkeypatch):
    user_id = uuid4()
    pipeline = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        name="Parity Pipeline",
        description="Backtest me",
        config={
            "nodes": [
                {
                    "id": "bias-node",
                    "agent_type": "bias_agent",
                    "config": {"model": "gpt-4o", "instructions": "Bias rules"},
                }
            ],
            "edges": [],
        },
        trigger_mode=None,
        scanner_id=None,
        signal_subscriptions=[{"signal_type": "golden_cross"}],
        scanner_tickers=["AAPL"],
        require_approval=False,
        approval_modes=[],
        schedule_enabled=False,
        schedule_start_time=None,
        schedule_end_time=None,
        schedule_days=[],
        liquidate_on_deactivation=False,
    )
    db = FakeAsyncSession(pipeline=pipeline, scalar_values=[0, 0, 0])
    current_user = SimpleNamespace(id=user_id, timezone="America/New_York")
    launch_calls = []

    monkeypatch.setattr(
        "app.api.v1.backtests.launch_backtest_runtime.apply_async",
        lambda **kwargs: launch_calls.append(kwargs),
    )

    payload = BacktestCreate(
        pipeline_id=pipeline.id,
        symbols=["AAPL", "MSFT"],
        start_date="2026-03-01",
        end_date="2026-03-31",
        timeframe="5m",
        initial_capital=10_000,
        slippage_model="fixed",
        slippage_value=0.01,
        commission_model="per_share",
        commission_value=0.005,
    )

    response = await start_backtest(payload=payload, current_user=current_user, db=db)

    assert response.status == BacktestRunStatus.PENDING
    assert db.added, "BacktestRun should be persisted"
    run = db.added[0]
    assert run.config["pipeline_snapshot"]["name"] == "Parity Pipeline"
    assert run.config["pipeline_snapshot"]["user_timezone"] == "America/New_York"
    assert run.config["pipeline_snapshot"]["liquidate_on_deactivation"] is False
    assert run.config["runtime_snapshot"]["agent_configs"]["bias_agent"]["instructions"] == "Bias rules"
    assert run.config["runtime"]["mode"] == "ephemeral_sandbox"
    assert launch_calls and launch_calls[0]["kwargs"]["backtest_run_id"] == str(run.id)


@pytest.mark.asyncio
@pytest.mark.no_tool_mocks
async def test_start_backtest_rejects_when_user_limit_reached():
    user_id = uuid4()
    pipeline = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        name="Busy Pipeline",
        description="",
        config={"nodes": [], "edges": []},
        trigger_mode=None,
        scanner_id=None,
        signal_subscriptions=[],
        scanner_tickers=[],
        require_approval=False,
        approval_modes=[],
        schedule_enabled=False,
        schedule_start_time=None,
        schedule_end_time=None,
        schedule_days=[],
        liquidate_on_deactivation=False,
    )
    db = FakeAsyncSession(pipeline=pipeline, scalar_values=[2])
    current_user = SimpleNamespace(id=user_id)
    payload = BacktestCreate(
        pipeline_id=pipeline.id,
        symbols=["AAPL"],
        start_date="2026-03-01",
        end_date="2026-03-31",
    )

    with pytest.raises(HTTPException) as exc_info:
        await start_backtest(payload=payload, current_user=current_user, db=db)

    assert exc_info.value.status_code == 429
    assert "concurrency limit" in exc_info.value.detail.lower()


@pytest.mark.asyncio
@pytest.mark.no_tool_mocks
async def test_cancel_backtest_marks_run_and_requests_runtime_stop(monkeypatch):
    run_id = uuid4()
    pipeline_id = uuid4()
    user_id = uuid4()
    run = SimpleNamespace(
        id=run_id,
        user_id=user_id,
        pipeline_id=pipeline_id,
        pipeline_name="Pipeline",
        status=BacktestRunStatus.RUNNING,
        progress={},
        metrics={},
        trades=[],
        equity_curve=[],
        estimated_cost=None,
        actual_cost=0.0,
        failure_reason=None,
        created_at=datetime.utcnow(),
        started_at=None,
        completed_at=None,
        config={"runtime": {"launch_details": {"container_name": "bt-123"}}},
    )
    db = FakeAsyncSession(run=run, executions=[])
    current_user = SimpleNamespace(id=user_id)
    stop_calls = []

    class FakeLauncher:
        def stop(self, runtime_details):
            stop_calls.append(runtime_details)
            return True

    monkeypatch.setattr("app.api.v1.backtests.get_backtest_runtime_launcher", lambda: FakeLauncher())

    response = await cancel_backtest(run_id=run_id, current_user=current_user, db=db)

    assert response.status == BacktestRunStatus.CANCELLED
    assert response.failure_reason == "Cancelled by user"
    assert response.completed_at is not None
    assert stop_calls == [{"container_name": "bt-123"}]
