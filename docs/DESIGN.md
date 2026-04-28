# Design System — kuber-agents

Created by `/design-consultation` on 2026-04-27. This is the source of truth for visual decisions. Read it before any UI work. Update the Decisions Log when anything changes.

## Product Context

- **What this is:** AI agent-based trading platform where retail traders describe strategies in plain English, watch multiple AI agents reason about each trade, and audit every decision through rich reports. Multi-broker (OANDA / Alpaca / Tradier) with paper-trading default.
- **Who it's for:** Side-hustle retail trader with a tech day job. Account size $25K–$150K. Trades options/futures evenings/early mornings. Time-poor, money-OK, technically fluent. Has already crossed the automation chasm (TradingView Pine Script / 3Commas / custom Python).
- **Space/industry:** Retail algorithmic trading + AI tooling. Peers: Public.com (agentic brokerage, autonomous), Trader.ai (40 AI agents across asset classes), TradingView (charts), 3Commas / TraderspoSt (bot platforms), QuantConnect (algorithmic IDE).
- **Project type:** Hybrid web app + dashboard. Marketing surfaces (marketplace, strategy detail) lean editorial; functional surfaces (monitoring, pipelines, executions) lean industrial.

## Memorable Thing

> *"AI that thinks out loud about your money — and you can audit every decision."*

Every design decision serves this. The "thinks out loud" part demands transparency surfaces (rich reports, streaming agent activity). The "audit every decision" part demands editorial gravitas in those moments — this is not a casino dashboard, it's a thoughtful tool.

## Aesthetic Direction

- **Direction:** **Industrial-Editorial hybrid**. Industrial for data/app screens (monitoring, pipelines, executions, scanner). Editorial for moments-of-significance (executive reports, marketplace landing, strategy detail).
- **Decoration level:** **Intentional**. Subtle paper-grain or noise overlay on editorial moments only. Zero decoration on data screens. Material icons throughout.
- **Mood:** Authoritative without being cold. Premium without being flashy. The product has opinions and explains them — a thinking partner, not a gambling app.
- **Anti-positioning:** Avoid the AI-trading purple gradient. Avoid Robinhood's consumer-green energy. Avoid TradingView's wall-of-charts density-only approach. Avoid every other Material-Angular SaaS look.
- **Reference posture:** Bloomberg Terminal authority + Stripe Dashboard craft + Linear's restraint. Closer to "newspaper" than "casino."

## Typography

All fonts are loaded from **Bunny Fonts** (privacy-respecting Google Fonts mirror, free). Fallback stack always ends in `system-ui, sans-serif`.

- **Display (editorial moments):** **Instrument Serif** — Executive Summary heading in execution-report-modal, strategy detail H1, marketplace hero. Serif evokes newspaper authority. Weights: 400 regular, 400 italic.
- **Display (app/utility):** **Cabinet Grotesk** — page H1s in app screens (monitoring, pipelines, my-strategies). Distinctive geometric sans, more personality than Inter. Weights: 700 bold, 800 extrabold.
- **Body:** **Instrument Sans** — same foundry as Instrument Serif, coherent system. All body copy, labels, buttons. Weights: 400, 500, 600.
- **Data/code:** **JetBrains Mono** with `font-feature-settings: "tnum"` (tabular-nums). Prices, P&L, percentages, agent reasoning code blocks, strategy descriptions in plain English. Weight: 400, 500.

**REPLACES Inter** entirely. Inter is on the overused-fonts list and the convergence trap for fintech apps.

**Loading:**
```html
<link rel="preconnect" href="https://fonts.bunny.net">
<link href="https://fonts.bunny.net/css?family=instrument-serif:400,400i|instrument-sans:400,500,600|cabinet-grotesk:700,800|jetbrains-mono:400,500&display=swap" rel="stylesheet">
```

**Type scale (modular, ratio 1.25):**

| Level | Size | Line height | Use |
|-------|------|-------------|-----|
| Display XL | 48px (3rem) | 1.1 | Marketplace hero (Instrument Serif) |
| Display L | 36px (2.25rem) | 1.15 | Page H1 (Cabinet Grotesk) |
| Display M | 28px (1.75rem) | 1.2 | Section heading, executive summary heading (Instrument Serif) |
| H1 | 24px (1.5rem) | 1.3 | Modal heading, dialog |
| H2 | 20px (1.25rem) | 1.35 | Subsection |
| H3 | 18px (1.125rem) | 1.4 | Card heading |
| Body L | 16px (1rem) | 1.5 | Default body |
| Body | 14px (0.875rem) | 1.5 | Compact body, table cells |
| Caption | 12px (0.75rem) | 1.4 | Metadata, footnotes |
| Mono L | 16px (1rem) | 1.5 | Tabular data, code blocks |
| Mono | 14px (0.875rem) | 1.5 | Inline metrics |

