from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.backtesting.orchestrator import BacktestOrchestrator
from app.backtesting.runtime_main import _start_embedded_signal_generator
from app.agents.risk_manager_agent import RiskManagerAgent
from app.models.backtest_run import BacktestRunStatus
from app.config import settings


class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, key: str):
        return self.store.get(key)

    def set(self, key: str, value: str):
        self.store[key] = value

    def delete(self, key: str):
        self.store.pop(key, None)

    def exists(self, key: str):
        return key in self.store


class FakeBroker:
    shared_redis = FakeRedis()

    def __init__(self, run_id: str, initial_capital: float, **_kwargs):
        self.run_id = run_id
        self.initial_capital = initial_capital
        self.redis = self.__class__.shared_redis
        self.closed_trades: list[dict] = []
        self.equity = initial_capital

    def evaluate_bar(self, symbol: str, candle: dict):
        self.equity = float(candle["close"])
        if candle.get("close_trade"):
            trade = {
                "id": f"{symbol}-trade",
                "strategy_family": "test",
                "action": "BUY",
                "entry_time": candle["timestamp"],
                "exit_time": candle["timestamp"],
                "entry_price": float(candle["close"]),
                "exit_price": float(candle["close"]),
                "stop_loss": 0.0,
                "take_profit": 0.0,
                "position_size": 1.0,
                "gross_pnl": 0.0,
                "commission": 0.0,
                "slippage": 0.0,
                "net_pnl": 0.0,
                "exit_reason": "target",
                "regime": "",
                "session": "",
                "duration_bars": 1,
                "r_multiple": 0.0,
            }
            self.closed_trades.append(trade)
            return trade
        return None

    def get_closed_trades(self):
        return list(self.closed_trades)

    def get_equity(self):
        return float(self.equity)


class FakeDbResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeDbSession:
    def __init__(self, status=BacktestRunStatus.RUNNING):
        self.status = status
        self.commit_count = 0

    def commit(self):
        self.commit_count += 1

    def execute(self, _query):
        return FakeDbResult(self.status)


def _make_run(**config_overrides):
    run_id = uuid4()
    run_config = {
        "symbols": ["AAPL"],
        "start_date": "2026-03-01",
        "end_date": "2026-03-02",
        "timeframe": "5m",
        "initial_capital": 10000.0,
    }
    run_config.update(config_overrides)
    return SimpleNamespace(
        id=run_id,
        user_id=uuid4(),
        config=run_config,
        status=BacktestRunStatus.PENDING,
        started_at=None,
        completed_at=None,
        actual_cost=0.0,
        failure_reason=None,
        progress={},
        metrics=None,
        equity_curve=[],
        trades=[],
        trades_count=0,
    )


def _make_pipeline():
    return SimpleNamespace(
        id=uuid4(),
        signal_subscriptions=[{"signal_type": "golden_cross"}],
    )


@pytest.mark.no_tool_mocks
def test_embedded_signal_generator_missing_path_fails_loudly(monkeypatch):
    monkeypatch.setattr(settings, "BACKTEST_RUNTIME_EMBED_SIGNAL_GENERATOR", True)
    monkeypatch.setattr("app.backtesting.runtime_main.os.path.exists", lambda _path: False)

    with pytest.raises(FileNotFoundError):
        _start_embedded_signal_generator()


@pytest.mark.no_tool_mocks
def test_orchestrator_stops_when_actual_cost_exceeds_budget(monkeypatch):
    FakeBroker.shared_redis = FakeRedis()
    monkeypatch.setattr("app.backtesting.orchestrator.BacktestBroker", FakeBroker)
    monkeypatch.setattr(
        "app.backtesting.orchestrator.PerformanceAnalytics.compute",
        lambda trades, equity_curve, initial_capital: {"trade_count": len(trades)},
    )

    run = _make_run(max_cost_usd=5.0)
    pipeline = _make_pipeline()
    db = FakeDbSession()
    orchestrator = BacktestOrchestrator(run, pipeline, db)

    monkeypatch.setattr(orchestrator, "_fetch_symbol_bars", lambda symbol: [{
        "timestamp": "2026-03-01T09:30:00Z",
        "high": 101,
        "low": 99,
        "close": 100,
    }])
    monkeypatch.setattr(orchestrator, "_replay_signals_for_timestamp", lambda _ts, _types: [{"ticker": "AAPL"}])
    monkeypatch.setattr(
        orchestrator,
        "_dispatch_signals_in_runtime",
        lambda _signals: [{"result": {"cost": 8.0}}],
    )

    result = orchestrator.run_backtest()

    assert result["status"] == BacktestRunStatus.FAILED.value
    assert run.status == BacktestRunStatus.FAILED
    assert "exceeded max_cost_usd" in (run.failure_reason or "")
    assert not FakeBroker.shared_redis.exists(f"backtest:{run.id}:checkpoint")


