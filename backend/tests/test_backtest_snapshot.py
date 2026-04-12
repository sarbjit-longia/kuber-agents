from types import SimpleNamespace
import importlib.util
from pathlib import Path

import pytest

from app.backtesting.snapshot import (
    build_backtest_runtime_snapshot,
    hydrate_pipeline_from_snapshot,
    prompt_overrides_from_runtime_snapshot,
)

_PROMPTS_MODULE_PATH = Path(__file__).resolve().parent.parent / "app" / "agents" / "prompts" / "__init__.py"
_PROMPTS_SPEC = importlib.util.spec_from_file_location("backtest_prompt_module", _PROMPTS_MODULE_PATH)
_PROMPTS_MODULE = importlib.util.module_from_spec(_PROMPTS_SPEC)
assert _PROMPTS_SPEC is not None and _PROMPTS_SPEC.loader is not None
_PROMPTS_SPEC.loader.exec_module(_PROMPTS_MODULE)
load_prompt = _PROMPTS_MODULE.load_prompt
use_prompt_overrides = _PROMPTS_MODULE.use_prompt_overrides


@pytest.mark.no_tool_mocks
def test_build_backtest_runtime_snapshot_captures_agent_configs_and_prompts():
    pipeline = SimpleNamespace(
        config={
            "nodes": [
                {
                    "id": "node-bias",
                    "agent_type": "bias_agent",
                    "config": {
                        "model": "gpt-4o",
                        "instructions": "Bias instructions",
                    },
                },
                {
                    "id": "node-strategy",
                    "agent_type": "strategy_agent",
                    "config": {
                        "instructions": "Strategy instructions",
                    },
                },
                {
                    "id": "node-risk",
                    "agent_type": "risk_manager_agent",
                    "config": {},
                },
            ]
        }
    )

    snapshot = build_backtest_runtime_snapshot(pipeline)

    assert "created_at" in snapshot
    assert "llm_settings" in snapshot
    assert "prompts" in snapshot
    assert "agent_configs" in snapshot

    agent_configs = snapshot["agent_configs"]
    assert agent_configs["bias_agent"]["node_id"] == "node-bias"
    assert agent_configs["bias_agent"]["model"] == "gpt-4o"
    assert agent_configs["bias_agent"]["instructions"] == "Bias instructions"

    assert agent_configs["strategy_agent"]["model"] == "gpt-4o"
    assert agent_configs["strategy_agent"]["instructions"] == "Strategy instructions"
    assert agent_configs["risk_manager_agent"]["model"] == "gpt-4o"

    bias_prompt = snapshot["prompts"]["bias_agent"]
    assert bias_prompt["exists"] is True
    assert bias_prompt["prompt_name"] == "bias_agent_system"
    assert bias_prompt["sha256"]
    assert bias_prompt["content"]


@pytest.mark.no_tool_mocks
def test_build_backtest_runtime_snapshot_handles_missing_prompt_mapping_nodes():
    pipeline = SimpleNamespace(
        config={
            "nodes": [
                {
                    "id": "node-market-data",
                    "agent_type": "market_data_agent",
                    "config": {"timeframes": ["5m", "1h"]},
                }
            ]
        }
    )

    snapshot = build_backtest_runtime_snapshot(pipeline)

    assert "market_data_agent" in snapshot["agent_configs"]
    assert snapshot["agent_configs"]["market_data_agent"]["model"] is not None
    assert set(snapshot["prompts"].keys()) == {
        "bias_agent",
        "strategy_agent",
        "risk_manager_agent",
        "trade_review_agent",
    }


@pytest.mark.no_tool_mocks
def test_prompt_overrides_can_be_derived_and_applied_from_runtime_snapshot():
    pipeline = SimpleNamespace(
        config={
            "nodes": [
                {
                    "id": "node-bias",
                    "agent_type": "bias_agent",
                    "config": {"instructions": "Bias rules"},
                }
            ]
        }
    )

    snapshot = build_backtest_runtime_snapshot(pipeline)
    snapshot["prompts"]["bias_agent"]["content"] = "Frozen bias prompt"
    overrides = prompt_overrides_from_runtime_snapshot(snapshot)

    with use_prompt_overrides(overrides):
        assert load_prompt("bias_agent_system") == "Frozen bias prompt"

    assert load_prompt("bias_agent_system") != "Frozen bias prompt"


@pytest.mark.no_tool_mocks
def test_hydrate_pipeline_from_snapshot_preserves_runtime_snapshot():
    pipeline = hydrate_pipeline_from_snapshot(
        {
            "id": "4f46b615-2359-4a9f-ae96-3f9d2e648099",
            "user_id": "5c1a72db-71dd-444b-b819-1b51ef6190fd",
            "name": "Snapshot Pipeline",
            "config": {"nodes": [{"id": "strategy", "agent_type": "strategy_agent", "config": {}}]},
            "signal_subscriptions": [{"signal_type": "golden_cross"}],
            "runtime_snapshot": {"prompts": {"strategy_agent": {"content": "Frozen strategy"}}},
        }
    )

    assert pipeline.name == "Snapshot Pipeline"
    assert pipeline.runtime_snapshot["prompts"]["strategy_agent"]["content"] == "Frozen strategy"
    assert pipeline.signal_subscriptions[0]["signal_type"] == "golden_cross"
