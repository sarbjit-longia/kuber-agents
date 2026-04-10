# Trading Platform Review And Upgrade Plan

## Scope

This review focuses on the implemented backend trading platform, especially:

- Agent pipeline design in `backend/app/agents/`
- Orchestration in `backend/app/orchestration/`
- Risk, execution, approvals, and monitoring flows
- Signal-driven architecture across backend, `signal-generator/`, `trigger-dispatcher/`, and documented `data-plane/`

Target use case for this plan:

- Retail users
- Swing trading and intraday trading
- Candle-based decision making
- Timeframes `>= 1m`
- Not intended for HFT or microsecond-sensitive execution

---

## Executive Assessment

This codebase already has the bones of a serious retail trading platform:

- Good event-driven architecture
- Strong service decomposition
- Real broker abstraction
- Real execution lifecycle states
- Signal/scanner model that can scale
- Good monitoring and observability direction

The main weakness is that the most important part of the product, the trade decision path, is still too LLM-dependent and too nondeterministic for production trading. The current platform is stronger as an AI-assisted signal orchestration product than as a reliable systematic trading product.

If the goal is a platform that users can trust for swing and intraday trading, the upgrade path should be:

1. Make market structure, signal qualification, and risk controls deterministic first.
2. Keep LLMs in explanation, ranking, and strategy authoring roles, not final mechanical execution logic.
3. Add research, backtesting, walk-forward validation, and portfolio risk controls before expanding strategy complexity.

Bottom line:

- Architecture foundation: good
- Production trading reliability: moderate
- Research and validation layer: weak
- Upgrade potential: high

---

## Evidence-Based Review

### What Is Good

#### 1. The event-driven architecture is the right one

The combination of signal generators, Kafka, trigger dispatcher, Celery workers, scanners, and pipeline execution is a strong foundation for sub-daily trading. This is aligned with how practical candle-based trading systems should operate.

Evidence:

- `docs/design.md`
- `backend/app/orchestration/executor.py`
- `backend/app/models/pipeline.py`
- `trigger-dispatcher/README.md`
- `signal-generator/app/generators/`

Why it is good:

- Good separation of signal creation from trade execution
- Scales better than naive polling
- Fits both intraday and swing workflows
- Lets you add new signals without rewriting the OMS layer

#### 2. Data architecture direction is strong

The documented data-plane design with 1-minute storage, higher timeframe aggregates, caching, and pre-computed indicators is exactly what a non-HFT trading platform needs.

Evidence:

- `docs/design.md`
- `data-plane/README.md`

Why it is good:

- 1-minute base data is enough for the target use case
- Derived higher timeframes are efficient and practical
- Centralized data reduces duplicated indicator calls
- Better for consistency between scanners, agents, and execution

#### 3. Broker abstraction and execution-state modeling are above MVP quality

The broker factory and execution model are not toy code. There is real thought around duplicate prevention, monitoring, reconciliation, approvals, and communication error states.

Evidence:

- `backend/app/services/brokers/factory.py`
- `backend/app/models/execution.py`
- `backend/app/agents/trade_manager_agent.py`
- `backend/app/orchestration/tasks/execute_pipeline.py`
- `backend/app/orchestration/tasks/monitoring.py`

Why it is good:

- Supports multiple brokers and asset classes
- Handles monitoring and not just order placement
- Uses state snapshots and recovery flows
- Includes human approval workflow for live/paper modes

#### 4. Signal breadth is already strong

The platform has broad signal coverage:

- `29` generator modules in `signal-generator/app/generators/`
- `70` signal types in `backend/app/schemas/signal.py`

This is a strong catalog for building watchlist- and regime-aware systems.

#### 5. Product thinking is better than a pure quant sandbox

There are scanners, subscriptions, notifications, reports, approvals, and execution dashboards. That matters if this is intended for real users instead of just research users.

Evidence:

- `backend/app/api/v1/`
- `backend/app/services/executive_report_generator.py`
- `backend/app/api/v1/executions.py`
- `backend/app/api/v1/approvals.py`

---

### What Is Bad

#### 1. Core trade generation is too nondeterministic

Bias, strategy, and risk are still driven too much by prompting, text parsing, and fallback cleanup logic. That is acceptable for analyst assistance. It is not enough for a production trading engine.

