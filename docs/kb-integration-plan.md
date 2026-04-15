# Plan: Expose KB Knowledge to Trading Agents

## Context

We created a `kb/` folder with 45 markdown files (~50K tokens) covering ICT trading concepts, skills, strategies, and chart patterns. The question is: what's the best way to expose this knowledge to our AI trading agents?

**The initial idea** — one tool per KB file (30-40 tools) — is problematic because:
- LLMs degrade with >15 tools (hallucinate tool names, call wrong tools)
- KB files are **knowledge** (rules, procedures), not **computation** — tools should compute things
- 40 tool schemas add ~4K tokens of overhead on every API call even when unused
- Each tool call is a full round-trip iteration in AgentRunner, adding latency

## Recommended Approach: KB-Backed Skills with Tiered Loading

Extend the **existing Skill system** (which already has 2 hardcoded skills in `skill_registry.py`) to load KB content. Three tiers:

| Tier | Content | Loading | Token Cost |
|------|---------|---------|-----------|
| **1. Concepts** | `kb/concepts/` (8 files) | Always injected into system prompt | ~13K |
| **2. Skills + Strategies** | `kb/skills/` + `kb/strategies/` (20 files) | User-selected via skill attachments (1-5 per agent) | ~1-5K each |
| **3. Patterns** | `kb/patterns/` (17 files) | Single `pattern_reference` tool, on-demand | ~0-2K per call |

**Total tool count stays at 8-9** (current 7-8 + 1 pattern_reference). No tool explosion.

**Token budget**: ~13K (concepts) + ~5K (3 skills) + ~1.3K (system prompt) = ~19K for knowledge. Leaves 180K+ for market data, tool results, and reasoning.

### Why This Approach

| Option | Verdict | Reason |
|--------|---------|--------|
| **A. One tool per KB file (30-40 tools)** | Bad | LLMs degrade >15 tools; knowledge isn't computation; schema overhead |
| **B. Pure skill expansion** | Close | But needs tiered loading to manage token budget |
| **C. RAG retrieval** | Premature | 50K tokens fits in context; RAG adds infra + latency + relevance risk; becomes needed at 500K+ |
| **D. Tiered KB-backed skills (chosen)** | Best | Extends existing patterns; concepts always available; selective skill loading; 1 tool for patterns |

### Architecture Diagram

