"""
Schemas for reusable agent skills.
"""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class AgentSkillAttachment(BaseModel):
    """A skill attached to a specific agent node in a pipeline."""

    skill_id: str = Field(..., min_length=1, max_length=120)
    version: Optional[str] = Field(default=None, max_length=32)
    enabled: bool = Field(default=True)
    overrides: Dict[str, Any] = Field(default_factory=dict)


class SkillSummary(BaseModel):
    """Catalog-facing summary of an available skill."""

    skill_id: str
    name: str
    slug: str
    version: str
    description: str
    agent_types: List[str] = Field(default_factory=list)
    source_type: Literal["system", "user_copy", "marketplace"] = "system"
    status: Literal["active", "deprecated", "draft"] = "active"
    tags: List[str] = Field(default_factory=list)
    category: str = "general"
    recommended_tools: List[str] = Field(default_factory=list)


class SkillDetail(SkillSummary):
    """Detailed skill definition used by the builder and runtime."""

    instruction_fragment: str = ""
    guardrails: List[str] = Field(default_factory=list)
    tool_overrides: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    publisher: str = "CloverCharts"
    visibility: Literal["private", "curated", "public"] = "curated"

