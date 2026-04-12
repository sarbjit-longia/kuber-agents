# Backtesting Implementation Review

> **Date:** 2026-04-11
> **Scope:** Code review and rating of the backtesting system implemented in `backend/app/backtesting/`, covering isolation, scalability, replay fidelity, API design, observability, resilience, test coverage, and code quality.

---

## Architecture Overview

The system is a three-layer design:

1. **Control plane** (FastAPI + PostgreSQL) — REST API, concurrency limit enforcement, pipeline/runtime snapshot freezing, `BacktestRun` lifecycle management
2. **Ephemeral runtime** — per-backtest isolated process (Celery task, Docker container, or Kubernetes Job)
3. **Replay engine** — timestamp-driven signal → pipeline → broker loop

```
POST /backtests
  → BacktestRun created (PENDING, with pipeline/runtime snapshots)
  → launch_backtest_runtime (Celery task)
    → Selects launcher: legacy_shared | docker_container | kubernetes_job
      → Ephemeral runtime: runtime_main.py
        → BacktestOrchestrator.run_backtest()
          → For each timestamp in timeline:
            1. Replay signals (signal-generator at historical ts)
            2. Match signals to pipeline (runtime_dispatcher.py)
            3. Execute pipeline inline (no Celery queue)
            4. Evaluate broker positions on bar
          → Compute metrics, persist, done
```

### Key Files

| File | Purpose |
|------|---------|
| `backend/app/backtesting/backtest_broker.py` | Redis-backed simulated broker (slippage, commission, SL/TP, PnL) |
| `backend/app/backtesting/orchestrator.py` | Timestamp-driven replay loop, timeline construction, metrics computation |
| `backend/app/backtesting/runtime_dispatcher.py` | Signal-to-pipeline matching (mirrors live trigger-dispatcher logic) |
| `backend/app/backtesting/runtime_launcher.py` | Strategy pattern: legacy_shared / docker_container / kubernetes_job |
| `backend/app/backtesting/runtime_main.py` | Ephemeral container entry point |
| `backend/app/backtesting/snapshot.py` | Pipeline config and LLM settings snapshot freezing |
| `backend/app/orchestration/tasks/run_backtest.py` | Celery task for Phase 1 (legacy_shared) execution |
| `backend/app/orchestration/tasks/launch_backtest_runtime.py` | Launcher Celery task — selects and starts runtime |
| `backend/app/api/v1/backtests.py` | REST endpoints + three-tier concurrency limit enforcement |
| `backend/app/models/backtest_run.py` | `BacktestRun` ORM model with status enum and JSONB columns |
| `backend/app/schemas/backtest.py` | Pydantic schemas: Create, Summary, Result, Progress |
| `signal-generator/app/utils/backtest_context.py` | `ContextVar` for per-request historical timestamp isolation |

---

## Ratings by Category

### 1. Isolation from Live Environment — 9/10

**What's working:**
- **Redis namespacing**: every key scoped to `backtest:{run_id}:{account|positions|trades}` — zero cross-run leakage
- **Pipeline snapshot freezing** at creation time: agent prompts, LLM model settings (temperature, base_url), and prompt SHA256 hashes are all captured — live config changes mid-run have no effect
- `mode="backtest"` flag threads through `PipelineExecutor`: skips live PDF generation, live broker calls, and live exchange connections
- **Signal-generator uses `ContextVar`** (`_backtest_ts`) for per-request timestamp isolation — concurrent backtests cannot leak timestamps to each other
- **Data-plane calls pass `backtest_ts`** query param so historical OHLCV data is returned instead of live quotes
- `BacktestBroker` never connects to a real exchange

**Gaps:**
- Embedded signal-generator failure is silent: if `/opt/signal-generator` is unavailable, the system falls back to the network signal-generator which may serve live data
- Redis keys are unencrypted (acceptable for in-cluster deployments, not for multi-tenant SaaS)

---

### 2. Scalability / Concurrency — 6/10

**What's working:**
- Three-tier concurrency limits, all configurable via environment variables:
  - `BACKTEST_MAX_ACTIVE_RUNS_PER_USER` (default 2)
  - `BACKTEST_MAX_ACTIVE_RUNS_PER_PIPELINE` (default 1)
  - `BACKTEST_MAX_ACTIVE_RUNS_GLOBAL` (default 100)
