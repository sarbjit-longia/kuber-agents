# TODOS

Captured during /plan-eng-review on 2026-04-27, scope = `docs/office-hours-design-20260427.md` Phase 1 demo sprint.

Format: each TODO has What, Why, Pros, Cons, Context, Depends on. Keep that structure when adding more.

---

## TODO-1 — Refactor `SignalGeneratorService` (1200+ lines)

**What:** Refactor `SignalGeneratorService` (currently 1200+ lines in `signal-generator/app/main.py:70`) into smaller classes by responsibility: config, Redis bus, generators, telemetry, lifecycle. Methods `_initialize_kafka` (now `_initialize_redis` post-Phase-1) and `_initialize_generators` (line 262, ~480 lines long) are the largest pain points.

**Why:** One-class-does-everything pattern slows down future changes. The Phase 1 Redis Streams swap will surface this — touching the file makes the size painful in a way that working around it hides.

**Pros:**
- Easier to test (smaller surfaces)
- Easier to extend with new signal types
- Smaller PRs going forward

**Cons:**
- 1-3 days of refactor with no immediate user benefit
- Behavioral neutral — risk of regression if not careful

**Context:**
- Class spans lines 70-1255 in `signal-generator/app/main.py`
- After Phase 1, `_initialize_redis_streams` (the renamed Kafka init) becomes a clean candidate to extract first
- Similar size pressure may exist in `trigger-dispatcher/app/main.py` — re-evaluate at the same time

