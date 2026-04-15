from pathlib import Path

from app.agents import get_registry
from app.orchestration.validator import PipelineValidator
from app.services.kb_loader import KBLoader
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
    assert any(skill.skill_id == "kb_skill_fair_value_gap" for skill in skills)
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


def test_kb_loader_parses_frontmatter_and_body():
    parsed = KBLoader.parse_frontmatter(
        """---
skill_id: kb_skill_test
name: Test Skill
category: ict
agent_types: [strategy_agent, bias_agent]
recommended_tools: [market_structure, fvg_detector]
tags: [ict, test]
---

# Test Skill

Body text.
"""
    )

    assert parsed.metadata["skill_id"] == "kb_skill_test"
    assert parsed.metadata["agent_types"] == ["strategy_agent", "bias_agent"]
    assert parsed.metadata["recommended_tools"] == ["market_structure", "fvg_detector"]
    assert parsed.body.startswith("# Test Skill")


def test_kb_loader_loads_skills_and_ignores_strategies(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    strategies_dir = tmp_path / "strategies"
    concepts_dir = tmp_path / "concepts"
    skills_dir.mkdir(parents=True)
    strategies_dir.mkdir()
    concepts_dir.mkdir()

    (skills_dir / "skill-a.md").write_text(
        """---
skill_id: kb_skill_alpha
name: Alpha Skill
category: ict
agent_types: [strategy_agent]
recommended_tools: [market_structure]
---

# Alpha

Alpha body.
""",
        encoding="utf-8",
    )
    (strategies_dir / "strategy-a.md").write_text(
        """---
skill_id: kb_strategy_should_be_ignored
name: Ignored Strategy
category: strategy
agent_types: [strategy_agent]
recommended_tools: [market_structure]
---

# Ignored
""",
        encoding="utf-8",
    )

    loader = KBLoader(kb_root=tmp_path)
    skills = loader.load_kb_skill_definitions()

    assert [skill.skill_id for skill in skills] == ["kb_skill_alpha"]
    assert skills[0].kb_source == "skills/skill-a.md"


def test_kb_loader_loads_concepts_for_supported_agents():
    loader = KBLoader()

    bias_bundle = loader.load_concepts_bundle("bias_agent")
    second_bias_bundle = loader.load_concepts_bundle("bias_agent")
    risk_bundle = loader.load_concepts_bundle("risk_manager_agent")

    assert bias_bundle == second_bias_bundle
    assert "FOUNDATIONAL ICT CONCEPTS" in bias_bundle
    assert "KB Concept: Fair Value Gap" in bias_bundle
    assert risk_bundle == ""


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