- Returns HTTP 429 (rate limit) vs 409 (conflict) correctly
- DB indexes on `(user_id, status)`, `(pipeline_id, status)`, and `status` alone make concurrency limit queries fast
- Launcher strategy pattern is clean and extensible — Docker and K8s launchers are implemented stubs ready for activation
- K8s `Job` spec is well-formed: TTL, restart policy, env injection, `activeDeadlineSeconds` safety net

**Critical gap:**
- **Default launcher is `legacy_shared`** — a single Celery queue. This means only one backtest runs at a time system-wide, regardless of the concurrency limits. The 100-run global limit is meaningless until Phase 2 launchers are activated.
- Signal replay and pipeline execution are fully synchronous — no per-symbol parallelism within a single run
- K8s Job spec has no CPU or memory resource limits defined

**Verdict:** The _design_ supports high concurrency; the _default configuration_ is sequential. Changing `BACKTEST_RUNTIME_MODE` to `docker_container` or `kubernetes_job` is the single biggest unlock.

---

### 3. Replay Fidelity / Parity with Live — 8/10

**What's working:**
- Signal replay calls the actual signal-generator service at a historical timestamp — same code path as live signal detection
- `runtime_dispatcher.py` mirrors the live `trigger-dispatcher` matching logic exactly (subscription filters, confidence thresholds, timeframe checks)
- `execute_pipeline_inline()` reuses `PipelineExecutor` directly — same agent logic, same prompt templates, no separate code path
- LLM model, temperature, and base_url are snapshot-frozen — model upgrades cannot affect in-progress backtests
- Timestamp-driven timeline ensures signals only see data available at that exact point in historical time

**Gaps:**
- Only `fixed` and `percentage` slippage models — no volume-weighted or market-impact slippage, which underestimates fill costs for large orders
- Signal execution is synchronous (one symbol at a time), while live signals can be concurrent — minor timing difference in multi-symbol strategies
- Equity curve is appended once per symbol per bar rather than once per timestamp, inflating its length

---

### 4. API & Database Design — 8/10

**What's working:**
- `BacktestRun` uses UUID primary key, JSONB columns for `config`, `progress`, `metrics`, `trades`, `equity_curve` — flexible schema that doesn't require migrations for new fields
- Clear `status` lifecycle: PENDING → RUNNING → COMPLETED / FAILED / CANCELLED
- Separate endpoints for summary (`GET /backtests/{id}`) and full results (`GET /backtests/{id}/results`) — avoids sending large trade arrays on list views
- Pydantic schemas cleanly separate Create, Summary, Result, and Progress concerns
- Cascade delete on `user_id` FK prevents orphaned backtest runs
- Cost estimation included at creation time (heuristic: ~100 executions/symbol/month × $0.075)

**Gaps:**
- No pagination on `GET /backtests` list — will return thousands of rows for active users
- No filtering by status or date range on the list endpoint
- Cost estimation is a heuristic and doesn't account for signal density or model cost variance
- `actual_cost` field exists in the model but is never checked against `max_cost_usd` during execution — the limit is decorative

---

### 5. Observability & Debugging — 7/10

**What's working:**
- `progress` JSONB updated every 25 bars or 2 seconds — provides a real-time progress view for the UI
- `metrics` JSONB captures full performance analytics at completion: Sharpe ratio, max drawdown, win rate, average trade duration
- `trades` JSONB stores complete trade history for post-run analysis
- `equity_curve` persisted for charting
- `config.runtime` stores container/pod names and launcher details for debugging failed runs

**Gaps:**
- No structured logging of wall-clock time per bar or per signal batch — impossible to identify which timestamp caused a slowdown
- `actual_cost` is tracked in the model but not enforced or surfaced meaningfully during execution
- Cancellation is only checked at timestamp boundaries — if a single LLM call hangs inside a pipeline execution, the cancellation request is blocked until that call completes

---

### 6. Resilience & Error Handling — 5/10

**What's working:**
- Explicit status transitions with error states (PENDING → RUNNING → COMPLETED/FAILED)
- Celery task error handlers mark the run as FAILED and persist the error message
- K8s `activeDeadlineSeconds` (default 1800s) provides a hard stop for runaway jobs

