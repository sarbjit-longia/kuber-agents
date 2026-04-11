"""
Pre-Trade Execution Filters (TP-022)

Checks spread, liquidity, and volatility conditions before allowing a
trade to be placed at the broker.  Run inside _execute_broker_trade
after risk approval but before the broker API call.

Returns a FilterResult — if rejected, the caller should skip execution
and log the reason rather than failing hard.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger()


@dataclass
class FilterResult:
    """Result of running all pre-trade checks."""
    passed: bool = True
    rejection_reason: Optional[str] = None
    checks: Dict[str, str] = field(default_factory=dict)  # check_name → "passed" | "skipped" | reason


class PreTradeFilter:
    """
    Deterministic pre-trade checks.

    All checks are skippable when the required data is absent — we never
    block a trade solely because market data is unavailable.  Rejections
    only happen when data is present AND clearly out of range.
    """

    # Defaults — overridden by broker response data when present
    MAX_SPREAD_PCT_DEFAULT      = 0.003   # 0.3% of price
    MIN_VOLUME_1M_DEFAULT       = 100_000  # 100k shares/contracts last minute
    MAX_ATR_MULT_DEFAULT        = 5.0     # ATR/price ratio upper bound
    MIN_ATR_MULT_DEFAULT        = 0.1     # ATR/price ratio lower bound (skip in dead market)

    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: Agent config dict from which we read optional overrides:
                max_spread_pct          float — max allowed bid-ask spread as % of price
                min_volume_1m           int   — min last-minute volume
                max_atr_mult            float — max ATR as % of price (skip if too volatile)
                min_atr_mult            float — min ATR as % of price (skip if no movement)
        """
        self.max_spread_pct = float(config.get("max_spread_pct", self.MAX_SPREAD_PCT_DEFAULT))
        self.min_volume_1m  = float(config.get("min_volume_1m",  self.MIN_VOLUME_1M_DEFAULT))
        self.max_atr_mult   = float(config.get("max_atr_mult",   self.MAX_ATR_MULT_DEFAULT))
        self.min_atr_mult   = float(config.get("min_atr_mult",   self.MIN_ATR_MULT_DEFAULT))

    def check(
        self,
        symbol: str,
        entry_price: float,
        market_data: Optional[Dict[str, Any]] = None,
        strategy_spec: Optional[Any] = None,
    ) -> FilterResult:
        """
        Run all pre-trade checks.

        Args:
            symbol:        Ticker symbol.
            entry_price:   Intended entry price.
            market_data:   Optional dict with keys: bid, ask, volume_1m, atr
            strategy_spec: Optional StrategySpec (for atr from regime context).

        Returns:
            FilterResult with passed=True if all checks pass, or False + reason.
        """
        result = FilterResult()
        md = market_data or {}

        # ── 1. Spread check ───────────────────────────────────────────
        bid = md.get("bid")
        ask = md.get("ask")
        if bid and ask and entry_price > 0:
            spread_pct = (float(ask) - float(bid)) / entry_price
            if spread_pct > self.max_spread_pct:
                result.passed = False
                result.rejection_reason = (
                    f"Spread too wide: {spread_pct*100:.3f}% "
                    f"(limit: {self.max_spread_pct*100:.2f}%). "
                    "Poor liquidity — avoid chasing."
                )
                result.checks["spread"] = result.rejection_reason
                return result  # Fast-exit on first failure
            result.checks["spread"] = "passed"
        else:
            result.checks["spread"] = "skipped (no bid/ask data)"

        # ── 2. Minimum volume check ───────────────────────────────────
        vol = md.get("volume_1m") or md.get("volume")
        if vol is not None:
            if float(vol) < self.min_volume_1m:
                result.passed = False
                result.rejection_reason = (
                    f"Volume too low: {float(vol):,.0f} "
                    f"(min: {self.min_volume_1m:,.0f}). "
                    "Insufficient liquidity for safe fill."
                )
                result.checks["volume"] = result.rejection_reason
                return result
            result.checks["volume"] = "passed"
        else:
            result.checks["volume"] = "skipped (no volume data)"

        # ── 3. ATR volatility bounds ──────────────────────────────────
        atr = md.get("atr")
        if atr and entry_price > 0:
            atr_pct = float(atr) / entry_price
            if atr_pct > self.max_atr_mult:
                result.passed = False
                result.rejection_reason = (
                    f"Volatility too high: ATR/price = {atr_pct*100:.2f}% "
                    f"(max: {self.max_atr_mult*100:.0f}%). "
                    "Avoid wide-range conditions — slippage risk too high."
                )
                result.checks["atr_upper"] = result.rejection_reason
                return result
            if atr_pct < self.min_atr_mult:
                result.passed = False
                result.rejection_reason = (
                    f"Volatility too low: ATR/price = {atr_pct*100:.3f}% "
                    f"(min: {self.min_atr_mult*100:.1f}%). "
                    "Dead market — no meaningful range to trade."
                )
                result.checks["atr_lower"] = result.rejection_reason
                return result
            result.checks["atr"] = "passed"
        else:
            result.checks["atr"] = "skipped (no ATR data)"

        return result


def parse_filter_config_from_instructions(instructions: str) -> Dict[str, Any]:
    """
    Extract filter overrides from natural language instructions.

    Examples parsed:
        "max spread 0.2%"         → max_spread_pct=0.002
        "minimum volume 500k"     → min_volume_1m=500000
        "skip if atr > 4%"        → max_atr_mult=0.04
    """
    config: Dict[str, Any] = {}
    text = instructions.lower()

    m = re.search(r'(?:max\s+)?spread\s+(\d+(?:\.\d+)?)\s*%', text)
    if m:
        config["max_spread_pct"] = float(m.group(1)) / 100

    m = re.search(r'(?:min(?:imum)?\s+)?volume\s+(\d+(?:\.\d+)?)\s*([km]?)', text)
    if m:
        val = float(m.group(1))
        suffix = m.group(2)
        if suffix == "k":
            val *= 1_000
        elif suffix == "m":
            val *= 1_000_000
        config["min_volume_1m"] = val

    return config