## Color

**Approach: Restrained.** Single accent. Neutrals carry the visual weight. Color is rare and meaningful. Dark mode is primary; light mode supported.

### Dark mode (primary)

| Token | Hex | Usage |
|-------|-----|-------|
| `--bg-primary` | `#0A0E1A` | Page background — deep blue-black, more authoritative than pure black |
| `--bg-surface` | `#14182A` | Cards, primary surface |
| `--bg-elevated` | `#1F2438` | Modals, dialogs, popovers, interactive surfaces |
| `--bg-hover` | `#2A3050` | Hover states on interactive surfaces |
| `--text-primary` | `#F5F7FA` | Body text |
| `--text-muted` | `#8B95A8` | Secondary text, labels |
| `--text-subtle` | `#5A6378` | Tertiary text, disabled |
| `--border-subtle` | `rgba(245, 247, 250, 0.08)` | Card borders, dividers |
| `--border-strong` | `rgba(245, 247, 250, 0.16)` | Focus outlines, prominent dividers |
| `--accent` | `#C9A96E` | **Single brand accent — warm gold** |
| `--accent-bg` | `rgba(201, 169, 110, 0.12)` | Accent backgrounds, highlights |
| `--accent-bg-hover` | `rgba(201, 169, 110, 0.18)` | Accent hover |

### Light mode (supported)

| Token | Hex |
|-------|-----|
| `--bg-primary` | `#F5F7FA` |
| `--bg-surface` | `#FFFFFF` |
| `--bg-elevated` | `#FFFFFF` (with shadow) |
| `--bg-hover` | `#EDF0F5` |
| `--text-primary` | `#0A0E1A` |
| `--text-muted` | `#5A6378` |
| `--text-subtle` | `#8B95A8` |
| `--border-subtle` | `rgba(10, 14, 26, 0.08)` |
| `--border-strong` | `rgba(10, 14, 26, 0.16)` |
| `--accent` | `#9C7E3E` (slightly desaturated for light bg readability) |

### Semantic colors (P&L data only — never as brand)

Existing values in `styles.scss` retained:

| Token | Hex | Usage |
|-------|-----|-------|
| `--color-success` | `#34d399` | Profitable trades, success states |
| `--color-warning` | `#f6c453` | Risk warnings, paper-trading badge |
| `--color-error` | `#fb7185` | Loss states, errors |
| `--color-info` | `#60a5fa` | Informational, neutral status |
| `--color-success-bg` | `rgba(52, 211, 153, 0.14)` | Success surface tint |
| `--color-warning-bg` | `rgba(246, 196, 83, 0.14)` | Warning surface tint |
| `--color-error-bg` | `rgba(251, 113, 133, 0.14)` | Error surface tint |
| `--color-info-bg` | `rgba(96, 165, 250, 0.14)` | Info surface tint |

**Rule:** semantic colors apply only to P&L data, status badges, and form validation. They never become brand surfaces. The brand accent is gold; everything else is neutrals.

### Accent gold usage rules

The warm gold (`#C9A96E`) is used **sparingly, with intent**:
- Primary CTA buttons at moments of weight: Import, Activate, Submit Deposit
- Executive Report's "Final Recommendation" highlight bar
- "Agent Consensus" pill when full agreement (use neutrals for partial)
- Marketplace hero CTA
- Active state on primary navigation

