"""
KB loader for markdown-backed concepts and skills.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from app.schemas.skill import SkillDetail


def _coerce_frontmatter_value(raw_value: str) -> Any:
    value = raw_value.strip()
    if not value:
        return ""
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip("'\"") for item in inner.split(",") if item.strip()]
    if value.startswith("{") and value.endswith("}"):
        return {}
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    return value.strip("'\"")


def _extract_description(body: str) -> str:
    for block in body.split("\n\n"):
        line = block.strip()
        if not line or line.startswith("#"):
            continue
        return " ".join(line.split())
    return "KB-backed trading skill"


def _slugify(value: str) -> str:
    return (
        value.lower()
        .replace("&", "and")
        .replace("/", "-")
        .replace("(", "")
        .replace(")", "")
        .replace(" ", "-")
    )


@dataclass(frozen=True)
class ParsedMarkdown:
    metadata: Dict[str, Any]
    body: str


class KBLoader:
    """Loads and caches knowledge base markdown content."""

    _CONCEPT_AGENT_TYPES = {"bias_agent", "strategy_agent"}

    def __init__(self, kb_root: Path | None = None):
        self.kb_root = kb_root or Path(__file__).resolve().parents[2] / "kb"
        self._concept_bundle_cache: Dict[str, str] = {}
        self._skill_cache: List[SkillDetail] | None = None

    @staticmethod
    def parse_frontmatter(content: str) -> ParsedMarkdown:
        if not content.startswith("---\n"):
            return ParsedMarkdown(metadata={}, body=content.strip())

        marker = "\n---\n"
        end_index = content.find(marker, 4)
        if end_index == -1:
            raise ValueError("Invalid frontmatter: missing closing '---'")

        metadata_block = content[4:end_index].strip()
        body = content[end_index + len(marker):].strip()
        metadata: Dict[str, Any] = {}

        for line in metadata_block.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if ":" not in stripped:
                raise ValueError(f"Invalid frontmatter line: {line}")
            key, raw_value = stripped.split(":", 1)
            metadata[key.strip()] = _coerce_frontmatter_value(raw_value)

        return ParsedMarkdown(metadata=metadata, body=body)

    def load_concepts_bundle(self, agent_type: str) -> str:
        if agent_type not in self._CONCEPT_AGENT_TYPES:
            return ""
        if agent_type in self._concept_bundle_cache:
            return self._concept_bundle_cache[agent_type]

        concepts_dir = self.kb_root / "concepts"
        sections: List[str] = []
        for path in sorted(concepts_dir.glob("*.md")):
            content = path.read_text(encoding="utf-8").strip()
            sections.append(f"## KB Concept: {path.stem.replace('-', ' ').title()}\n\n{content}")

        bundle = ""
        if sections:
            bundle = "# FOUNDATIONAL ICT CONCEPTS\n\n" + "\n\n".join(sections)

        self._concept_bundle_cache[agent_type] = bundle
        return bundle

    def load_kb_skill_definitions(self) -> List[SkillDetail]:
        if self._skill_cache is not None:
            return self._skill_cache

        skills_dir = self.kb_root / "skills"
        skill_definitions: List[SkillDetail] = []
        for path in sorted(skills_dir.glob("*.md")):
            content = path.read_text(encoding="utf-8")
            parsed = self.parse_frontmatter(content)
            metadata = parsed.metadata
            missing = [
                key
                for key in ("skill_id", "name", "category", "agent_types", "recommended_tools")
                if not metadata.get(key)
            ]
            if missing:
                raise ValueError(
                    f"KB skill '{path.name}' missing required frontmatter fields: {', '.join(missing)}"
                )

            skill_definitions.append(
                SkillDetail(
                    skill_id=str(metadata["skill_id"]),
                    name=str(metadata["name"]),
                    slug=str(metadata.get("slug") or _slugify(str(metadata["name"]))),
                    version=str(metadata.get("version") or "1.0.0"),
                    description=str(metadata.get("description") or _extract_description(parsed.body)),
                    category=str(metadata["category"]),
                    agent_types=list(metadata["agent_types"]),
                    tags=list(metadata.get("tags") or []),
                    recommended_tools=list(metadata["recommended_tools"]),
                    instruction_fragment=parsed.body,
                    guardrails=list(metadata.get("guardrails") or []),
                    tool_overrides=dict(metadata.get("tool_overrides") or {}),
                    kb_source=str(path.relative_to(self.kb_root)),
                )
            )

        self._skill_cache = skill_definitions
        return skill_definitions


kb_loader = KBLoader()
