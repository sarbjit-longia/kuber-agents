"""
First-party skill registry and runtime resolver.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.schemas.skill import AgentSkillAttachment, SkillDetail, SkillSummary
from app.services.kb_loader import kb_loader


_RUNTIME_TOOL_MAP: Dict[str, str] = {
    "fvg_detector": "fvg_detector",
    "order_block_detector": "order_block_detector",
    "session_context_analyzer": "session_context_analyzer",
    "liquidity_analyzer": "liquidity_analyzer",
    "market_structure": "market_structure_analyzer",
    "premium_discount": "premium_discount_analyzer",
    "rsi": "rsi_calculator",
    "macd": "macd_calculator",
    "sma_crossover": "sma_crossover",
    "bollinger_bands": "bollinger_bands",
}


_HARDCODED_SKILLS: Dict[str, SkillDetail] = {
    "ict_fvg_retracement": SkillDetail(
        skill_id="ict_fvg_retracement",
        name="ICT FVG Retracement",
        slug="ict-fvg-retracement",
        version="1.0.0",
        description=(
            "Trade fair value gaps as retracement zones, not as standalone entry triggers."
        ),
        category="ict",
        agent_types=["strategy_agent", "bias_agent"],
        tags=["ict", "fvg", "smc", "retracement"],
        recommended_tools=[
            "fvg_detector",
            "market_structure",
            "premium_discount",
            "liquidity_analyzer",
        ],
        instruction_fragment=(
            "Treat a Fair Value Gap as a retracement zone, not a standalone entry trigger. "
            "Only consider an FVG actionable when it aligns with market structure, directional bias, "
            "and location context such as discount for longs or premium for shorts. "
            "Prefer unfilled or partially mitigated FVGs. Wait for price to retrace into the gap "
            "and show continuation intent rather than chasing displacement candles."
        ),
        guardrails=[
            "Reject setups where price never retraces into the gap.",
            "Reject setups where the FVG conflicts with higher-timeframe structure or bias.",
            "Reject setups that are not in a favorable premium/discount context.",
        ],
        tool_overrides={
            "fvg_detector": {"timeframe": "5m", "lookback_candles": 80},
            "market_structure": {"timeframe": "1h"},
            "premium_discount": {"timeframe": "4h"},
            "liquidity_analyzer": {"timeframe": "1h"},
        },
    ),
    "multi_timeframe_bias": SkillDetail(
        skill_id="multi_timeframe_bias",
        name="Multi-Timeframe Bias",
        slug="multi-timeframe-bias",
        version="1.0.0",
        description=(
            "Determine directional bias from higher-timeframe structure and momentum before lower-timeframe execution."
        ),
        category="bias",
        agent_types=["bias_agent"],
        tags=["bias", "htf", "confluence"],
        recommended_tools=["market_structure", "rsi", "macd"],
        instruction_fragment=(
            "Determine bias using higher-timeframe structure first, then use momentum tools as confirmation. "
            "If structure and momentum disagree materially, prefer NEUTRAL over forcing a directional call."
        ),
        guardrails=[
            "Use the highest-confidence higher timeframe as the anchor.",
            "Do not call a strong directional bias when structure is mixed across timeframes.",
        ],
        tool_overrides={
            "market_structure": {"timeframe": "4h"},
            "rsi": {"timeframe": "1h", "period": 14},
            "macd": {"timeframe": "1h"},
        },
    ),
}


def _build_skill_registry() -> Dict[str, SkillDetail]:
    registry = dict(_HARDCODED_SKILLS)
    for kb_skill in kb_loader.load_kb_skill_definitions():
        registry.setdefault(kb_skill.skill_id, kb_skill)
    return registry


SKILL_REGISTRY: Dict[str, SkillDetail] = _build_skill_registry()


class SkillRegistryService:
    """Provides catalog access and runtime resolution for agent skills."""

    def list_skills(self, agent_type: Optional[str] = None) -> List[SkillSummary]:
        skills = list(SKILL_REGISTRY.values())
        if agent_type:
            skills = [skill for skill in skills if agent_type in skill.agent_types]
        return [
            SkillSummary(**skill.model_dump())
            for skill in sorted(skills, key=lambda item: item.name.lower())
        ]

    def get_skill(self, skill_id: str) -> Optional[SkillDetail]:
        return SKILL_REGISTRY.get(skill_id)

    def validate_attachments(
        self,
        attachments: List[Dict[str, Any]] | List[AgentSkillAttachment],
        agent_type: str,
    ) -> List[str]:
        errors: List[str] = []
        seen: set[str] = set()

        for raw_attachment in attachments or []:
            attachment = (
                raw_attachment
                if isinstance(raw_attachment, AgentSkillAttachment)
                else AgentSkillAttachment.model_validate(raw_attachment)
            )
            if attachment.skill_id in seen:
                errors.append(f"Duplicate skill attachment '{attachment.skill_id}'")
                continue
            seen.add(attachment.skill_id)

            skill = self.get_skill(attachment.skill_id)
            if not skill:
                errors.append(f"Unknown skill '{attachment.skill_id}'")
                continue
            if skill.status != "active":
                errors.append(f"Skill '{attachment.skill_id}' is not active")
            if agent_type not in skill.agent_types:
                errors.append(
                    f"Skill '{attachment.skill_id}' cannot be attached to agent '{agent_type}'"
                )

        return errors

    def resolve_for_agent(
        self,
        *,
        agent_type: str,
        attachments: List[Dict[str, Any]] | List[AgentSkillAttachment] | None,
        base_runtime_tools: List[str],
    ) -> Dict[str, Any]:
        resolved_skills: List[SkillDetail] = []
        instruction_fragments: List[str] = []
        public_tools: List[str] = []
        runtime_tools = list(base_runtime_tools)
        runtime_tool_overrides: Dict[str, Dict[str, Any]] = {}

        for raw_attachment in attachments or []:
            attachment = (
                raw_attachment
                if isinstance(raw_attachment, AgentSkillAttachment)
                else AgentSkillAttachment.model_validate(raw_attachment)
            )
            if not attachment.enabled:
                continue

            skill = self.get_skill(attachment.skill_id)
            if not skill or skill.status != "active" or agent_type not in skill.agent_types:
                continue

            resolved_skills.append(skill)
            if skill.instruction_fragment:
                instruction_fragments.append(skill.instruction_fragment)

            for tool_name in skill.recommended_tools:
                if tool_name not in public_tools:
                    public_tools.append(tool_name)
                runtime_name = _RUNTIME_TOOL_MAP.get(tool_name)
                if runtime_name and runtime_name not in runtime_tools:
                    runtime_tools.append(runtime_name)

            for public_tool_name, params in skill.tool_overrides.items():
                runtime_name = _RUNTIME_TOOL_MAP.get(public_tool_name, public_tool_name)
                merged = dict(params or {})
                merged.update(attachment.overrides or {})
                runtime_tool_overrides[runtime_name] = merged

        return {
            "skills": resolved_skills,
            "instruction_fragments": instruction_fragments,
            "recommended_tools": public_tools,
            "runtime_tools": runtime_tools,
            "tool_overrides": runtime_tool_overrides,
        }


skill_registry = SkillRegistryService()
