"""
Strategy document helpers.
"""
from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any, Dict, Iterable, Tuple


_LIST_FIELDS = {"tags", "markets", "timeframes"}


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "strategy"


def _parse_list(raw: str) -> list[str]:
    value = raw.strip()
    if not value:
        return []
    if value.startswith("[") and value.endswith("]"):
        try:
            decoded = json.loads(value)
            if isinstance(decoded, list):
                return [str(item).strip() for item in decoded if str(item).strip()]
        except json.JSONDecodeError:
            pass
        value = value[1:-1]
    return [part.strip() for part in value.split(",") if part.strip()]


def parse_frontmatter(markdown_content: str) -> Tuple[Dict[str, Any], str]:
    if not markdown_content or not markdown_content.startswith("---\n"):
        return {}, markdown_content or ""

    end = markdown_content.find("\n---\n", 4)
    if end == -1:
        return {}, markdown_content

    header = markdown_content[4:end]
    body = markdown_content[end + 5 :]
    data: Dict[str, Any] = {}
    for line in header.splitlines():
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        if key in _LIST_FIELDS:
            data[key] = _parse_list(value)
        else:
            data[key] = value.strip('"').strip("'")
    return data, body.lstrip("\n")


def serialize_frontmatter(metadata: Dict[str, Any]) -> str:
    lines = ["---"]
    for key in (
        "title",
        "summary",
        "visibility",
        "category",
        "style",
        "difficulty",
        "markets",
        "timeframes",
        "tags",
        "risk_notes",
        "pipeline_snapshot_version",
    ):
        value = metadata.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, list):
            rendered = ", ".join(str(item) for item in value if str(item).strip())
        else:
            rendered = str(value)
        lines.append(f"{key}: {rendered}")
    lines.append("---")
    return "\n".join(lines)


def compose_markdown(metadata: Dict[str, Any], body_markdown: str) -> str:
    header = serialize_frontmatter(metadata)
    body = (body_markdown or "").strip()
    return f"{header}\n\n{body}\n" if body else f"{header}\n"


def merge_strategy_metadata(
    explicit: Dict[str, Any],
    parsed: Dict[str, Any],
    defaults: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    merged = dict(defaults or {})
    merged.update({k: v for k, v in parsed.items() if v not in (None, "")})
    merged.update({k: v for k, v in explicit.items() if v not in (None, "")})
    for field in _LIST_FIELDS:
        merged[field] = [str(item).strip() for item in merged.get(field, []) if str(item).strip()]
    return merged


def normalize_pipeline_spec(spec: Dict[str, Any] | None) -> Dict[str, Any]:
    normalized = dict(spec or {})
    pipeline = normalized.get("pipeline") if isinstance(normalized.get("pipeline"), dict) else {}
    normalized["pipeline"] = pipeline
    normalized["is_runnable"] = bool(pipeline.get("config"))
    return normalized


def build_strategy_scaffold(title: str, summary: str | None = None) -> str:
    body = [
        "## Thesis",
        "",
        summary or "Describe the market context and setup this strategy trades.",
        "",
        "## Entry Rules",
        "",
        "- Define the trigger clearly.",
        "",
        "## Risk Management",
        "",
        "- Define stop placement, target logic, and invalidation.",
        "",
        "## Operational Notes",
        "",
        "- Describe broker, schedule, or approval assumptions.",
    ]
    return "\n".join(body)


def build_strategy_body_from_pipeline(snapshot: Dict[str, Any]) -> str:
    config = snapshot.get("config") or {}
    nodes = config.get("nodes") or []
    signal_filters = snapshot.get("signal_subscriptions") or []

    lines: list[str] = [
        "**PIPELINE OVERVIEW:**",
        f"• Pipeline Name: {snapshot.get('name') or 'Unnamed pipeline'}",
        f"• Description: {snapshot.get('description') or 'No description provided.'}",
        f"• Trigger Mode: {snapshot.get('trigger_mode') or 'periodic'}",
        f"• Runtime Mode: {config.get('mode') or 'paper'}",
        "",
        "**OPERATIONAL SETTINGS:**",
        f"• Approval Required: {'Yes' if snapshot.get('require_approval') else 'No'}",
        f"• Notifications Enabled: {'Yes' if snapshot.get('notification_enabled') else 'No'}",
        f"• Active Hours Enabled: {'Yes' if snapshot.get('schedule_enabled') else 'No'}",
    ]

    if signal_filters:
        lines.extend(["", "**SIGNAL FILTERS:**"])
        for entry in signal_filters:
            label = entry.get("signal_type", "signal")
            if entry.get("timeframe"):
                label = f"{label} ({entry['timeframe']})"
            if entry.get("min_confidence") is not None:
                label = f"{label} min confidence {entry['min_confidence']}"
            lines.append(f"• {label}")

    if nodes:
        lines.extend(["", "**AGENT CONFIGURATION:**"])
        for index, node in enumerate(nodes, start=1):
            agent_type = node.get("agent_type", "agent")
            agent_config = node.get("config") or {}
            lines.append(f"• Step {index}: {agent_type}")
            instructions = str(agent_config.get("instructions") or "").strip()
            if instructions:
                instruction_preview = " ".join(instructions.split())
                lines.append(f"  Prompt: {instruction_preview[:240]}{'…' if len(instruction_preview) > 240 else ''}")
            skills = agent_config.get("skills") or []
            if skills:
                lines.append("  Skills: " + ", ".join(
                    skill.get("skill_id", "skill") if isinstance(skill, dict) else str(skill)
                    for skill in skills
                ))
            tools = agent_config.get("tools") or []
            if tools:
                tool_names = []
                for tool in tools:
                    if isinstance(tool, dict):
                        tool_names.append(str(tool.get("tool_type") or tool.get("type") or tool.get("name") or "tool"))
                    else:
                        tool_names.append(str(tool))
                lines.append("  Tools: " + ", ".join(tool_names))

    return "\n".join(lines)


def remove_pipeline_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for key, item in value.items():
            lower = key.lower()
            if any(secret in lower for secret in ("token", "secret", "api_key", "apikey", "account_id", "phone", "chat_id", "bot_token")):
                continue
            cleaned[key] = remove_pipeline_secrets(item)
        return cleaned
    if isinstance(value, list):
        return [remove_pipeline_secrets(item) for item in value]
    return value


def remove_pipeline_brokers(snapshot: Dict[str, Any] | None) -> Dict[str, Any]:
    cleaned = deepcopy(snapshot or {})
    config = cleaned.get("config")
    if isinstance(config, dict):
        config.pop("broker_tool", None)

        nodes = config.get("nodes")
        if isinstance(nodes, list):
            for node in nodes:
                node_config = node.get("config") if isinstance(node, dict) else None
                if not isinstance(node_config, dict):
                    continue

                tools = node_config.get("tools")
                if isinstance(tools, list):
                    node_config["tools"] = [
                        tool
                        for tool in tools
                        if not _is_broker_tool(tool)
                    ]

    return cleaned


def _is_broker_tool(tool: Any) -> bool:
    if isinstance(tool, str):
        raw = tool
    elif isinstance(tool, dict):
        raw = tool.get("tool_type") or tool.get("type") or tool.get("name") or ""
    else:
        raw = ""

    value = str(raw).lower()
    return value.endswith("_broker") or value == "broker"


def filter_frontmatter(metadata: Dict[str, Any], keys: Iterable[str]) -> Dict[str, Any]:
    return {key: metadata.get(key) for key in keys if metadata.get(key) not in (None, "", [])}