**Never** use gold for:
- Body text (contrast issues)
- Decorative gradients (no `linear-gradient(gold-blue)` — that's the AI slop trap)
- Status badges (those use semantic colors)
- More than ~5% of any screen's pixel area

## Spacing

- **Base unit:** 8px
- **Density:** comfortable on editorial surfaces, compact on data screens

| Token | Value |
|-------|-------|
| `--space-2xs` | 4px |
| `--space-xs` | 8px |
| `--space-sm` | 12px |
| `--space-md` | 16px |
| `--space-lg` | 24px |
| `--space-xl` | 32px |
| `--space-2xl` | 48px |
| `--space-3xl` | 64px |

## Layout

- **Approach:** Hybrid — strict grid for app screens, editorial breakouts allowed for marketplace + report executive summary.
- **Grid:** 12 columns, 24px gutter (16px on tablet, 12px on mobile).
- **Max content width:** 1280px (app), 1080px (editorial reading widths).
- **Breakpoints:** mobile (<640px), tablet (640–1024px), desktop (>1024px).

### Border radius (hierarchical)

| Token | Value | Use |
|-------|-------|-----|
| `--radius-sm` | 4px | Cards, list items |
| `--radius-md` | 8px | Panels, larger surfaces |
| `--radius-lg` | 12px | Modals, dialogs |
| `--radius-pill` | 9999px | Status badges, consensus pill, chip elements |

**Rule:** never use the same radius on every element ("uniform bubble radius" is on the AI slop blacklist). Hierarchy is intentional.

## Motion

- **Approach:** Intentional, restrained. Motion serves comprehension and signals state — never decoration.
- **Easing:**
  - `--ease-out: cubic-bezier(0.16, 1, 0.3, 1)` — entrances, modal-open, expansion
  - `--ease-in: cubic-bezier(0.7, 0, 0.84, 0)` — exits
  - `--ease-in-out: cubic-bezier(0.83, 0, 0.17, 1)` — interactive state changes
- **Duration:**
  - `--motion-instant: 50ms` — focus rings, hover states
  - `--motion-short: 150ms` — color/opacity transitions
  - `--motion-medium: 300ms` — modal/dialog transitions, panel expansion
  - `--motion-long: 500ms` — welcome animations, first-load reveals
- **Specific patterns:**
  - Agent reasoning streaming feed (per `/plan-design-review` Issue 3A): each agent event slides in with `translateY(8px) → translateY(0)` over 200ms with `ease-out`
  - Modal open/close: 300ms `ease-out` opacity + scale (0.96 → 1.0)
  - Empty-state CTAs: subtle pulse on first render only
- **Forbidden:** scroll-jacking, parallax, particle effects, looping ambient animations, motion that triggers without user intent.
- **Accessibility:** respect `prefers-reduced-motion: reduce` — all motion above 200ms reduces to instant or 100ms.

## Component Vocabulary (existing — preserve)

These patterns already exist in the codebase and are part of the system:

- **Hero with eyebrow:** `eyebrow chip + h1 + body + CTA` (see `strategies-marketplace.component.html:8`)
- **Loading / error / content state:** `*ngIf="loading"`, `*ngIf="error && !loading"`, `*ngIf="content && !loading"` (see `execution-report-modal.component.html:14`)
- **Mat-icon vocabulary:** `summarize`, `lightbulb`, `flag`, `show_chart`, `psychology`, `warning`, `storefront`, `ios_share`, `folder`, `check_circle`, `error`, `info`, `download`, `open_in_new` — established and consistent
- **Section divider:** `<mat-divider>` between report sections
- **Accordion for nested detail:** `mat-accordion` + `mat-expansion-panel` (Detailed Agent Analysis)
- **Modal footer pattern:** Cancel button + secondary action + primary CTA (right-aligned)
- **Overview-strip cards:** small label + large value (see marketplace overview-strip)

When adding new patterns, check this list first. Reuse before invent.

## SCSS migration plan (Phase 1+ work, not immediate)

Existing `styles.scss` (693 lines) currently uses Inter + cyan/teal gradient + Material cyan/teal palette. Migration to this system happens during Phase 1 build:

1. Replace `font-family: 'Inter'` with the Bunny Fonts loading + the new stack (`Instrument Sans` body, `Cabinet Grotesk` for app H1, `Instrument Serif` for editorial H1)
2. Replace `--accent-primary: #56c2ff` and `--accent-secondary: #2bd4b3` with single `--accent: #C9A96E`
3. Remove `--accent-gradient` (cyan-to-teal gradient is AI slop)
4. Adjust `--bg-primary: #0b0f14` → `#0A0E1A`
5. Add `--bg-surface`, `--bg-elevated`, `--bg-hover` tokens
6. Update `--shadow-accent` to use gold
7. Update Material palette mixin (currently `mat.$cyan-palette` + `mat.$teal-palette`) to a custom palette derived from gold
8. Add type scale custom properties
9. Add radius scale custom properties
10. Add motion custom properties

Estimate: 1 day of careful CSS work + visual QA across all existing screens.

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-27 | Initial system created | `/design-consultation` after `/office-hours` + `/plan-eng-review` + `/plan-design-review`. Departs from Inter + cyan/teal gradient (existing baseline) toward Industrial-Editorial with warm gold accent. Memorable thing: "AI that thinks out loud about your money — and you can audit every decision." |