Evidence:

- `backend/app/agents/bias_agent.py`
- `backend/app/agents/strategy_agent.py`
- `backend/app/agents/risk_manager_agent.py`

Specific problems:

- Strategy parsing relies on JSON extraction and regex fallback.
- Reasoning is post-processed and re-synthesized.
- Risk sizing uses LLM output parsing for mechanical quantities.
- Fallback logic is doing operational work that should be deterministic.

This creates failure modes such as:

- inconsistent entries and exits
- instruction drift
- malformed output handling
- behavior that changes with model or prompt updates

#### 2. The platform currently mixes “AI analyst” and “execution engine” responsibilities

A good retail trading platform should separate:

- deterministic rule engine
- strategy specification layer
- explanation layer
- execution layer

Right now those concerns bleed into each other.

Example:

- LLMs effectively decide concrete trade levels and risk actions
- deterministic tools are secondary helpers instead of primary decision makers

That is backward for a production system.

#### 3. There is a real docs-vs-code and tests-vs-code drift problem

The repository still contains old trigger-agent assumptions even though the architecture says trigger agents were replaced by signal systems.

Evidence:

- `backend/app/agents/__init__.py` does not register `TimeTriggerAgent`
- `backend/app/orchestration/validator.py` still requires `time_trigger` for periodic pipelines
- `backend/tests/test_agent_pipeline.py`
- `backend/tests/test_agents.py`
- `backend/tests/test_orchestration.py`
- `docs/context.md`
- `docs/design.md`

This is not cosmetic. It means the platform contract is not clean enough yet.

#### 4. Some important strategy tools are partial or placeholder quality

Evidence:

- `backend/app/tools/strategy_tools/indicator_tools.py`

Examples:

- SMA crossover result is effectively stubbed with zeros and TODOs
- RSI divergence flags are TODO placeholders

This is a warning sign because the strategy layer presents itself as richer than the deterministic implementation underneath.

#### 5. There are still fail-open paths in places where fail-safe is preferable

Evidence:

- `backend/app/agents/trade_review_agent.py`

If the review LLM fails, the agent defaults to `APPROVED`. That is convenient operationally but wrong for a live-trading risk posture.

For live trading:

- review failure should block or downgrade to manual approval
- not silently lean toward approval

#### 6. Several exit and execution controls are unfinished

Evidence:

- `backend/app/agents/trade_manager_agent.py`

Examples:

- webhook sending is TODO
- VIX/news/market-crash emergency logic is TODO
- commission capture is TODO

This is manageable, but it confirms the platform is still between advanced MVP and full production.

#### 7. Neutral-bias handling is too rigid for a complete product

Evidence:

- `backend/app/agents/strategy_agent.py`

Current behavior skips strategy generation when bias is neutral. That makes sense for trend-following systems, but it blocks:

- range trading
- mean reversion
- opening range reversion
- fade setups
- volatility compression breakout setups before bias expansion

A serious user platform needs strategy archetypes with different regime logic, not one universal “neutral means hold” rule.

#### 8. There is almost no real research platform yet

Missing or weak:

- backtesting engine
- slippage and commission simulation
- walk-forward testing
- Monte Carlo robustness
- parameter stability analysis
- portfolio-level exposure simulation
- regime performance breakdown

Without this, users can create pipelines, but they cannot properly validate them.

---

## Ratings

| Area | Rating (1-10) | Why |
|---|---:|---|
| Architecture and service decomposition | 8 | Good separation across API, execution, signals, data, brokers, monitoring |
| Data plane direction | 8 | Strong fit for 1m+ candle trading, centralized indicators, caching |
| Signal generation breadth | 8 | Wide signal catalog and scalable event-driven model |
| Scanner and trigger model | 7 | Good concept and flow, but some implementation/docs drift |
| Pipeline orchestration | 7 | Real execution state model, Celery integration, recovery flows |
| Broker abstraction | 7 | Good multi-broker foundation, practical for retail execution |
| Position monitoring and reconciliation | 7 | Better than average MVP, but still has TODOs and edge-case risk |
| Risk management engine | 5 | Good intent, but too LLM-driven for mechanical sizing and controls |
| Strategy engine reliability | 4 | Too prompt- and parser-dependent for production trust |
| Deterministic technical analytics | 5 | Some tools are useful, some are partial/stubbed |
| Backtesting and research capability | 2 | Major gap for systematic strategy validation |
| Portfolio risk and capital allocation | 3 | Mostly trade-level, not portfolio-level |
| Test suite reliability and freshness | 3 | Clear stale assumptions around `time_trigger` and older APIs |
| Documentation alignment with implementation | 4 | Strong docs exist, but they are not fully synchronized with code |
| Readiness for swing-trading users | 6 | Closer to usable with good UX and risk controls |
| Readiness for intraday users | 5 | Usable foundation, but strategy determinism and research layer are not strong enough |

