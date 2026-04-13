"""
Helpers for freezing prompt and model state for parity backtests.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
from typing import Any, Dict, Iterable

from app.config import settings
from app.models.pipeline import Pipeline

PROMPT_AGENT_MAP = {
    "bias_agent": "bias_agent_system",
    "strategy_agent": "strategy_agent_system",
    "risk_manager_agent": "risk_manager_system",
    "trade_review_agent": "trade_review_agent_system",
}

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "agents" / "prompts"
DEFAULT_AGENT_MODELS = {
    "bias_agent": "gpt-4o",
    "strategy_agent": "gpt-4o",
    "risk_manager_agent": "gpt-4o",
    "trade_review_agent": "gpt-4o",
}


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _snapshot_prompt(prompt_name: str) -> Dict[str, Any]:
    prompt_path = PROMPTS_DIR / f"{prompt_name}.md"
    if not prompt_path.exists():
        return {
            "prompt_name": prompt_name,
            "path": str(prompt_path),
            "exists": False,
        }

    content = prompt_path.read_text(encoding="utf-8").strip()
    stat = prompt_path.stat()
    return {
        "prompt_name": prompt_name,
        "path": str(prompt_path),
        "exists": True,
        "sha256": _sha256(content),
        "size_bytes": stat.st_size,
        "modified_at": datetime.utcfromtimestamp(stat.st_mtime).isoformat(),
        "content": content,
    }


def _iter_pipeline_nodes(pipeline: Pipeline) -> Iterable[Dict[str, Any]]:
    config = pipeline.config or {}
    nodes = config.get("nodes") or []
    return [node for node in nodes if isinstance(node, dict)]


def _snapshot_agent_configs(pipeline: Pipeline) -> Dict[str, Dict[str, Any]]:
    snapshots: Dict[str, Dict[str, Any]] = {}
    for node in _iter_pipeline_nodes(pipeline):
        agent_type = node.get("agent_type") or node.get("type")
        if not agent_type:
            continue

        node_config = node.get("config") or {}
        snapshots[agent_type] = {
            "node_id": node.get("id"),
            "model": node_config.get("model") or DEFAULT_AGENT_MODELS.get(agent_type) or settings.OPENAI_MODEL,
            "instructions": node_config.get("instructions"),
            "raw_config": node_config,
        }
    return snapshots


def build_backtest_runtime_snapshot(pipeline: Pipeline) -> Dict[str, Any]:
    """
    Freeze prompt and model settings that affect parity backtest behavior.
    """
    prompt_snapshots = {
        agent_type: _snapshot_prompt(prompt_name)
        for agent_type, prompt_name in PROMPT_AGENT_MAP.items()
    }
    return {
        "created_at": datetime.utcnow().isoformat(),
        "llm_settings": {
            "openai_model": settings.OPENAI_MODEL,
            "openai_temperature": settings.OPENAI_TEMPERATURE,
            "openai_base_url": settings.OPENAI_BASE_URL,
            "langfuse_enabled": settings.LANGFUSE_ENABLED,
        },
        "agent_configs": _snapshot_agent_configs(pipeline),
        "prompts": prompt_snapshots,
    }


def prompt_overrides_from_runtime_snapshot(runtime_snapshot: Dict[str, Any] | None) -> Dict[str, str]:
    overrides: Dict[str, str] = {}
    for prompt_snapshot in (runtime_snapshot or {}).get("prompts", {}).values():
        prompt_name = prompt_snapshot.get("prompt_name")
        content = prompt_snapshot.get("content")
        if prompt_name and isinstance(content, str):
            overrides[prompt_name] = content
    return overrides


def hydrate_pipeline_from_snapshot(snapshot: Dict[str, Any], *, fallback_pipeline_id=None, fallback_user_id=None):
    config = deepcopy(snapshot.get("config") or {})
    return SimpleNamespace(
        id=snapshot.get("id") or fallback_pipeline_id,
        user_id=snapshot.get("user_id") or fallback_user_id,
        name=snapshot.get("name"),
        description=snapshot.get("description"),
        config=config,
        trigger_mode=snapshot.get("trigger_mode"),
        scanner_id=snapshot.get("scanner_id"),
        signal_subscriptions=deepcopy(snapshot.get("signal_subscriptions") or []),
        scanner_tickers=deepcopy(snapshot.get("scanner_tickers") or []),
        require_approval=snapshot.get("require_approval", False),
        approval_modes=deepcopy(snapshot.get("approval_modes") or []),
        schedule_enabled=snapshot.get("schedule_enabled", False),
        schedule_start_time=snapshot.get("schedule_start_time"),
        schedule_end_time=snapshot.get("schedule_end_time"),
        schedule_days=deepcopy(snapshot.get("schedule_days") or []),
        liquidate_on_deactivation=snapshot.get("liquidate_on_deactivation", False),
        user_timezone=snapshot.get("user_timezone") or "America/New_York",
        runtime_snapshot=deepcopy(snapshot.get("runtime_snapshot") or {}),
    )
