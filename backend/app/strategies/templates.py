"""
First-Party Deterministic Strategy Templates (TP-013)

Each template is a self-contained specification dict that describes:
  - valid market regime
  - allowed timeframes
  - entry trigger (maps to a SetupEvaluator family)
  - stop logic
  - target logic
  - time-based invalidation
  - position sizing model
  - asset universe filters

Templates are NOT prompt instructions. They are machine-readable contracts
that drive the deterministic evaluators. Users can copy and customise them.
"""
from __future__ import annotations
from typing import Dict, Any, List, Optional


StrategyTemplate = Dict[str, Any]

# ---------------------------------------------------------------------------
# Intraday Templates
# ---------------------------------------------------------------------------

ORB: StrategyTemplate = {
    "id": "orb",
    "name": "Opening Range Breakout",
    "description": (
        "Trade the breakout of the first 30-minute range (6 × 5m candles). "
        "Valid only during the regular session. Avoid on low-range days."
    ),
    "category": "intraday",
    "style": "momentum",
    "evaluator_family": "orb",
    "allowed_timeframes": ["1m", "3m", "5m"],
    "execution_timeframe": "5m",
    "required_regime": "regular_session",
    "entry": {
        "trigger": "close_above_orb_high | close_below_orb_low",
        "confirmation": "candle_direction_matches_breakout",
        "range_filter": {"min_atr_multiplier": 0.3, "max_atr_multiplier": 3.0},
    },
    "stop": {
        "type": "fixed",
        "long_stop": "orb_low",
        "short_stop": "orb_high",
    },
    "target": {
        "type": "rr_ratio",
        "ratio": 2.0,
        "take_profit_2_ratio": 3.0,
    },
    "invalidation": {
        "time_stop": "14:00 ET",
        "re_entry": False,
    },
    "position_sizing": {
        "model": "risk_pct",
        "default_risk_pct": 0.01,
    },
    "universe": {
        "asset_classes": ["equities"],
        "avoid_earnings": True,
        "min_adr_pct": 0.005,
    },
}

VWAP_PULLBACK: StrategyTemplate = {
    "id": "vwap_pullback",
    "name": "VWAP Pullback Continuation",
    "description": (
        "Enter on a pullback to VWAP in the direction of the intraday trend. "
        "Long when price reclaims VWAP in uptrend; short when it rejects VWAP in downtrend."
    ),
    "category": "intraday",
    "style": "trend_continuation",
    "evaluator_family": "vwap_pullback",
    "allowed_timeframes": ["1m", "3m", "5m", "15m"],
    "execution_timeframe": "5m",
    "required_regime": "trending",
    "entry": {
        "trigger": "price_crosses_vwap_in_trend_direction",
        "confirmation": "previous_candle_touched_vwap",
        "proximity_atr_multiplier": 0.5,
    },
    "stop": {
        "type": "breakeven_trail",
        "initial_long_stop": "pullback_low_minus_0.3atr",
        "initial_short_stop": "pullback_high_plus_0.3atr",
    },
    "target": {
        "type": "rr_ratio",
        "ratio": 2.0,
    },
    "invalidation": {
        "time_stop": "15:30 ET",
        "re_entry": True,
        "max_re_entries": 2,
    },
    "position_sizing": {
        "model": "risk_pct",
        "default_risk_pct": 0.01,
    },
    "universe": {
        "asset_classes": ["equities", "futures"],
        "avoid_earnings": True,
        "min_volume_1m": 500000,
    },
}

FIRST_PULLBACK: StrategyTemplate = {
    "id": "first_pullback",
    "name": "First Pullback In Trend",
    "description": (
        "Buy the first 2-8% pullback after an impulse leg in an uptrend, "
        "or sell the first 2-8% bounce in a downtrend."
    ),
    "category": "intraday",
    "style": "trend_continuation",
    "evaluator_family": "first_pullback",
    "allowed_timeframes": ["5m", "15m", "30m"],
    "execution_timeframe": "5m",
    "required_regime": "trending",
    "entry": {
        "trigger": "price_resuming_after_pullback",
        "pullback_range_pct": {"min": 0.02, "max": 0.08},
        "confirmation": "close_above_prior_candle_high",
    },
    "stop": {
        "type": "breakeven_trail",
        "initial_stop": "pullback_low_minus_0.2atr",
    },
    "target": {
        "type": "rr_ratio",
        "ratio": 2.5,
    },
    "position_sizing": {
        "model": "risk_pct",
        "default_risk_pct": 0.01,
    },
    "universe": {
        "asset_classes": ["equities", "futures", "crypto"],
        "avoid_earnings": True,
    },
}

RANGE_FADE: StrategyTemplate = {
    "id": "range_fade",
    "name": "Range Fade At Extremes",
    "description": (
        "Fade price at the extremes of a sideways range. "
        "Short at range top, long at range bottom, targeting range midpoint."
    ),
    "category": "intraday",
    "style": "mean_reversion",
    "evaluator_family": "range_fade",
    "allowed_timeframes": ["5m", "15m"],
    "execution_timeframe": "5m",
    "required_regime": "sideways",
    "entry": {
        "trigger": "price_at_range_extreme",
        "proximity_atr_multiplier": 0.2,
        "confirmation": "reversal_candle",
    },
    "stop": {
        "type": "fixed",
        "buffer_atr_multiplier": 0.3,
    },
    "target": {
        "type": "range_midpoint",
    },
    "position_sizing": {
        "model": "risk_pct",
        "default_risk_pct": 0.008,
    },
    "universe": {
        "asset_classes": ["equities", "forex"],
        "prefer_low_volatility": True,
    },
}

# ---------------------------------------------------------------------------
# Swing Templates
# ---------------------------------------------------------------------------