---

## Comparison To Standard Trading System Patterns

### Pattern A: Discretionary Trader Assistant

What it looks like:

- scans markets
- summarizes setups
- suggests entries/exits
- trader confirms manually

How this platform compares:

- Strong fit today
- The current LLM-heavy design is acceptable here
- This is the closest thing the product already does well

Rating against this pattern: `8/10`

### Pattern B: Rules-Based Automated Candle Trading System

What it looks like:

- deterministic entry rules
- deterministic exits
- deterministic position sizing
- clear session and regime filters
- backtest before live deployment

How this platform compares:

- Strong architecture base
- Weak deterministic strategy core
- weak research validation layer

Rating against this pattern: `4/10`

### Pattern C: Multi-Strategy Retail Trading Platform

What it looks like:

- multiple strategy archetypes
- separate logic for trend, breakout, mean reversion, swing
- portfolio risk engine
- journaling and analytics
- broker and notification integrations

How this platform compares:

- Good product skeleton
- not enough deterministic strategy templates
- not enough portfolio/risk orchestration

Rating against this pattern: `5/10`

### Pattern D: Institutional-Style OMS/EMS

What it looks like:

- order routing sophistication
- smart execution
- low-latency market microstructure optimization
- venue-aware fills

How this platform compares:

- Not the target, and it does not need to be
- Current level is fine for the stated product goals

Rating against target needs: `Not required`

---

## Strategic Direction Recommendation

The best upgrade path is not “add more AI”.

The best path is:

- deterministic market and risk engine first
- LLM as strategy authoring, explanation, ranking, and review layer
- strong backtesting and validation layer
- portfolio-level controls
- clean user-facing strategy templates for swing and intraday

Recommended operating model:

1. Signal layer finds opportunities.
2. Deterministic setup engine validates entries/exits using candle rules.
3. Deterministic risk engine sizes and filters trades.
4. LLM explains, ranks, or proposes rule templates.
5. Execution engine handles approvals, routing, monitoring, reconciliation.

That architecture is much safer and much easier to test.

---

## Target Product Capabilities

To become a strong user-facing swing and intraday platform, the product should support these strategy families well:

### Swing Trading

- daily and 4h trend following
- breakout and pullback continuation
- multi-day mean reversion
- earnings/news risk filters
- market regime filters using index and sector context

### Intraday Trading

- 1m, 3m, 5m, 15m execution logic
- opening range breakout
- VWAP pullback and reclaim/reject
- trend continuation after pullback
- range fade and failed breakout
- volatility and liquidity filters
- session-aware controls

### Cross-Cutting Controls

- deterministic stop, target, and trailing-stop models
- max daily loss
- max concurrent positions
- sector and correlation limits
- exposure caps by asset class and side
- slippage-aware backtest/live consistency

---

## Phased Upgrade Plan

## Phase 0: Correctness And Platform Alignment

Goal:

- remove architecture drift
- make the platform internally consistent
- reduce false confidence

## Phase 1: Deterministic Trading Core

Goal:

- move core trade qualification, entry rules, and risk sizing out of prompt parsing

## Phase 2: Research And Validation

Goal:

- let users and internal teams prove a strategy before live use

## Phase 3: Production Trading Controls

Goal:

- strengthen execution safety and real-world usability

## Phase 4: Portfolio And User Product Maturity

Goal:

- evolve from single-trade automation into a serious multi-strategy platform

---

## Ticket Roadmap

