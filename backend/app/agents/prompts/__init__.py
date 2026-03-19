"""
Prompt loader for agent system prompts.

Loads .md files from this directory and caches them at import time.
"""

import os
import structlog

logger = structlog.get_logger()

_PROMPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_cache: dict[str, str] = {}


def load_prompt(agent_name: str) -> str:
    """Load a system prompt from a .md file in the prompts directory.

    Args:
        agent_name: Base name of the prompt file (without extension).
                    E.g. "bias_agent_system" loads "bias_agent_system.md".

    Returns:
        The prompt text, or empty string if the file is not found.
    """
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
