"""
Prompt loader for agent system prompts.

Loads .md files from this directory and supports scoped runtime overrides for
backtests that need frozen prompt snapshots.
"""

from contextlib import contextmanager
from contextvars import ContextVar
import os

import structlog

logger = structlog.get_logger()

_PROMPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_cache: dict[str, str] = {}
_prompt_overrides: ContextVar[dict[str, str] | None] = ContextVar(
    "agent_prompt_overrides",
    default=None,
)


@contextmanager
def use_prompt_overrides(overrides: dict[str, str] | None):
    token = _prompt_overrides.set(overrides or None)
    try:
        yield
    finally:
        _prompt_overrides.reset(token)


def load_prompt(agent_name: str) -> str:
    """Load a system prompt from a .md file in the prompts directory.

    Args:
        agent_name: Base name of the prompt file (without extension).
                    E.g. "bias_agent_system" loads "bias_agent_system.md".

    Returns:
        The prompt text, or empty string if the file is not found.
    """
    overrides = _prompt_overrides.get() or {}
    if agent_name in overrides:
        return overrides[agent_name]

    if agent_name in _cache:
        return _cache[agent_name]

    file_path = os.path.join(_PROMPTS_DIR, f"{agent_name}.md")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        _cache[agent_name] = content
        logger.info("prompt_loaded", agent_name=agent_name, tokens_approx=len(content.split()))
        return content
    except FileNotFoundError:
        logger.warning("prompt_file_not_found", agent_name=agent_name, path=file_path)
        _cache[agent_name] = ""
        return ""


def load_kb_context(agent_type: str) -> str:
    """Load foundational KB concepts for the given agent type."""
    from app.services.kb_loader import kb_loader

    return kb_loader.load_concepts_bundle(agent_type)