| ID | Phase | Area | Ticket | Current Problem | Upgrade Outcome | Depends On | Priority |
|---|---|---|---|---|---|---|---|
| TP-001 | 0 | Architecture | Remove legacy `time_trigger` dependency from validator and docs | `backend/app/orchestration/validator.py` still requires `time_trigger` while `backend/app/agents/__init__.py` no longer registers it | Periodic pipelines are validated against actual architecture | None | P0 |
| TP-002 | 0 | Testing | Rewrite stale agent/orchestration tests to match current agent registry and periodic/signal model | Tests reference `TimeTriggerAgent` and older market data assumptions | Test suite becomes trustworthy again | TP-001 | P0 |
| TP-003 | 0 | Docs | Align `docs/context.md` and `docs/design.md` with implemented execution order and trade review stage | Current docs still show removed concepts and omit some real behavior | Engineering and agents work from one contract | TP-001 | P1 |
| TP-004 | 0 | Quality | Add architecture conformance checks in CI for registered agents, validator rules, and docs snippets | Drift is currently manual and repeated | Prevents stale architectural assumptions from reappearing | TP-001, TP-002 | P1 |
| TP-005 | 1 | Strategy Engine | Introduce deterministic strategy specification schema | Strategy output is LLM JSON plus regex fallback parsing in `backend/app/agents/strategy_agent.py` | Strategy logic becomes machine-valid and testable | TP-001 | P0 |
| TP-006 | 1 | Strategy Engine | Build deterministic setup evaluators for core strategy families | Current setup generation is mostly prompt-driven | Users get reproducible strategies for ORB, pullback, breakout, mean reversion, swing continuation | TP-005 | P0 |
| TP-007 | 1 | Bias/Regime | Split bias into deterministic regime filters instead of free-form LLM synthesis | Bias is useful but too subjective and globally enforced | Trend, range, volatility, and session regime become explicit controls | TP-005 | P0 |
| TP-008 | 1 | Risk Engine | Replace LLM-based position sizing with deterministic risk formulas and policy rules | `backend/app/agents/risk_manager_agent.py` parses text to get size and warnings | Stable risk sizing across runs and models | TP-005 | P0 |
| TP-009 | 1 | Risk Engine | Add portfolio-level risk controls | Current risk is mostly single-trade | Control total exposure, side imbalance, sector concentration, and correlation | TP-008 | P0 |
| TP-010 | 1 | Strategy Tools | Finish incomplete technical tools and remove placeholder outputs | `indicator_tools.py` has TODO/stub logic for SMA/divergence | Tool layer becomes reliable input for deterministic strategies | TP-005 | P1 |
| TP-011 | 1 | LLM Usage | Reposition LLMs to strategy authoring, explanation, ranking, and anomaly review only | LLMs currently sit too close to the execution-critical path | Better safety without losing AI usefulness | TP-005, TP-008 | P1 |
| TP-012 | 1 | Review Gate | Change trade review failure mode from fail-open to fail-safe for live trading | `trade_review_agent.py` defaults to approval on LLM failure | Safer live-trading posture | TP-011 | P0 |
| TP-013 | 1 | Strategy Catalog | Create first-party strategy templates by trading style | Product lacks standardized swing/intraday archetypes | Faster onboarding and better consistency | TP-006, TP-007, TP-008 | P1 |
| TP-014 | 2 | Backtesting | Build event-driven backtest engine on the same candle/timeframe primitives as live trading | No true research layer exists | Users can validate rules on historical candles using the same logic as production | TP-005, TP-006, TP-008 | P0 |
| TP-015 | 2 | Backtesting | Add commissions, slippage, and partial-fill simulation | Current design is too optimistic without execution frictions | Research becomes closer to live performance | TP-014 | P0 |
| TP-016 | 2 | Validation | Add walk-forward testing and out-of-sample validation | No systematic defense against overfitting | Better production readiness and user trust | TP-014 | P1 |
| TP-017 | 2 | Analytics | Add regime, session, ticker, and timeframe performance breakdowns | Users currently cannot see where a strategy actually works | Faster refinement of swing vs intraday systems | TP-014 | P1 |
| TP-018 | 2 | Analytics | Add trade journal and post-trade classification engine | Reports exist, but not a deep feedback loop | Platform learns from execution quality and setup quality | TP-014 | P2 |
| TP-019 | 3 | Execution | Implement real webhook delivery, retries, and delivery receipts | `trade_manager_agent.py` still has webhook TODOs | Reliable external automation integration | TP-001 | P1 |
| TP-020 | 3 | Execution | Complete advanced exit controls: trailing stops, break-even logic, time stops, session exits | Current exits are basic and some emergency logic is TODO | Better intraday and swing trade lifecycle control | TP-008 | P0 |
| TP-021 | 3 | Execution | Add session-aware execution policies | Platform targets candle trading but does not yet fully encode session logic | Better handling of open, lunch, close, overnight, and weekend risk | TP-006, TP-020 | P0 |
| TP-022 | 3 | Execution | Add spread, liquidity, and volatility pre-trade filters | Current trade path can still approve setups in poor execution conditions | Fewer low-quality fills and better live robustness | TP-008, TP-021 | P1 |
| TP-023 | 3 | Reconciliation | Harden monitoring and reconciliation against broker/API edge cases | Monitoring is already decent but still has TODOs and recovery complexity | More reliable closure state and P&L reporting | TP-020 | P1 |
| TP-024 | 3 | Market Context | Implement deterministic market-wide risk controls using index, VIX, and scheduled-event filters | Emergency exit hooks exist but are TODOs | Better behavior in abnormal market conditions | TP-007, TP-020 | P1 |
| TP-025 | 4 | Product | Add strategy deployment guardrails: paper-first, min sample size, max drawdown gates | Users can otherwise activate weak strategies too early | Safer retail user experience | TP-014, TP-016 | P0 |
| TP-026 | 4 | Product | Add portfolio dashboard for active risk, heat, sector load, and strategy overlap | Current experience is execution-centric, not portfolio-centric | More serious user operating layer | TP-009 | P1 |
| TP-027 | 4 | Product | Add copyable first-party playbooks for swing and intraday users | Platform is flexible but may feel too open-ended | Better activation and retention | TP-013, TP-025 | P1 |
| TP-028 | 4 | Product | Add strategy marketplace contract for deterministic templates, not just prompt instructions | Current “agent marketplace” idea is compelling but risky if prompt-only | Safer extensibility model | TP-005, TP-013 | P2 |
| TP-029 | 4 | Compliance/Risk | Add kill-switches and user-level emergency circuit breakers | Needed before scale in live trading | Faster operational containment of user and platform risk | TP-020, TP-023 | P0 |
| TP-030 | 4 | ML/AI | Add model quality monitoring for any remaining AI-assisted stages | LLM usage will remain, but should be monitored | Detects drift in ranking/explanation/review quality | TP-011 | P2 |