DAILY_TREND_PULLBACK: StrategyTemplate = {
    "id": "daily_trend_pullback",
    "name": "Daily Trend Pullback",
    "description": (
        "Enter on a pullback to a key level (SMA, support) in the direction of the "
        "daily trend. Hold for multi-day continuation."
    ),
    "category": "swing",
    "style": "trend_continuation",
    "evaluator_family": "first_pullback",
    "allowed_timeframes": ["1h", "4h", "1d"],
    "execution_timeframe": "1h",
    "required_regime": "trending",
    "entry": {
        "trigger": "pullback_to_sma_or_support",
        "timeframes": ["4h", "1d"],
        "pullback_range_pct": {"min": 0.03, "max": 0.12},
        "confirmation": "daily_candle_close",
    },
    "stop": {
        "type": "fixed",
        "initial_stop": "below_pullback_low",
    },
    "target": {
        "type": "rr_ratio",
        "ratio": 2.5,
        "partial_take_at_ratio": 1.5,
    },
    "invalidation": {
        "daily_close_below_stop": True,
    },
    "position_sizing": {
        "model": "risk_pct",
        "default_risk_pct": 0.01,
    },
    "universe": {
        "asset_classes": ["equities"],
        "avoid_earnings_within_days": 5,
        "min_market_cap": "mid_cap",
    },
}

BREAKOUT_RETEST: StrategyTemplate = {
    "id": "breakout_retest",
    "name": "Breakout Retest Continuation",
    "description": (
        "Enter on a retest of a recently broken level (resistance → support, "
        "or support → resistance). The level must have been broken cleanly."
    ),
    "category": "swing",
    "style": "trend_continuation",
    "evaluator_family": "breakout_retest",
    "allowed_timeframes": ["1h", "4h", "1d"],
    "execution_timeframe": "1h",
    "required_regime": "any",
    "entry": {
        "trigger": "price_retesting_broken_level",
        "proximity_atr_multiplier": 0.5,
        "confirmation": "holding_above_broken_level",
        "max_candles_since_breakout": 10,
    },
    "stop": {
        "type": "fixed",
        "stop_atr_below_level": 1.0,
    },
    "target": {
        "type": "rr_ratio",
        "ratio": 2.0,
    },
    "position_sizing": {
        "model": "risk_pct",
        "default_risk_pct": 0.01,
    },
    "universe": {
        "asset_classes": ["equities", "futures", "crypto"],
    },
}

SWING_MOMENTUM: StrategyTemplate = {
    "id": "swing_momentum",
    "name": "4H/Daily Momentum Continuation",
    "description": (
        "Enter on a strong momentum candle (close in top 30% of range for longs) "
        "when SMA20 > SMA50 alignment confirms the trend."
    ),
    "category": "swing",
    "style": "momentum",
    "evaluator_family": "swing_continuation",
    "allowed_timeframes": ["4h", "1d"],
    "execution_timeframe": "4h",
    "required_regime": "trending",
    "entry": {
        "trigger": "momentum_candle_in_trend",
        "close_in_top_pct_for_long": 0.70,
        "close_in_bottom_pct_for_short": 0.30,
        "sma_alignment": "required",
    },
    "stop": {
        "type": "atr_trail",
        "initial_stop": "candle_low_plus_0.2atr",
        "trail_atr_multiplier": 1.5,
    },
    "target": {
        "type": "rr_ratio",
        "ratio": 2.5,
    },
    "position_sizing": {
        "model": "risk_pct",
        "default_risk_pct": 0.01,
    },
    "universe": {
        "asset_classes": ["equities", "futures"],
        "avoid_earnings_within_days": 3,
    },
}

MEAN_REVERSION_MA: StrategyTemplate = {
    "id": "mean_reversion_ma",
    "name": "Mean Reversion To Moving Average",
    "description": (
        "Enter when price is >2 standard deviations from SMA20 and showing "
        "early signs of reversal. Target the SMA20."
    ),
    "category": "swing",
    "style": "mean_reversion",
    "evaluator_family": "mean_reversion",
    "allowed_timeframes": ["1h", "4h"],
    "execution_timeframe": "1h",
    "required_regime": "sideways_or_low_volatility",
    "entry": {
        "trigger": "z_score_beyond_threshold",
        "z_score_threshold": 2.0,
        "confirmation": "reversal_candle",
    },
    "stop": {
        "type": "fixed",
        "buffer_atr_multiplier": 0.5,
    },
    "target": {
        "type": "sma20",
    },
    "invalidation": {
        "avoid_high_volatility": True,
        "avoid_earnings": True,
    },
    "position_sizing": {
        "model": "risk_pct",
        "default_risk_pct": 0.008,
    },
    "universe": {
        "asset_classes": ["equities", "forex"],
        "prefer_low_beta": True,
    },
}

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

STRATEGY_TEMPLATES: Dict[str, StrategyTemplate] = {
    # Intraday
    "orb":            ORB,
    "vwap_pullback":  VWAP_PULLBACK,
    "first_pullback": FIRST_PULLBACK,
    "range_fade":     RANGE_FADE,
    # Swing
    "daily_trend_pullback": DAILY_TREND_PULLBACK,
    "breakout_retest":      BREAKOUT_RETEST,
    "swing_momentum":       SWING_MOMENTUM,
    "mean_reversion_ma":    MEAN_REVERSION_MA,
}


def get_template(template_id: str) -> Optional[StrategyTemplate]:
    """Return a template by ID, or None if not found."""
    return STRATEGY_TEMPLATES.get(template_id)


def list_templates(category: Optional[str] = None) -> List[StrategyTemplate]:
    """Return all templates, optionally filtered by category."""
    templates = list(STRATEGY_TEMPLATES.values())
    if category:
        templates = [t for t in templates if t.get("category") == category]
    return templates