```
┌──────────────────────────────────────────────────────────┐
│                    Agent System Prompt                     │
│                                                          │
│  ┌─────────────────────────────────────────────────┐     │
│  │ TIER 1: Foundational Concepts (always loaded)    │     │
│  │ ~13K tokens from kb/concepts/*.md                │     │
│  │ - market-structure, liquidity, FVG, block-types  │     │
│  │ - premium-discount, displacement, time, PO3      │     │
│  └─────────────────────────────────────────────────┘     │
│                                                          │
│  ┌─────────────────────────────────────────────────┐     │
│  │ Base Agent System Prompt (existing .md files)    │     │
│  │ ~1.3K tokens                                     │     │
│  └─────────────────────────────────────────────────┘     │
│                                                          │
│  ┌─────────────────────────────────────────────────┐     │
│  │ TIER 2: Active Skills (user-selected, 1-5)      │     │
│  │ ~1-5K tokens each from kb/skills/ + strategies/  │     │
│  │ Injected via existing resolve_for_agent() flow   │     │
│  └─────────────────────────────────────────────────┘     │
│                                                          │
├──────────────────────────────────────────────────────────┤
│                    Tool Definitions                       │
│                                                          │
│  Existing tools (7-8):                                   │
│  fvg_detector, liquidity_analyzer, market_structure,     │
│  premium_discount, rsi, macd, sma_crossover, bollinger   │
│                                                          │
│  New tool (+1):                                          │
│  pattern_reference(category, pattern_name) → loads from  │
│  TIER 3: kb/patterns/ on-demand                          │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## Implementation Steps

### Step 1: Add YAML frontmatter to KB skill/strategy files

Add metadata block to each `kb/skills/*.md` and `kb/strategies/*.md` (20 files). The `instruction_fragment` will be the full file content; frontmatter provides structured metadata for registration.

```yaml
---
skill_id: kb_skill_fair_value_gap
name: Fair Value Gap
category: ict
agent_types: [strategy_agent, bias_agent]
recommended_tools: [fvg_detector, market_structure, premium_discount]
tags: [ict, fvg, imbalance, displacement]
---
```

**Files to modify**: All 10 `kb/skills/*.md` + all 10 `kb/strategies/*.md`

**Why frontmatter instead of a separate manifest**: Keeps metadata co-located with content. When someone edits a KB file, they see and can update the metadata. A separate manifest creates synchronization problems.

### Step 2: Create KBLoader service

New file: `backend/app/services/kb_loader.py`

- `KBLoader` class (singleton)
- `load_concepts() -> str` — reads and concatenates all `kb/concepts/*.md` with section headers, caches result
- `load_skill_file(relative_path: str) -> str` — loads a single KB file, caches
- `parse_frontmatter(content: str) -> (dict, str)` — extracts YAML frontmatter from markdown
- Cache is in-memory dict (KB rarely changes; invalidate on restart)
- Resolves `kb/` path relative to project root

### Step 3: Add `kb_source` field to SkillDetail schema

**File**: `backend/app/schemas/skill.py`

Add one field to `SkillDetail`:
```python
kb_source: Optional[str] = None  # e.g., "skills/fair-value-gap.md"
```

Backward-compatible — existing hardcoded skills have `kb_source=None` and work unchanged.

### Step 4: Auto-register KB files as skills in SkillRegistry

**File**: `backend/app/services/skill_registry.py`

Add `_load_kb_skills()` function that:
1. Scans `kb/skills/*.md` and `kb/strategies/*.md`
2. For each file: parse YAML frontmatter for metadata
3. Create `SkillDetail` with full file content as `instruction_fragment` and `kb_source` pointing to the file
4. Merge into `SKILL_REGISTRY` dict (existing 2 hardcoded skills kept as-is — they have manually tuned `tool_overrides`)
5. Called at module import time (same pattern as current dict initialization)

This turns the skill catalog from 2 items to ~22 items. The `GET /api/v1/skills` endpoint and UI skill picker work unchanged.

### Step 5: Add `load_kb_context()` to prompt loader

**File**: `backend/app/agents/prompts/__init__.py`

Add function:
```python
def load_kb_context() -> str:
    """Load foundational KB concepts for agent system prompts."""
    from app.services.kb_loader import kb_loader
    return kb_loader.load_concepts()
```

### Step 6: Inject concepts into agent system prompts

**Files**:
- `backend/app/agents/strategy_agent.py` (~line 274)
- `backend/app/agents/bias_agent.py` (system prompt construction)

Change is minimal — prepend concepts to system prompt:
```python
kb_context = load_kb_context()
system_prompt = kb_context + "\n\n" + load_prompt("strategy_agent_system") + skill_prompt + ...
```

**Why always load concepts**: An agent using any ICT skill needs market structure, liquidity, FVG, premium/discount knowledge. The dependency overlap is nearly 100%. The overhead of tracking concept dependencies per skill is not worth it at 13K tokens.

### Step 7: Add `pattern_reference` tool

**File**: `backend/app/tools/openai_tools.py`

Add one new tool:
- Schema: `pattern_reference(category: "harmonic"|"classic"|"candlestick", pattern_name: str)`
- Handler: loads the matching `kb/patterns/` markdown file and returns content
- Add `"pattern_reference"` to default_tools in StrategyAgent metadata

This adds exactly 1 tool (total: 8-9, well under the 15-20 threshold).

**Why a tool for patterns but not for skills/concepts**: Patterns are supplementary reference material — not always needed, and the agent should decide when to look one up. Skills and concepts are active knowledge that shapes every decision.

### Step 8: Tests

**File**: `backend/tests/test_skill_registry.py` (extend existing)

- Test KB skills are loaded and discoverable via `list_skills()`
- Test `resolve_for_agent()` injects KB content as `instruction_fragment`
- Test concepts are loaded and cached by KBLoader
- Test `pattern_reference` tool returns correct content
- Test frontmatter parsing handles edge cases

---

## Key Files Summary

| File | Action |
|------|--------|
| `kb/skills/*.md` (10 files) | Add YAML frontmatter |
| `kb/strategies/*.md` (10 files) | Add YAML frontmatter |
| `backend/app/services/kb_loader.py` | **Create** — KB file loading + caching |
| `backend/app/schemas/skill.py` | Add `kb_source` field |
| `backend/app/services/skill_registry.py` | Add `_load_kb_skills()` auto-registration |
| `backend/app/agents/prompts/__init__.py` | Add `load_kb_context()` |
| `backend/app/agents/strategy_agent.py` | Prepend concepts to system prompt |
| `backend/app/agents/bias_agent.py` | Prepend concepts to system prompt |
| `backend/app/tools/openai_tools.py` | Add `pattern_reference` tool |
| `backend/tests/test_skill_registry.py` | Extend with KB skill tests |

## Token Budget Analysis

With a 200K model context window:

| Component | Tokens | Notes |
|-----------|--------|-------|
| Concepts (always) | ~13K | 8 files, foundational knowledge |
| System prompt | ~1.3K | Strategy agent prompt |
| Skill fragments (1-5 attached) | ~3-7K | User selects, typically 2-3 |
| Tool schemas (8-9 tools) | ~1K | Function calling overhead |
| Market data | ~15-25K | Candles, indicators, bias context |
| Tool call results | ~5-10K | Computed analysis from tools |
| User instructions | ~0.5K | Pipeline config |
| **Total used** | **~40-60K** | |
| **Remaining for reasoning** | **~140-160K** | 70-80% of context free |

## Verification

1. **Unit tests**: Run `docker exec -it clovercharts-backend pytest tests/test_skill_registry.py -v`
2. **API check**: `GET /api/v1/skills` should return ~22 skills (2 existing + 20 KB-backed)
3. **API check**: `GET /api/v1/skills?agent_type=strategy_agent` should filter correctly
4. **Pipeline test**: Create a pipeline with StrategyAgent, attach 2-3 KB skills, run execution — verify skill instructions appear in agent reasoning
5. **Token check**: Log the total system prompt length in StrategyAgent to verify it stays under 25K tokens with concepts + 3 skills attached

## Future Extensions

- **Database-backed skills**: Move from file-based to DB-stored skills for user-created custom skills
- **Skill versioning**: Track versions when KB files change
- **Skill marketplace**: Allow users to share/publish custom skills
- **Smart concept loading**: If token budget becomes tight, load only concepts referenced by attached skills
- **RAG upgrade**: If KB grows past ~200K tokens, add embedding-based retrieval as a fallback
