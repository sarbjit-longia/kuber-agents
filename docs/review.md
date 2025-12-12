# Project Review (Living Doc)

**Purpose**: Continuously review work landing in this repo (from humans and other coding agents), capture architectural alignment vs. `docs/`, and keep a short, actionable “next steps” list.

**Last updated**: 2025-12-11

---

## Current snapshot (what exists + what’s working)

### Backend (FastAPI + agents + orchestration)
- **Agent discovery is implemented** via `backend/app/agents/registry.py` + `/api/v1/agents` (`backend/app/api/v1/agents.py`), returning `AgentMetadata` with JSON-schema config for dynamic UI forms.
- **Execution reporting is implemented at the state level** (`agent_reports` in `PipelineState`) and is serialized into the `executions.reports` column by the orchestrator (`backend/app/orchestration/executor.py`).
- **Scanner + signal-trigger plumbing is present** in the data model (`Pipeline.trigger_mode`, `Pipeline.scanner_id`, `signal_subscriptions`) and in the scanners CRUD API (`backend/app/api/v1/scanners.py`).

### Signal System (event-driven trigger mode)
- **`signal-generator/`**: Emits signals and publishes to Kafka when available, with Prometheus/OpenTelemetry metrics.
- **`trigger-dispatcher/`**: Consumes Kafka, maintains an in-memory cache of active signal pipelines, matches by (tickers ∩ scanner tickers) + subscription + confidence, checks running executions, then enqueues Celery tasks. Design-wise, this matches `docs/services/signal-system.md` and `docs/services/scanner.md`.

### Observability
- OpenTelemetry + Prometheus + Grafana docs are detailed and appear consistent with the multi-service architecture (`docs/services/monitoring.md`).

---

## Alignment check vs. project philosophy (agent-first, async-first, immutable state)

### What’s aligned
- **Agent-first logic is mostly respected**: agents expose metadata/config schema and operate on a shared `PipelineState`.
- **Marketplace-ready primitives exist**: metadata + pricing rate fields + dynamic config schemas are already part of the core types.

### Where we’re drifting (important)
- **State immutability**: the current `PipelineState` is mutated in-place (e.g., `state.add_log(...)`, `state.add_cost(...)`, `state.add_report(...)`). This conflicts with the repo rule “Agents receive state, return new state (don’t mutate)”.
  - Recommendation: either (A) formally adopt “mutable state” (update docs/rules accordingly), or (B) refactor agents/orchestrator to return a new `PipelineState` copy and treat state as immutable.
- **Async-first**: base agent `process()` is synchronous today. If we want “async-first everywhere”, we should standardize on `async def process(...)` for agents (or at least for any I/O agent/tool interactions).

---

## Notable product/architecture gaps (vs requirements/roadmap)

### 1) Reporting Agent appears missing from the registry
Docs/roadmap call out a “Reporting Agent” as part of the MVP chain, but the backend agent registry currently registers:
- `TimeTriggerAgent`, `MarketDataAgent`, `BiasAgent`, `StrategyAgent`, `RiskManagerAgent`, `TradeManagerAgent`

**Gap**: there’s no registered “Reporting Agent” class, even though the orchestrator supports `agent_reports`.

**Next step**: either implement/register `ReportingAgent`, or update docs/roadmap to reflect the intended reporting model (state-level reports only, no agent).

### 2) Time trigger agent status vs. “signal system” direction
Docs suggest time-trigger is deprecated / replaced by the signal system. The code still registers `TimeTriggerAgent` and still has time-trigger related tooling.

**Next step**: decide whether:
- we keep `TimeTriggerAgent` as the implementation of `TriggerMode.PERIODIC` (recommended), or
- we fully deprecate it and move periodic triggering entirely to Celery Beat/orchestrator without a trigger-agent node.

### 3) LLM tool detection endpoint exists but isn’t in the design narrative
`/api/v1/agents/validate-instructions` introduces an LLM-powered tool detection workflow (strategy instructions → detected tools + cost estimate).

**Risks**:
- **Cost tracking**: this path estimates LLM cost but does not appear to persist it in the platform’s cost tracking tables.
- **Budget enforcement / rate limiting**: not obviously enforced here; could become an abuse vector.
- **Model choice**: hard-coded `gpt-4` use may be expensive for a “helper” endpoint.

**Next step**: document this feature explicitly and align it with cost/budget enforcement requirements (or gate it behind tier/budget).

---

## Data model/doc mismatch (small but should be cleaned up)

The scanner documentation describes a `tickers` JSONB column on `scanners`, but the current implementation uses:
- `scanners.config` (JSONB) which contains `{"tickers": [...]}`.

This is not a functional problem, but it’s easy to confuse future contributors and downstream services. Prefer updating docs to match reality (`config.tickers`) or migrating schema to match docs.

---

## Quality/engineering gaps to keep watching

### Testing coverage
Roadmap explicitly notes unit coverage goals were deferred. With multiple services (backend, data-plane, signal-generator, trigger-dispatcher), regression risk is increasing.

**Near-term goal**: add targeted tests around:
- `/api/v1/agents` metadata contracts (schema shape stability)
- scanner CRUD + scanner usage validation
- signal matching logic (confidence thresholds + “skip running pipelines”)

### Consistency of types across frontend/backend
`AgentMetadata` is pivotal for UI form generation. Any drift in schema fields (e.g., `pricing_rate`, `requires_timeframes`, tool support fields) will break the pipeline builder.

**Policy**: treat `AgentMetadata` as a stable API contract; add a contract test.

---

## Next steps (ranked, concrete)

1. **Decide on state immutability vs. mutation** and make docs + code consistent (this decision impacts every future agent).
2. **Clarify “trigger agent” architecture**:
   - keep `TimeTriggerAgent` as the periodic trigger node (UI-visible), or
   - make periodic pipelines “scheduler-driven” (UI-hidden) and remove the trigger node.
3. **Close the “Reporting Agent” gap**:
   - implement + register a `ReportingAgent`, or
   - update docs to define reporting as orchestrator/state responsibility only.
4. **Bring tool-detection into the cost/budget system**:
   - persist LLM usage in `cost_tracking`,
   - enforce budget/tier rules,
   - consider cheaper model defaults (or caching).
5. **Add contract tests** for `/api/v1/agents` and scanner + signal trigger matching.

---

## Monitoring checklist (use this when reviewing new agent PRs/changes)

- **Agent additions**
  - Includes `get_metadata()` with JSON-schema config
  - Registered in agent registry
  - Has tests (happy path + failure path)
  - Declares `requires_timeframes` accurately
  - Avoids untracked LLM/tool costs
- **API changes**
  - `/api/v1/agents` response schema unchanged (or versioned)
  - Authz rules consistent (public vs authenticated endpoints is intentional)
- **Signal/scanner changes**
  - Matching logic unchanged or tested (tickers, confidence, subscription types)
  - Back-compat for deprecated `scanner_tickers` preserved until migration complete
- **Cost system changes**
  - LLM calls tracked and persisted
  - Budget enforcement consistent across API + background workers