**Critical gaps:**
- **No checkpoint/resume**: if a 10-hour backtest crashes at hour 9, it must restart from the beginning. The K8s deadline of 30 minutes makes this especially risky for long date ranges.
- Cancellation polling is at timestamp boundaries only — a hanging LLM call or slow data-plane response blocks cancellation for its entire duration
- No retry logic for transient signal-generator or data-plane failures during replay — a single network blip fails the entire run
- `DockerContainerBacktestLauncher.stop()` is an incomplete stub — cannot actually stop a running Docker container backtest

---

### 7. Test Coverage — 6/10

**What's covered:**
- `test_backtests_api.py`: snapshot creation, concurrency limit enforcement, cancellation endpoint
- `test_backtest_snapshot.py`: agent config capture, prompt hashing, LLM settings freezing
- `test_backtest_runtime_launcher.py`: K8s Job spec construction, Docker env injection, stop operations

**Gaps:**
- No tests for `BacktestOrchestrator` — the core timestamp-driven replay loop is entirely untested
- No tests for `BacktestBroker` — slippage, commission, SL/TP evaluation, and PnL calculation are untested
- No integration test covering the full signal replay → pipeline execution → broker evaluation cycle
- Concurrency limit enforcement tested at the API layer only, not at the DB query level

---

### 8. Code Quality — 8/10

**What's working:**
- Lazy import pattern in `__init__.py` files avoids circular imports at container startup
- Strategy Pattern for `BacktestRuntimeLauncher` is clean and extensible
- `execute_pipeline_inline()` is a clever reuse of `PipelineExecutor` without Celery queue overhead
- `_env_int()` helper for safe environment variable parsing with sane defaults
- Type hints throughout, Pydantic validation on all API boundaries
- Status enum with clear transitions and meaningful naming

**Gaps:**
- `runtime_dispatcher.py` duplicates the live `trigger-dispatcher` signal-matching logic — two places to maintain when matching rules change
- `LegacySharedBacktestLauncher.stop()` logs "not supported" silently rather than raising, masking cancellation failures
- Equity curve double-append is a latent bug (appended once per closed trade and once unconditionally per symbol per bar)

---

## Summary Scorecard

| Category | Score | Verdict |
|----------|-------|---------|
| Isolation from live | **9/10** | Production-ready |
| Scalability / Concurrency | **6/10** | Design is right; default config is sequential |
| Replay fidelity | **8/10** | Strong; slippage models need expansion |
| API & DB design | **8/10** | Solid; needs pagination and cost enforcement |
| Observability | **7/10** | Good foundation; missing per-bar perf logging |
| Resilience | **5/10** | No checkpoint/resume — risky for runs > 30 min |
| Test coverage | **6/10** | API layer tested; core logic untested |
| Code quality | **8/10** | Clean patterns; minor duplication |
| **Overall** | **7.1/10** | Strong foundation; Phase 2 launchers are the key unlock |

---

## Must-Fix Before Shipping

1. **Change `BACKTEST_RUNTIME_MODE` default** from `legacy_shared` to `docker_container` or `kubernetes_job` — this is the single biggest gap blocking real concurrency
2. **Add bar-level Redis checkpoints** in `BacktestOrchestrator` to allow resume after crash — needed for any backtest over 1 hour
3. **Write tests for `BacktestOrchestrator` and `BacktestBroker`** — these are the highest-risk untested components
4. **Fail loudly** if embedded signal-generator is requested but unavailable — never silently fall back to live network mode
5. **Add pagination and status filtering** to `GET /backtests` list endpoint before it's publicly used

## Nice-to-Have Improvements

- Volume-weighted or market-impact slippage model in `BacktestBroker`
- Per-bar wall-clock timing in the `metrics` JSONB for performance profiling
- Async signal dispatch per symbol within a single run for faster multi-symbol backtests
- Extract shared signal-matching logic from `runtime_dispatcher.py` into a shared library used by both backtesting and live `trigger-dispatcher`
- Enforce `max_cost_usd` against `actual_cost` during execution to prevent runaway LLM spend
- Complete `DockerContainerBacktestLauncher.stop()` so Docker-mode backtests can be cancelled
