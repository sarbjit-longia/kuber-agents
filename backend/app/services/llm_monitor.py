"""
LLM Decision Quality Monitoring (TP-030)

Tracks distributions of LLM-produced decisions (bias, strategy, trade review)
over recent executions to detect drift, degradation, or runaway patterns.

Metrics tracked per pipeline:
  - Bias distribution: BULLISH / BEARISH / NEUTRAL counts and ratios
  - Strategy action distribution: BUY / SELL / HOLD ratios
  - Trade review distribution: APPROVED / REJECTED / HOLD ratios
  - Average confidence levels
  - Anomaly flags: e.g., >90% APPROVED suggests reviewer is rubber-stamping

This data is exposed via GET /dashboard/llm-quality so operators can
spot model drift before it affects live trading.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution import Execution, ExecutionStatus

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Thresholds for anomaly detection
# ---------------------------------------------------------------------------
BIAS_CONCENTRATION_THRESHOLD    = 0.85  # Alert if >85% of biases are the same
APPROVAL_RATE_HIGH_THRESHOLD    = 0.95  # Alert if review approves >95% of trades
APPROVAL_RATE_LOW_THRESHOLD     = 0.10  # Alert if review approves <10% (over-restrictive)
HOLD_RATE_HIGH_THRESHOLD        = 0.70  # Alert if strategy produces >70% HOLDs
MIN_SAMPLE_FOR_ANOMALY          = 10    # Don't flag anomalies with fewer samples


@dataclass
class LLMQualityReport:
    """Quality metrics for LLM-driven stages in a set of executions."""
    pipeline_id: Optional[str]
    sample_size: int
    bias_distribution: Dict[str, int] = field(default_factory=dict)
    strategy_distribution: Dict[str, int] = field(default_factory=dict)
    review_distribution: Dict[str, int] = field(default_factory=dict)
    avg_bias_confidence: Optional[float] = None
    avg_strategy_confidence: Optional[float] = None
    avg_review_confidence: Optional[float] = None
    anomalies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pipeline_id": self.pipeline_id,
            "sample_size": self.sample_size,
            "bias": {
                "distribution": self.bias_distribution,
                "avg_confidence": self.avg_bias_confidence,
            },
            "strategy": {
                "distribution": self.strategy_distribution,
                "avg_confidence": self.avg_strategy_confidence,
            },
            "review": {
                "distribution": self.review_distribution,
                "avg_confidence": self.avg_review_confidence,
            },
            "anomalies": self.anomalies,
            "health": "warning" if self.anomalies else "ok",
        }


async def compute_quality_report(
    db: AsyncSession,
    user_id: UUID,
    pipeline_id: Optional[UUID] = None,
    limit: int = 100,
) -> LLMQualityReport:
    """
    Compute LLM quality metrics from recent completed executions.

    Args:
        db:           Async DB session.
        user_id:      Filter to this user's executions.
        pipeline_id:  Optionally filter to a specific pipeline.
        limit:        Max executions to analyse (most recent first).

    Returns:
        LLMQualityReport with distributions and anomaly flags.
    """
    q = select(Execution).where(
        Execution.user_id == user_id,
        Execution.status == ExecutionStatus.COMPLETED,
    )
    if pipeline_id:
        q = q.where(Execution.pipeline_id == pipeline_id)
    q = q.order_by(Execution.completed_at.desc()).limit(limit)

    result = await db.execute(q)
    executions = result.scalars().all()

    report = LLMQualityReport(
        pipeline_id=str(pipeline_id) if pipeline_id else None,
        sample_size=len(executions),
    )

    if not executions:
        return report

    bias_counts: Dict[str, int]     = defaultdict(int)
    strategy_counts: Dict[str, int] = defaultdict(int)
    review_counts: Dict[str, int]   = defaultdict(int)
    bias_confidences:     List[float] = []
    strategy_confidences: List[float] = []
    review_confidences:   List[float] = []

    for ex in executions:
        state = ex.result or {}

        # ── Bias ─────────────────────────────────────────────────────
        biases = state.get("biases", {})
        for tf_bias in biases.values():
            if isinstance(tf_bias, dict):
                label = (tf_bias.get("bias") or "").upper()
                if label:
                    bias_counts[label] += 1
                conf = tf_bias.get("confidence")
                if conf is not None:
                    bias_confidences.append(float(conf))

        # ── Strategy ─────────────────────────────────────────────────
        strategy = state.get("strategy") or {}
        if isinstance(strategy, dict):
            action = (strategy.get("action") or "").upper()
            if action:
                strategy_counts[action] += 1
            conf = strategy.get("confidence")
            if conf is not None:
                strategy_confidences.append(float(conf))

        # ── Trade review ─────────────────────────────────────────────
        review = state.get("trade_review") or {}
        if isinstance(review, dict):
            decision = (review.get("decision") or "").upper()
            if decision:
                review_counts[decision] += 1
            conf = review.get("confidence")
            if conf is not None:
                review_confidences.append(float(conf))

    report.bias_distribution     = dict(bias_counts)
    report.strategy_distribution = dict(strategy_counts)
    report.review_distribution   = dict(review_counts)

    if bias_confidences:
        report.avg_bias_confidence = round(sum(bias_confidences) / len(bias_confidences), 3)
    if strategy_confidences:
        report.avg_strategy_confidence = round(sum(strategy_confidences) / len(strategy_confidences), 3)
    if review_confidences:
        report.avg_review_confidence = round(sum(review_confidences) / len(review_confidences), 3)

    # ── Anomaly detection ─────────────────────────────────────────────
    if report.sample_size >= MIN_SAMPLE_FOR_ANOMALY:
        _detect_anomalies(report)

    return report


def _detect_anomalies(report: LLMQualityReport) -> None:
    """Mutate report.anomalies with detected quality issues."""

    # Bias concentration
    total_bias = sum(report.bias_distribution.values())
    if total_bias >= MIN_SAMPLE_FOR_ANOMALY:
        for label, count in report.bias_distribution.items():
            ratio = count / total_bias
            if ratio > BIAS_CONCENTRATION_THRESHOLD:
                report.anomalies.append(
                    f"Bias concentration: {label} = {ratio*100:.0f}% of signals "
                    f"({count}/{total_bias}). Model may be stuck — review instructions."
                )

    # Strategy HOLD dominance
    total_strat = sum(report.strategy_distribution.values())
    if total_strat >= MIN_SAMPLE_FOR_ANOMALY:
        hold_count = report.strategy_distribution.get("HOLD", 0)
        hold_ratio = hold_count / total_strat
        if hold_ratio > HOLD_RATE_HIGH_THRESHOLD:
            report.anomalies.append(
                f"Strategy HOLD rate too high: {hold_ratio*100:.0f}% ({hold_count}/{total_strat}). "
                "Strategy agent may be over-cautious or receiving poor market data."
            )

    # Trade review approval rate
    total_review = sum(report.review_distribution.values())
    if total_review >= MIN_SAMPLE_FOR_ANOMALY:
        approved = report.review_distribution.get("APPROVED", 0)
        approval_rate = approved / total_review
        if approval_rate > APPROVAL_RATE_HIGH_THRESHOLD:
            report.anomalies.append(
                f"Trade review approval rate suspiciously high: {approval_rate*100:.0f}% "
                f"({approved}/{total_review}). Review agent may be rubber-stamping trades."
            )
        if approval_rate < APPROVAL_RATE_LOW_THRESHOLD:
            report.anomalies.append(
                f"Trade review approval rate suspiciously low: {approval_rate*100:.0f}% "
                f"({approved}/{total_review}). Review agent may be too restrictive — "
                "check review instructions."
            )

    # Low confidence warnings
    if report.avg_strategy_confidence is not None and report.avg_strategy_confidence < 0.40:
        report.anomalies.append(
            f"Average strategy confidence is low ({report.avg_strategy_confidence:.0%}). "
            "Consider adding more context to strategy instructions or market data."
        )