---

## Recommended Delivery Order

If resources are limited, do not start with “more strategies”.

Start in this order:

1. `TP-001` to `TP-004`
2. `TP-005`, `TP-006`, `TP-007`, `TP-008`, `TP-012`
3. `TP-014`, `TP-015`, `TP-016`
4. `TP-020`, `TP-021`, `TP-023`, `TP-029`
5. Portfolio, templates, and marketplace work after that

This sequence converts the platform from an AI-driven demo engine into a real trading product foundation.

---

## Suggested Strategy Template Set

These should be first-party deterministic templates, not prompt-only templates.

### Intraday Templates

- Opening Range Breakout
- VWAP Pullback Continuation
- First Pullback In Trend
- Range Fade At Extremes
- Failed Breakout Reversal
- Volatility Compression Breakout

### Swing Templates

- Daily Trend Pullback
- Breakout Retest Continuation
- 4H/Daily Momentum Continuation
- Mean Reversion To Moving Average
- Weekly Support Bounce With Daily Confirmation

Each template should define:

- valid market regime
- allowed timeframes
- exact entry trigger
- stop logic
- target logic
- time-based invalidation
- position sizing model
- asset universe filters

---

## Final Recommendation

This platform should not try to compete on execution speed. That is not the right battlefield.

It should compete on:

- clean event-driven architecture
- strong deterministic candle-based strategy engine
- high-quality retail user workflows
- safe automation with human approvals where needed
- strong research-to-live consistency

Right now the platform is best described as:

- a strong trading-automation foundation
- a promising AI-assisted trader workstation
- not yet a fully trustworthy systematic swing/intraday trading platform

With the phase plan above, it can become one.