@pytest.mark.no_tool_mocks
def test_orchestrator_resume_skips_replaying_signals_for_checkpointed_timestamp(monkeypatch):
    FakeBroker.shared_redis = FakeRedis()
    monkeypatch.setattr("app.backtesting.orchestrator.BacktestBroker", FakeBroker)
    monkeypatch.setattr(
        "app.backtesting.orchestrator.PerformanceAnalytics.compute",
        lambda trades, equity_curve, initial_capital: {"trade_count": len(trades)},
    )

    run = _make_run()
    pipeline = _make_pipeline()
    db = FakeDbSession()
    checkpoint_key = f"backtest:{run.id}:checkpoint"
    FakeBroker.shared_redis.set(
        checkpoint_key,
        json.dumps(
            {
                "timeline_index": 0,
                "current_symbol_index": -1,
                "processed_bars": 0,
                "total_bars": 1,
                "current_ts": "2026-03-01T09:30:00Z",
                "signal_dispatch_completed": True,
                "equity_curve": [10000.0],
                "actual_cost": 0.0,
            }
        ),
    )
    orchestrator = BacktestOrchestrator(run, pipeline, db)

    monkeypatch.setattr(orchestrator, "_fetch_symbol_bars", lambda symbol: [{
        "timestamp": "2026-03-01T09:30:00Z",
        "high": 101,
        "low": 99,
        "close": 100,
    }])
    replay_calls = []
    monkeypatch.setattr(
        orchestrator,
        "_replay_signals_for_timestamp",
        lambda _ts, _types: replay_calls.append(_ts) or [],
    )
    monkeypatch.setattr(orchestrator, "_dispatch_signals_in_runtime", lambda _signals: [])

    result = orchestrator.run_backtest()

    assert result["status"] == BacktestRunStatus.COMPLETED.value
    assert replay_calls == []


@pytest.mark.no_tool_mocks
def test_orchestrator_equity_curve_appends_once_per_processed_bar(monkeypatch):
    FakeBroker.shared_redis = FakeRedis()
    monkeypatch.setattr("app.backtesting.orchestrator.BacktestBroker", FakeBroker)
    monkeypatch.setattr(
        "app.backtesting.orchestrator.PerformanceAnalytics.compute",
        lambda trades, equity_curve, initial_capital: {"trade_count": len(trades)},
    )

    run = _make_run()
    pipeline = _make_pipeline()
    db = FakeDbSession()
    orchestrator = BacktestOrchestrator(run, pipeline, db)

    monkeypatch.setattr(orchestrator, "_fetch_symbol_bars", lambda symbol: [{
        "timestamp": "2026-03-01T09:30:00Z",
        "high": 101,
        "low": 99,
        "close": 100,
        "close_trade": True,
    }])
    monkeypatch.setattr(orchestrator, "_replay_signals_for_timestamp", lambda _ts, _types: [])
    monkeypatch.setattr(orchestrator, "_dispatch_signals_in_runtime", lambda _signals: [])
    monkeypatch.setattr(orchestrator, "_trade_from_dict", lambda trade: trade)

    orchestrator.run_backtest()

    assert run.equity_curve == [10000.0, 100.0]


@pytest.mark.no_tool_mocks
def test_orchestrator_replays_all_signal_types_when_pipeline_has_no_subscriptions(monkeypatch):
    FakeBroker.shared_redis = FakeRedis()
    monkeypatch.setattr("app.backtesting.orchestrator.BacktestBroker", FakeBroker)

    run = _make_run()
    pipeline = SimpleNamespace(id=uuid4(), signal_subscriptions=[])
    db = FakeDbSession()
    orchestrator = BacktestOrchestrator(run, pipeline, db)

    captured: dict[str, object] = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [{"signal_type": "distribution_signal"}]

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr(orchestrator.http, "post", fake_post)

    signals = orchestrator._replay_signals_for_timestamp("2026-04-10T19:45:00+00:00", [])

    assert signals == [{"signal_type": "distribution_signal"}]
    assert captured["json"]["signal_types"] == []
    assert captured["json"]["symbols"] == ["AAPL"]


@pytest.mark.no_tool_mocks
def test_risk_manager_uses_backtest_broker_account_info(monkeypatch):
    class StubBacktestBroker:
        def __init__(self, run_id: str, initial_capital: float, **_kwargs):
            self.run_id = run_id
            self.initial_capital = initial_capital

        def get_account(self):
            return {"cash": 8250.0, "equity": 10350.0}

        def get_positions(self):
            return {
                "AAPL": {
                    "symbol": "AAPL",
                    "qty": 12,
                    "entry_price": 245.5,
                }
            }

    monkeypatch.setattr(
        "app.agents.risk_manager_agent.BacktestBroker",
        StubBacktestBroker,
        raising=False,
    )

    agent = RiskManagerAgent.__new__(RiskManagerAgent)
    agent.config = {"initial_capital": 100000.0}
    agent.logger = SimpleNamespace(warning=lambda *_args, **_kwargs: None)
    agent.log = lambda *_args, **_kwargs: None
    agent._get_broker_tool = lambda: (_ for _ in ()).throw(
        AssertionError("live broker lookup should not run during backtests")
    )

    state = SimpleNamespace(mode="backtest", backtest_run_id="run-123", initial_capital=100000.0)

    broker_info = agent._get_broker_account_info(state)

    assert broker_info["source"] == "backtest_broker"
    assert broker_info["buying_power"] == 8250.0
    assert broker_info["equity"] == 10350.0
    assert broker_info["positions"][0]["symbol"] == "AAPL"
