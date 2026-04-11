"""
First-Party Strategy Playbooks (TP-027 / TP-028)

Pre-configured, copyable pipeline templates that give users a working
starting point for common swing and intraday strategies.

Each playbook produces a complete pipeline config (nodes + edges) wired
to a specific deterministic strategy template from TP-013.

Usage::
    playbook = get_playbook("orb_intraday")
    pipeline_config = playbook.to_pipeline_config(symbol="AAPL", mode="paper")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.strategies.templates import STRATEGY_TEMPLATES, StrategyTemplate


# ---------------------------------------------------------------------------
# Playbook model
# ---------------------------------------------------------------------------

@dataclass
class Playbook:
    """A pre-configured, copyable pipeline template."""
    id: str
    name: str
    description: str
    category: str               # "intraday" | "swing"
    strategy_template_id: str   # Maps to STRATEGY_TEMPLATES
    difficulty: str             # "beginner" | "intermediate" | "advanced"
    timeframes: List[str]
    default_risk_pct: float     # 0–1
    instructions: Dict[str, str]  # Per-agent instruction snippets
    tags: List[str] = field(default_factory=list)

    def to_pipeline_config(
        self,
        symbol: str,
        mode: str = "paper",
        risk_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Generate a complete pipeline config ready for POST /pipelines.

        The config follows the standard node/edge structure consumed by
        PipelineExecutor and rendered in the guided pipeline builder.
        """
        rp = risk_pct or self.default_risk_pct
        tpl: Optional[StrategyTemplate] = STRATEGY_TEMPLATES.get(self.strategy_template_id)
        exec_tf = tpl.get("execution_timeframe", "5m") if tpl else "5m"

        return {
            "symbol": symbol,
            "mode": mode,
            "timeframes": self.timeframes,
            "nodes": [
                {
                    "id": "node-1",
                    "agent_type": "market_data_agent",
                    "config": {
                        "timeframes": self.timeframes,
                        "limit": 100,
                    },
                },
                {
                    "id": "node-2",
                    "agent_type": "bias_agent",
                    "config": {
                        "instructions": self.instructions.get("bias", ""),
                        "timeframes": self.timeframes,
                    },
                },
                {
                    "id": "node-3",
                    "agent_type": "strategy_agent",
                    "config": {
                        "instructions": self.instructions.get("strategy", ""),
                        "strategy_family": self.strategy_template_id,
                        "execution_timeframe": exec_tf,
                    },
                },
                {
                    "id": "node-4",
                    "agent_type": "risk_manager_agent",
                    "config": {
                        "instructions": (
                            self.instructions.get("risk", "") +
                            f" Risk {rp*100:.0f}% of account per trade."
                        ),
                        "max_concurrent_positions": 3,
                    },
                },
                {
                    "id": "node-5",
                    "agent_type": "trade_review_agent",
                    "config": {
                        "instructions": self.instructions.get("review", ""),
                    },
                },
                {
                    "id": "node-6",
                    "agent_type": "trade_manager_agent",
                    "config": {
                        "instructions": self.instructions.get("execution", ""),
                        "no_entry_sessions": ["lunch", "after_hours", "pre_market"],
                        "tools": [],  # User adds broker tool after cloning
                    },
                },
            ],
            "edges": [
                {"from": "node-1", "to": "node-2"},
                {"from": "node-2", "to": "node-3"},
                {"from": "node-3", "to": "node-4"},
                {"from": "node-4", "to": "node-5"},
                {"from": "node-5", "to": "node-6"},
            ],
            # Guardrail defaults — require 10 paper trades before going live
            "guardrails": {
                "min_paper_trades": 10,
                "min_win_rate": 0.0,
                "max_drawdown_pct": 0.30,
            },
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialise for API response."""
        tpl = STRATEGY_TEMPLATES.get(self.strategy_template_id)
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "difficulty": self.difficulty,
            "strategy_template_id": self.strategy_template_id,
            "strategy_template": tpl,
            "timeframes": self.timeframes,
            "default_risk_pct": self.default_risk_pct,
            "tags": self.tags,
        }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_PLAYBOOKS: Dict[str, Playbook] = {}


def _register(pb: Playbook) -> Playbook:
    _PLAYBOOKS[pb.id] = pb
    return pb


# ── Intraday ──────────────────────────────────────────────────────────────

_register(Playbook(
    id="orb_intraday",
    name="Opening Range Breakout",
    description=(
        "Trade the first 30-minute range breakout. "
        "Long above the ORB high, short below the low. "
        "2:1 R/R, stop at opposite extreme of range. "
        "Ideal for high-relative-volume stocks at the open."
    ),
    category="intraday",
    strategy_template_id="orb",
    difficulty="beginner",
    timeframes=["5m", "1h"],
    default_risk_pct=0.01,
    instructions={
        "bias": (
            "Assess the pre-market context and overnight gap. "
            "Be BULLISH if the stock is gapping up with strong volume relative to 30-day average. "
            "Be BEARISH if gapping down with distribution. "
            "Be NEUTRAL otherwise — ORB works in both directions but don't fight a strong trend."
        ),
        "strategy": (
            "Use the Opening Range Breakout strategy. "
            "The opening range is defined by the first 30 minutes (6 × 5m candles). "
            "Enter long on a clean close above the ORB high with confirming candle direction. "
            "Enter short on a close below the ORB low. "
            "Only trade if the range size is between 0.3× and 3× ATR — avoid micro or monster ranges."
        ),
        "risk": (
            "Use risk-based position sizing. "
            "Stop is the opposite extreme of the opening range. "
            "Target is 2:1 risk/reward from entry. "
        ),
        "review": (
            "Approve if: volume > 1.5× average, spread < 0.1%, no earnings within 2 days. "
            "Reject if: setup formed after 10:30 AM ET, range is more than 4% of price, "
            "or the stock has had >5 reversals in the range already."
        ),
        "execution": (
            "Close by 2:00 PM ET if still open. "
            "No new entries after 11:30 AM ET. "
            "Break-even at 1R."
        ),
    },
    tags=["intraday", "momentum", "breakout", "beginner-friendly"],
))

_register(Playbook(
    id="vwap_pullback_intraday",
    name="VWAP Pullback Continuation",
    description=(
        "Enter on a pullback to VWAP in the direction of the intraday trend. "
        "For uptrending stocks: buy when price reclaims VWAP after a brief dip. "
        "For downtrenders: short when price rejects VWAP on the way down."
    ),
    category="intraday",
    strategy_template_id="vwap_pullback",
    difficulty="intermediate",
    timeframes=["5m", "1h"],
    default_risk_pct=0.01,
    instructions={
        "bias": (
            "Assess the intraday trend relative to the prior day's close and pre-market levels. "
            "Be BULLISH if price is trending above VWAP and above the open with higher lows. "
            "Be BEARISH if price is below VWAP and forming lower highs. "
            "Neutral during the first 30 minutes — wait for trend to establish."
        ),
        "strategy": (
            "Use the VWAP Pullback Continuation strategy. "
            "Wait for price to pull back to VWAP from the trend direction. "
            "Enter long when a 5m candle closes back above VWAP after touching or slightly breaching it. "
            "Enter short when price rejects from below VWAP with a bearish candle. "
            "Stop is the pullback low (long) or high (short) minus 0.3× ATR."
        ),
        "risk": "Risk 1% per trade. Target 2:1 R/R from entry.",
        "review": (
            "Approve if: price has made at least 2 higher highs (or lower lows) before the pullback. "
            "Reject if: price is choppy or has crossed VWAP more than 3 times in the last hour."
        ),
        "execution": (
            "No entries during lunch (12:00–14:00 ET). "
            "Close by 3:30 PM ET. "
            "Trail stop 1% once position is profitable."
        ),
    },
    tags=["intraday", "trend-following", "vwap", "intermediate"],
))

_register(Playbook(
    id="range_fade_intraday",
    name="Range Fade At Extremes",
    description=(
        "Fade price at the top and bottom of a defined intraday range. "
        "Best on low-volatility days when price is clearly ranging. "
        "Short at range resistance, long at range support, target the midpoint."
    ),
    category="intraday",
    strategy_template_id="range_fade",
    difficulty="intermediate",
    timeframes=["5m", "15m"],
    default_risk_pct=0.008,
    instructions={
        "bias": (
            "Be NEUTRAL — this strategy is designed for sideways markets. "
            "Only run when the broader market is in a consolidation or low-volatility regime. "
            "Skip on high-momentum days or major news days."
        ),
        "strategy": (
            "Use the Range Fade strategy. "
            "Identify the intraday range high and low from the first 2 hours of trading. "
            "Short when price tests the range high with a reversal candle. "
            "Long when price tests the range low with a bullish engulfing. "
            "Target the range midpoint."
        ),
        "risk": "Risk 0.8% per trade. Stop is 0.3× ATR beyond the range extreme.",
        "review": "Reject if VIX > 25 or SPY is moving >1% intraday.",
        "execution": "No new entries after 2:30 PM ET. Close all by 3:45 PM ET.",
    },
    tags=["intraday", "mean-reversion", "range", "low-volatility"],
))

# ── Swing ─────────────────────────────────────────────────────────────────

_register(Playbook(
    id="daily_trend_pullback_swing",
    name="Daily Trend Pullback (Swing)",
    description=(
        "Buy pullbacks to key support in a confirmed daily uptrend. "
        "Hold for 3–10 days targeting a continuation of the primary trend. "
        "Risk management uses a fixed stop below the pullback low."
    ),
    category="swing",
    strategy_template_id="daily_trend_pullback",
    difficulty="intermediate",
    timeframes=["1h", "4h", "1d"],
    default_risk_pct=0.01,
    instructions={
        "bias": (
            "Use the daily and 4h charts to assess trend. "
            "Be BULLISH if the stock is above its 20-day SMA, the 20-day SMA is above the 50-day SMA, "
            "and the stock has made a higher high in the last 5 days. "
            "Be BEARISH for the inverse. Skip if the sector ETF is in a downtrend."
        ),
        "strategy": (
            "Use the First Pullback In Trend strategy on the daily chart. "
            "Look for a 3–8% pullback from a recent swing high in an uptrend. "
            "Enter when the daily candle closes above the prior day's high after the pullback. "
            "Stop below the pullback low minus 0.2× ATR."
        ),
        "risk": "Risk 1% per trade. Target 2.5:1 R/R (hold for continuation).",
        "review": (
            "Approve if: no earnings within 5 trading days, daily volume > 50-day average volume, "
            "relative strength vs sector is positive. "
            "Reject if: the pullback is more than 12% or the stock is extended past a prior breakout."
        ),
        "execution": (
            "Use limit orders at the prior high. "
            "No intraday management — check once per day at market close. "
            "Break-even at 1R. Exit if daily candle closes below the 20-day SMA."
        ),
    },
    tags=["swing", "trend-following", "multi-day", "intermediate"],
))

_register(Playbook(
    id="breakout_retest_swing",
    name="Breakout Retest (Swing)",
    description=(
        "Enter on the first retest of a clean breakout level after resistance "
        "has been converted to support. Hold for continuation of the breakout move."
    ),
    category="swing",
    strategy_template_id="breakout_retest",
    difficulty="advanced",
    timeframes=["1h", "4h", "1d"],
    default_risk_pct=0.01,
    instructions={
        "bias": (
            "Be BULLISH if price has broken above a multi-week resistance with above-average volume "
            "and is now pulling back to retest that level. "
            "Be BEARISH for the inverse. "
            "Do not take breakout retests in choppy or low-volume environments."
        ),
        "strategy": (
            "Use the Breakout Retest Continuation strategy. "
            "The broken level must have been tested at least twice as resistance before the breakout. "
            "Enter on the retest only if price is holding above (for longs) or below (for shorts) the level. "
            "Stop 1× ATR beyond the level — a close through it invalidates the breakout."
        ),
        "risk": "Risk 1% per trade. Target 2:1 R/R minimum.",
        "review": (
            "Approve if: retest is occurring within 10 bars of the breakout, volume contracted on the retest "
            "(showing orderly digestion). "
            "Reject if: price has already tested the level and rejected once since the breakout — "
            "that increases the odds of a failed breakout."
        ),
        "execution": "Hold for 5–15 days. Trail stop 1.5× ATR after reaching 1R.",
    },
    tags=["swing", "breakout", "retest", "advanced"],
))

_register(Playbook(
    id="mean_reversion_swing",
    name="Mean Reversion To Moving Average",
    description=(
        "Enter when price stretches more than 2 standard deviations from the "
        "20-period SMA and shows early reversal signs. Target the SMA."
    ),
    category="swing",
    strategy_template_id="mean_reversion_ma",
    difficulty="advanced",
    timeframes=["1h", "4h"],
    default_risk_pct=0.008,
    instructions={
        "bias": (
            "Be CONTRARIAN — this strategy fades extended moves. "
            "Be BULLISH when an oversold stock is returning to fair value (z-score < -2). "
            "Be BEARISH when an overbought stock is reverting (z-score > +2). "
            "Only run in low-volatility, sideways market environments."
        ),
        "strategy": (
            "Use the Mean Reversion To Moving Average strategy. "
            "Enter only when the z-score is beyond ±2.0 from the 20-period SMA. "
            "Require a reversal candle (engulfing, hammer, or shooting star). "
            "Target is the 20-period SMA. Stop is 0.5× ATR beyond the entry candle extreme."
        ),
        "risk": "Risk 0.8% per trade. High-probability setup so smaller R/R is acceptable.",
        "review": (
            "Reject if: earnings within 3 days, VIX > 25, or the stock has made a new 52-week extreme "
            "— trends can stay extended for longer than mean-reversion models expect."
        ),
        "execution": "Exit at the 20-period SMA or if the z-score exceeds ±3.0 (runaway move).",
    },
    tags=["swing", "mean-reversion", "oversold", "advanced"],
))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_playbook(playbook_id: str) -> Optional[Playbook]:
    return _PLAYBOOKS.get(playbook_id)


def list_playbooks(category: Optional[str] = None) -> List[Playbook]:
    pbs = list(_PLAYBOOKS.values())
    if category:
        pbs = [p for p in pbs if p.category == category]
    return pbs


def validate_template(template: StrategyTemplate) -> List[str]:
    """
    Validate a strategy template against the marketplace contract (TP-028).

    Returns a list of validation errors (empty = valid).
    """
    errors: List[str] = []
    required_keys = ["id", "name", "description", "category", "evaluator_family",
                     "entry", "stop", "target", "position_sizing"]
    for k in required_keys:
        if k not in template:
            errors.append(f"Missing required field: '{k}'")

    if "position_sizing" in template:
        ps = template["position_sizing"]
        if ps.get("model") not in ("risk_pct", "fixed_shares", "fixed_notional"):
            errors.append("position_sizing.model must be one of: risk_pct, fixed_shares, fixed_notional")
        if ps.get("model") == "risk_pct":
            rp = ps.get("default_risk_pct", 0)
            if not (0 < rp <= 0.05):
                errors.append("position_sizing.default_risk_pct must be between 0 and 0.05 (5%)")

    if "entry" in template and "trigger" not in template["entry"]:
        errors.append("entry.trigger is required")

    if "stop" in template and "type" not in template["stop"]:
        errors.append("stop.type is required")

    if "target" in template and "type" not in template["target"]:
        errors.append("target.type is required")

    return errors
