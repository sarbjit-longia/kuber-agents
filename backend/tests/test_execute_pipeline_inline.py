from __future__ import annotations

import os

import pytest

os.environ.setdefault("HOME", "/tmp")

try:
    from app.orchestration.tasks.execute_pipeline import execute_pipeline, execute_pipeline_inline
except PermissionError as exc:  # pragma: no cover - local CrewAI import quirk
    pytest.skip(f"execute_pipeline import unavailable in local test env: {exc}", allow_module_level=True)


@pytest.mark.no_tool_mocks
def test_execute_pipeline_inline_uses_task_request_stack(monkeypatch):
    events: list[tuple[str, object]] = []

    def fake_push_request(**kwargs):
        events.append(("push", kwargs["id"]))

    def fake_pop_request():
        events.append(("pop", None))

    def fake_run(**kwargs):
        events.append(("run", kwargs))
        return {"status": "completed"}

    monkeypatch.setattr(execute_pipeline, "push_request", fake_push_request)
    monkeypatch.setattr(execute_pipeline, "pop_request", fake_pop_request)
    monkeypatch.setattr(execute_pipeline, "run", fake_run)

    result = execute_pipeline_inline(
        pipeline_id="pipeline-1",
        user_id="user-1",
        mode="backtest",
        execution_id="execution-1",
        signal_context={"metadata": {"backtest_run_id": "run-1"}},
        symbol="AAPL",
    )

    assert result == {"status": "completed"}
    assert events[0][0] == "push"
    assert str(events[0][1]).startswith("inline-")
    assert events[1] == (
        "run",
        {
            "pipeline_id": "pipeline-1",
            "user_id": "user-1",
            "mode": "backtest",
            "execution_id": "execution-1",
            "signal_context": {"metadata": {"backtest_run_id": "run-1"}},
            "symbol": "AAPL",
            "pipeline_snapshot": None,
            "runtime_snapshot": None,
        },
    )
    assert events[2] == ("pop", None)
