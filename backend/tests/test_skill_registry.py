from app.agents import get_registry
from app.orchestration.validator import PipelineValidator
from app.services.skill_registry import skill_registry


def test_strategy_agent_metadata_supports_skills():
    registry = get_registry()
    metadata = registry.get_metadata("strategy_agent")

    assert metadata is not None
    assert metadata.supports_skills is True
    assert "ict" in metadata.supported_skill_categories


def test_skill_registry_lists_agent_skills():
    skills = skill_registry.list_skills(agent_type="strategy_agent")

    assert any(skill.skill_id == "ict_fvg_retracement" for skill in skills)
    assert all("strategy_agent" in skill.agent_types for skill in skills)


def test_skill_registry_resolves_runtime_tools():
    resolved = skill_registry.resolve_for_agent(
        agent_type="strategy_agent",
        attachments=[{"skill_id": "ict_fvg_retracement", "enabled": True, "overrides": {}}],
        base_runtime_tools=["rsi_calculator"],
    )

    runtime_tools = resolved["runtime_tools"]

    assert "rsi_calculator" in runtime_tools
    assert "fvg_detector" in runtime_tools
    assert "market_structure_analyzer" in runtime_tools
    assert resolved["instruction_fragments"]


def test_pipeline_validator_rejects_unknown_skill_attachment():
    pipeline_config = {
        "nodes": [
            {
                "id": "node-strategy",
                "agent_type": "strategy_agent",
                "config": {
                    "instructions": "Test strategy",
                    "skills": [
                        {"skill_id": "missing_skill", "enabled": True, "overrides": {}}
                    ],
                },
            },
        ],
        "edges": [],
    }

    validator = PipelineValidator()
    ok, errors = validator.validate(pipeline_config)

    assert ok is False
    assert any("Unknown skill 'missing_skill'" in error for error in errors)

