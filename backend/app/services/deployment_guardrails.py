"""
Strategy Deployment Guardrails (TP-025)

Prevents premature live deployment of strategies by enforcing:
  1. Paper-first: at least N completed paper executions required
  2. Minimum win-rate floor: paper trades must meet a minimum threshold
  3. Maximum drawdown gate: reject if recent paper P&L shows >X% drawdown

Integrated into the pipeline PATCH (activation) endpoint.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution import Execution, ExecutionStatus

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Defaults (can be overridden in pipeline config under "guardrails" key)
# ---------------------------------------------------------------------------
DEFAULT_MIN_PAPER_TRADES: int = 10
DEFAULT_MIN_WIN_RATE: float   = 0.0   # 0% = disabled; set e.g. 0.40 for 40% floor
DEFAULT_MAX_DRAWDOWN: float   = 0.30  # 30% drawdown blocks live deployment


@dataclass
class GuardrailResult:
    """Outcome of a deployment guardrail check."""
    passed: bool
    failures: List[str]
    warnings: List[str]
    metrics: Dict[str, Any]


async def check_live_deployment(
    db: AsyncSession,
    pipeline_id: UUID,
    pipeline_config: Dict[str, Any],
) -> GuardrailResult:
    """
    Run all deployment guardrails before allowing a pipeline to go live.

    Args:
        db:              Async database session.
        pipeline_id:     The pipeline being activated.
        pipeline_config: Current pipeline config (for overrides under "guardrails").

    Returns:
        GuardrailResult — if `passed` is False, the activation should be blocked.
    """
    guardrail_cfg = pipeline_config.get("guardrails", {})

    min_paper  = int(guardrail_cfg.get("min_paper_trades",  DEFAULT_MIN_PAPER_TRADES))
    min_wr     = float(guardrail_cfg.get("min_win_rate",     DEFAULT_MIN_WIN_RATE))
    max_dd     = float(guardrail_cfg.get("max_drawdown_pct", DEFAULT_MAX_DRAWDOWN))

    failures: List[str] = []
    warnings: List[str] = []

    # ── Fetch recent paper executions ─────────────────────────────────
    result = await db.execute(
        select(Execution).where(
            and_(
                Execution.pipeline_id == pipeline_id,
                Execution.mode == "paper",
                Execution.status == ExecutionStatus.COMPLETED,
            )
        ).order_by(Execution.completed_at.desc()).limit(200)
    )
    paper_execs = result.scalars().all()
    paper_count = len(paper_execs)

    # ── 1. Paper-first gate ───────────────────────────────────────────
    if paper_count < min_paper:
        failures.append(
            f"Paper-first requirement not met: {paper_count}/{min_paper} completed paper "
            f"trades on record. Run more paper trades before going live."
        )

    # ── 2. Win-rate gate ─────────────────────────────────────────────
    win_rate: Optional[float] = None
    if paper_count > 0 and min_wr > 0:
        wins, total = _count_wins(paper_execs)
        win_rate = wins / total if total > 0 else 0.0
        if win_rate < min_wr:
            failures.append(
                f"Win-rate below threshold: {win_rate*100:.1f}% < {min_wr*100:.0f}% "
                f"required. Improve the strategy in paper mode first."
            )
        elif win_rate < min_wr + 0.10:
            warnings.append(
                f"Win-rate is close to the minimum threshold: {win_rate*100:.1f}% "
                f"(min: {min_wr*100:.0f}%). Monitor carefully in live mode."
            )

    # ── 3. Max drawdown gate ─────────────────────────────────────────
    peak_drawdown: Optional[float] = None
    if paper_count > 0 and max_dd < 1.0:
        peak_drawdown = _compute_max_drawdown(paper_execs)
        if peak_drawdown is not None and peak_drawdown > max_dd:
            failures.append(
                f"Paper drawdown too high: {peak_drawdown*100:.1f}% "
                f"exceeds maximum allowed {max_dd*100:.0f}%. "
                "Reduce position sizing or tighten stop rules before going live."
            )
        elif peak_drawdown is not None and peak_drawdown > max_dd * 0.75:
            warnings.append(
                f"Paper drawdown ({peak_drawdown*100:.1f}%) is approaching "
                f"the {max_dd*100:.0f}% limit. Review risk settings."
            )

    metrics = {
        "paper_trades": paper_count,
        "required_paper_trades": min_paper,
        "win_rate": round(win_rate, 4) if win_rate is not None else None,
        "required_win_rate": min_wr,
        "max_drawdown_pct": round(peak_drawdown, 4) if peak_drawdown is not None else None,
        "allowed_max_drawdown_pct": max_dd,
    }

    return GuardrailResult(
        passed=len(failures) == 0,
        failures=failures,
        warnings=warnings,
        metrics=metrics,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_wins(executions: List[Execution]):
    """Count winning trades from execution result JSON."""
    wins, total = 0, 0
    for ex in executions:
        result = ex.result or {}
        trade_outcome = result.get("trade_outcome") or {}
        pnl = trade_outcome.get("pnl")
        if pnl is not None:
            total += 1
            if float(pnl) > 0:
                wins += 1
    return wins, total


def _compute_max_drawdown(executions: List[Execution]) -> Optional[float]:
    """
    Compute peak-to-trough drawdown from a list of paper executions.

    Builds a running cumulative P&L series and returns the max drawdown fraction.
    Returns None if no P&L data is available.
    """
    pnls: List[float] = []
    for ex in sorted(executions, key=lambda e: e.completed_at or e.created_at):
        result = ex.result or {}
        trade_outcome = result.get("trade_outcome") or {}
        pnl = trade_outcome.get("pnl")
        if pnl is not None:
            pnls.append(float(pnl))

    if not pnls:
        return None

    cumulative = 0.0
    peak       = 0.0
    max_dd     = 0.0
    for p in pnls:
        cumulative += p
        if cumulative > peak:
            peak = cumulative
        if peak > 0:
            dd = (peak - cumulative) / peak
            if dd > max_dd:
                max_dd = dd

    return max_dd