**Depends on:** Phase 1 Redis Streams swap landing first (so this work doesn't double-touch the file).

---

## TODO-2 — Expand `trigger-dispatcher` test coverage to full pipeline-matching logic

**What:** Expand `trigger-dispatcher` test coverage from Phase 1's Redis Streams tests to full coverage of `TriggerDispatcher.match_signals_to_pipelines` and the rest of the consumer behavior.

**Why:** Pipeline matching is a hot path executed on every signal. It is currently untested. Phase 1 adds Redis Streams I/O tests but leaves the matching logic uncovered. Future bugs in matching are silent failures (signals fired but wrong pipelines triggered).

**Pros:**
- Catch matching bugs in CI rather than production
- Maps to the "well-tested code is non-negotiable" preference
- Sets up cleaner refactoring later

**Cons:**
- 1-2 days of test writing for code that is currently working
- Test fixtures for pipeline matching are non-trivial (need DB fixtures, signal fixtures, pipeline subscription configs)

**Context:**
- `trigger-dispatcher/app/main.py:237` `match_signals_to_pipelines` is untested today
- `trigger-dispatcher/tests/` directory exists but is empty as of 2026-04-27
- Phase 1 will create `trigger-dispatcher/tests/test_consumer.py` and `conftest.py`; this TODO is to expand from there

**Depends on:** Phase 1 Redis Streams swap (so the test fixture infrastructure exists from TODO-2's foundation).

---

## TODO-3 — Re-add Prometheus + Grafana + `redis_exporter` for Phase 3 production launch

**What:** Re-add `prometheus`, `grafana`, and `redis_exporter` services to `deploy/local/docker-compose.prod.yml`. Wire Grafana dashboards:
- Redis (community dashboard ID 763 or 11835)
- kuber-agents app metrics (from existing Backend Prometheus instrumentation)
- Celery/queue metrics
- OANDA broker latency
- Stream consumer lag (`stream_pending_count`, XPENDING-derived)

**Why:** Phase 1 strips these for the demo footprint. Phase 3 launches with real partner usage, and ops debugging without dashboards is slow and error-prone. Captures the trip hazard so the team doesn't launch blind.

**Pros:**
- Production-grade observability for partner phase
- Restores parity with the original `docker-compose.prod.yml` design
- `redis_exporter` is required for the consumer-lag dashboard after the Redis Streams swap

**Cons:**
- 1-2 days to re-stand-up plus dashboard wiring
- Adds back ~512 MB + 256 MB to the Hetzner footprint (acceptable on CCX33 if upgrading; tight on CCX23)

**Context:**
- Stripped during Phase 1 per design doc and Issue 1C decision
- `redis_exporter` is a NEW service (not present in original `docker-compose.prod.yml`) needed because Phase 1 swapped Kafka → Redis Streams
- Time to re-add: at start of Phase 3 build (Week 7), before any partner goes live

**Depends on:** ≥3 deposits landing (= Phase 3 trigger).

---

## TODO-4 — Run `/design-consultation` to produce `DESIGN.md` (DONE 2026-04-27)

**Status:** Shipped. File at `docs/DESIGN.md`.

**What shipped:** Full design system covering aesthetic direction (Industrial-Editorial hybrid), typography (Instrument Serif / Cabinet Grotesk / Instrument Sans / JetBrains Mono — replaces Inter), color (single warm-gold accent `#C9A96E` replacing cyan/teal gradient, dark-mode primary), spacing (8px base scale), layout (12-column grid + editorial breakouts), motion (intentional, restrained, reduced-motion-aware), and SCSS migration plan from existing `styles.scss`.

**Note:** Originally scoped as "post-Phase-1" but ran inline at the end of the planning session. The system reflects existing reference patterns (marketplace eyebrow+hero, execution-report-modal section structure, mat-icon vocabulary) plus deliberate departures (drop Inter, drop cyan/teal gradient).

**SCSS migration is still pending** — listed as Phase 1 build work in the design doc, ~1 day of careful CSS work + visual QA across all existing screens. Track migration progress against the "SCSS migration plan" section in `docs/DESIGN.md`.

---

## TODO-5 — Mobile responsive audit + a11y formalization for demo flow

**What:** Audit and fix mobile/tablet UX + accessibility for the demo flow surfaces:
- `/strategies/marketplace`
- `/strategies/:id`
- `/my-strategies`
- `/pipelines` and `/pipelines/:id`
- `/monitoring`
- `execution-report-modal`

Specifically: mobile-first viewport breakpoints, keyboard navigation patterns, ARIA landmarks, color contrast (target WCAG AA 4.5:1 for body text), touch target sizes (44×44 px minimum on mobile).

**Why:** Phase 1 demos are desktop-screen-share via Zoom. Phase 2 prospects re-visiting the demo URL on mobile (some retail traders are mobile-heavy) must not bounce due to broken responsive behavior. Conversion math breaks if mobile is unusable.

**Pros:**
- Conversion-safe across devices
- A11y compliance reduces legal exposure (some jurisdictions require it)
- Cleaner Phase 3 launch

**Cons:**
- 1-2 days of audit + fixes

**Context:**
- `/plan-design-review` 2026-04-27 rated Pass 6 (Responsive & Accessibility) at 5/10 due to no mobile/a11y spec in the plan
- Material components are responsive and a11y-aware by default, but custom CSS often breaks both — must verify per surface

**Depends on:** Phase 1 demo shipped.

---

## TODO-6 — Project-level `/quantum` slash command for one-shot home-server deploys (DONE 2026-04-27)

**Status:** Shipped. File at `.claude/commands/quantum.md`.

**What shipped:** Slash command exposing 6 subcommands that map to `deploy/local/deploy.sh` CLI: `status`, `health`, `migrate`, `rollback`, `sync`, `logs <service>`. Plus `full` (tells user to run interactive script directly — interactive deploy steps require human confirmation and aren't safe to automate from chat) and `help` (lists subcommands).

**Behavior rules baked in:**
- Subcommand whitelist (no inventing new subcommands)
- Destructive ops (`rollback`) require confirmation before running
- `migrate` flags that it runs against production DB
- `logs` without service name returns help instead of dropping into interactive mode
- After-action summary on success; verbatim error + suggested next step on failure

**Future work if needed (not blocking anything today):**
- A `.claude/skills/quantum-deploy/SKILL.md` if multi-step interactive flows ever need to embed in other skills (e.g., a "deploy + run smoke test + report" pipeline). For now the slash command is sufficient.
- Add to CLAUDE.md skill-routing rules so suggestions like "deploy to quantum" auto-route to `/quantum` (low priority — solo-founder workflow).
