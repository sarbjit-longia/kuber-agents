"""
Deterministic Setup Evaluators (TP-006)

Each evaluator takes a RegimeContext + candles and returns a StrategySpec
(or None when the setup is not valid).  No LLM calls — all logic is rule-based
and fully reproducible.

Supported families:
  orb              – Opening Range Breakout
  vwap_pullback    – VWAP Pullback Continuation
  first_pullback   – First Pullback In Trend
  range_fade       – Range Fade At Extremes
  breakout_retest  – Breakout Retest Continuation
  swing_continuation – 4H/Daily momentum continuation
  mean_reversion   – Mean Reversion To Moving Average
"""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from app.schemas.pipeline_state import RegimeContext, StrategySpec, TimeframeData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _recent_closes(candles: List[TimeframeData], n: int) -> List[float]:
    return [c.close for c in candles[-n:]] if len(candles) >= n else []


def _atr(candles: List[TimeframeData], period: int = 14) -> Optional[float]:
    if len(candles) < period + 1:
        return None
    trs = []
    for i in range(1, len(candles)):
        c = candles[i]
        prev = candles[i - 1]
        trs.append(max(c.high - c.low, abs(c.high - prev.close), abs(c.low - prev.close)))
    return statistics.mean(trs[-period:])


def _vwap(candles: List[TimeframeData]) -> Optional[float]:
    vol = sum(c.volume for c in candles if c.volume > 0)
    if vol == 0:
        return None
    tpv = sum((c.high + c.low + c.close) / 3 * c.volume for c in candles if c.volume > 0)
    return tpv / vol


def _opening_range(candles_5m: List[TimeframeData]) -> Optional[Dict]:
    """Return high/low of the first 30 minutes (6 × 5m candles)."""
    if len(candles_5m) < 6:
        return None
    first6 = candles_5m[:6]
    return {
        "high": max(c.high for c in first6),
        "low":  min(c.low  for c in first6),
    }


# ---------------------------------------------------------------------------
# Main evaluator registry
# ---------------------------------------------------------------------------

class SetupEvaluator:
    """
    Runs all evaluators in priority order and returns the best valid StrategySpec,
    or None when no setup qualifies.

    Usage::
        evaluator = SetupEvaluator()
        spec = evaluator.evaluate(
            regime=regime,
            candles_5m=candles_5m,
            candles_1h=candles_1h,
            current_price=current_price,
        )
    """

    def evaluate(
        self,
        regime: RegimeContext,
        candles_5m: List[TimeframeData],
        candles_1h: Optional[List[TimeframeData]] = None,
        candles_daily: Optional[List[TimeframeData]] = None,
        current_price: float = 0.0,
        execution_timeframe: str = "5m",
    ) -> Optional[StrategySpec]:
        """Return the highest-priority valid setup, or None."""
        candles_1h    = candles_1h    or []
        candles_daily = candles_daily or []

        evaluators = [
            lambda: self._orb(regime, candles_5m, current_price, execution_timeframe),
            lambda: self._vwap_pullback(regime, candles_5m, current_price, execution_timeframe),
            lambda: self._first_pullback(regime, candles_5m, candles_1h, current_price, execution_timeframe),
            lambda: self._range_fade(regime, candles_5m, current_price, execution_timeframe),
            lambda: self._breakout_retest(regime, candles_1h or candles_5m, current_price, execution_timeframe),
            lambda: self._swing_continuation(regime, candles_daily or candles_1h, current_price, "1d"),
            lambda: self._mean_reversion(regime, candles_1h or candles_5m, current_price, execution_timeframe),
        ]

        for fn in evaluators:
            spec = fn()
            if spec and spec.action != "HOLD":
                return spec
        return None

    # ------------------------------------------------------------------
    # 1. Opening Range Breakout
    # ------------------------------------------------------------------
    def _orb(
        self,
        regime: RegimeContext,
        candles: List[TimeframeData],
        price: float,
        tf: str,
    ) -> Optional[StrategySpec]:
        if regime.session not in ("regular",):
            return None

        orb = _opening_range(candles)
        if orb is None:
            return None

        atr = _atr(candles)
        if atr is None:
            return None

        range_size = orb["high"] - orb["low"]
        # Only trade ORB when range is meaningful (>0.3 ATR) and not over-extended (< 3 ATR)
        if range_size < atr * 0.3 or range_size > atr * 3:
            return None

        latest = candles[-1] if candles else None
        if latest is None:
            return None

        # Bullish breakout: close above ORB high
        if latest.close > orb["high"] and latest.close > latest.open:
            stop = orb["low"]
            target = price + (price - stop) * 2.0  # 2:1 R/R
            return StrategySpec(
                strategy_family="orb",
                timeframe=tf,
                action="BUY",
                entry_price=round(orb["high"], 4),
                stop_loss=round(stop, 4),
                take_profit=round(target, 4),
                stop_type="fixed",
                valid_until=datetime.utcnow().replace(hour=16, minute=0, second=0),
                regime_required="regular",
                confidence=0.65,
                entry_reason=f"ORB bullish breakout above {orb['high']:.2f}",
                exit_reason=f"Initial stop at ORB low {stop:.2f}, 2:1 target {target:.2f}",
                source="deterministic",
            )

        # Bearish breakdown: close below ORB low
        if latest.close < orb["low"] and latest.close < latest.open:
            stop = orb["high"]
            target = price - (stop - price) * 2.0
            return StrategySpec(
                strategy_family="orb",
                timeframe=tf,
                action="SELL",
                entry_price=round(orb["low"], 4),
                stop_loss=round(stop, 4),
                take_profit=round(target, 4),
                stop_type="fixed",
                valid_until=datetime.utcnow().replace(hour=16, minute=0, second=0),
                regime_required="regular",
                confidence=0.65,
                entry_reason=f"ORB bearish breakdown below {orb['low']:.2f}",
                exit_reason=f"Initial stop at ORB high {stop:.2f}, 2:1 target {target:.2f}",
                source="deterministic",
            )

        return None

    # ------------------------------------------------------------------
    # 2. VWAP Pullback Continuation
    # ------------------------------------------------------------------
    def _vwap_pullback(
        self,
        regime: RegimeContext,
        candles: List[TimeframeData],
        price: float,
        tf: str,
    ) -> Optional[StrategySpec]:
        if len(candles) < 10:
            return None

        vwap = _vwap(candles)
        if vwap is None:
            return None

        atr = _atr(candles)
        if atr is None:
            return None

        above_vwap = regime.above_vwap
        trend      = regime.trend

        # Long: uptrend, price pulled back to within 0.5 ATR of VWAP, now reclaiming
        if trend == "uptrend" and above_vwap is True:
            last  = candles[-1]
            prev  = candles[-2]
            near_vwap = abs(prev.low - vwap) < atr * 0.5
            reclaim   = prev.close < vwap and last.close > vwap
            if near_vwap and reclaim:
                stop   = round(min(prev.low, vwap - atr * 0.3), 4)
                target = round(price + (price - stop) * 2.0, 4)
                return StrategySpec(
                    strategy_family="vwap_pullback",
                    timeframe=tf,
                    action="BUY",
                    entry_price=round(price, 4),
                    stop_loss=stop,
                    take_profit=target,
                    stop_type="breakeven_trail",
                    confidence=0.70,
                    regime_required="uptrend",
                    entry_reason=f"VWAP pullback reclaim at {vwap:.2f}",
                    exit_reason=f"Stop below VWAP pullback low {stop:.2f}",
                    source="deterministic",
                )

        # Short: downtrend, price rallied to VWAP, rejecting
        if trend == "downtrend" and above_vwap is False:
            last = candles[-1]
            prev = candles[-2]
            near_vwap = abs(prev.high - vwap) < atr * 0.5
            reject    = prev.close > vwap and last.close < vwap
            if near_vwap and reject:
                stop   = round(max(prev.high, vwap + atr * 0.3), 4)
                target = round(price - (stop - price) * 2.0, 4)
                return StrategySpec(
                    strategy_family="vwap_pullback",
                    timeframe=tf,
                    action="SELL",
                    entry_price=round(price, 4),
                    stop_loss=stop,
                    take_profit=target,
                    stop_type="breakeven_trail",
                    confidence=0.70,
                    regime_required="downtrend",
                    entry_reason=f"VWAP rejection at {vwap:.2f}",
                    exit_reason=f"Stop above VWAP rejection high {stop:.2f}",
                    source="deterministic",
                )

        return None

    # ------------------------------------------------------------------
    # 3. First Pullback In Trend
    # ------------------------------------------------------------------
    def _first_pullback(
        self,
        regime: RegimeContext,
        candles_5m: List[TimeframeData],
        candles_1h: List[TimeframeData],
        price: float,
        tf: str,
    ) -> Optional[StrategySpec]:
        ref = candles_1h if len(candles_1h) >= 20 else candles_5m
        if len(ref) < 20:
            return None

        atr = _atr(ref)
        if atr is None:
            return None

        trend = regime.trend
        closes = _recent_closes(ref, 20)
        if not closes:
            return None

        # Detect impulse leg followed by shallow correction
        peak   = max(closes[-15:-5])
        trough = min(closes[-5:])
        recent = closes[-1]

        if trend == "uptrend":
            pullback_pct = (peak - trough) / peak if peak > 0 else 0
            resuming     = recent > trough and recent > closes[-2]
            if 0.02 <= pullback_pct <= 0.08 and resuming:
                stop   = round(trough - atr * 0.2, 4)
                target = round(price + (price - stop) * 2.5, 4)
                return StrategySpec(
                    strategy_family="first_pullback",
                    timeframe=tf,
                    action="BUY",
                    entry_price=round(price, 4),
                    stop_loss=stop,
                    take_profit=target,
                    stop_type="breakeven_trail",
                    confidence=0.72,
                    regime_required="uptrend",
                    entry_reason=f"First pullback {pullback_pct*100:.1f}% in uptrend, resuming",
                    exit_reason=f"Stop below pullback low {stop:.2f}",
                    source="deterministic",
                )

        if trend == "downtrend":
            bounce_pct = (trough - peak) / trough if trough > 0 else 0  # negative
            peak2  = max(closes[-5:])
            valley = min(closes[-15:-5])
            bounce = (peak2 - valley) / abs(valley) if valley != 0 else 0
            resuming = recent < peak2 and recent < closes[-2]
            if 0.02 <= bounce <= 0.08 and resuming:
                stop   = round(peak2 + atr * 0.2, 4)
                target = round(price - (stop - price) * 2.5, 4)
                return StrategySpec(
                    strategy_family="first_pullback",
                    timeframe=tf,
                    action="SELL",
                    entry_price=round(price, 4),
                    stop_loss=stop,
                    take_profit=target,
                    stop_type="breakeven_trail",
                    confidence=0.72,
                    regime_required="downtrend",
                    entry_reason=f"First bounce {bounce*100:.1f}% in downtrend, resuming",
                    exit_reason=f"Stop above bounce high {stop:.2f}",
                    source="deterministic",
                )

        return None

    # ------------------------------------------------------------------
    # 4. Range Fade At Extremes
    # ------------------------------------------------------------------
    def _range_fade(
        self,
        regime: RegimeContext,
        candles: List[TimeframeData],
        price: float,
        tf: str,
    ) -> Optional[StrategySpec]:
        if regime.trend != "sideways" or len(candles) < 20:
            return None

        atr = _atr(candles)
        if atr is None:
            return None

        highs  = [c.high  for c in candles[-20:]]
        lows   = [c.low   for c in candles[-20:]]
        range_high = statistics.mean(sorted(highs, reverse=True)[:3])  # Top-3 avg
        range_low  = statistics.mean(sorted(lows)[:3])                  # Bottom-3 avg
        mid        = (range_high + range_low) / 2

        last = candles[-1] if candles else None
        if last is None:
            return None

        # Short at top of range
        if price >= range_high - atr * 0.2 and last.close < last.open:
            stop   = round(range_high + atr * 0.3, 4)
            target = round(mid, 4)
            return StrategySpec(
                strategy_family="range_fade",
                timeframe=tf,
                action="SELL",
                entry_price=round(price, 4),
                stop_loss=stop,
                take_profit=target,
                stop_type="fixed",
                confidence=0.60,
                regime_required="sideways",
                entry_reason=f"Range top fade near {range_high:.2f}",
                exit_reason=f"Target range midpoint {mid:.2f}",
                source="deterministic",
            )

        # Long at bottom of range
        if price <= range_low + atr * 0.2 and last.close > last.open:
            stop   = round(range_low - atr * 0.3, 4)
            target = round(mid, 4)
            return StrategySpec(
                strategy_family="range_fade",
                timeframe=tf,
                action="BUY",
                entry_price=round(price, 4),
                stop_loss=stop,
                take_profit=target,
                stop_type="fixed",
                confidence=0.60,
                regime_required="sideways",
                entry_reason=f"Range bottom bounce near {range_low:.2f}",
                exit_reason=f"Target range midpoint {mid:.2f}",
                source="deterministic",
            )

        return None

    # ------------------------------------------------------------------
    # 5. Breakout Retest Continuation
    # ------------------------------------------------------------------
    def _breakout_retest(
        self,
        regime: RegimeContext,
        candles: List[TimeframeData],
        price: float,
        tf: str,
    ) -> Optional[StrategySpec]:
        if len(candles) < 30:
            return None

        atr = _atr(candles)
        if atr is None:
            return None

        # Find recent swing high that was broken
        lookback = candles[-30:-5]
        recent   = candles[-5:]
        if not lookback or not recent:
            return None

        swing_high = max(c.high for c in lookback)
        swing_low  = min(c.low  for c in lookback)
        last = recent[-1]

        # Bullish: broke above swing high, now retesting it from above
        broke_high = any(c.close > swing_high for c in recent[:-1])
        retesting  = abs(price - swing_high) < atr * 0.5
        holding    = last.close > swing_high - atr * 0.3

        if broke_high and retesting and holding and regime.trend in ("uptrend", "sideways"):
            stop   = round(swing_high - atr, 4)
            target = round(price + (price - stop) * 2.0, 4)
            return StrategySpec(
                strategy_family="breakout_retest",
                timeframe=tf,
                action="BUY",
                entry_price=round(price, 4),
                stop_loss=stop,
                take_profit=target,
                stop_type="fixed",
                confidence=0.68,
                entry_reason=f"Breakout retest of {swing_high:.2f}",
                exit_reason=f"Stop below breakout level {stop:.2f}",
                source="deterministic",
            )

        # Bearish: broke below swing low, retesting from below
        broke_low = any(c.close < swing_low for c in recent[:-1])
        retesting_low = abs(price - swing_low) < atr * 0.5
        holding_low   = last.close < swing_low + atr * 0.3

        if broke_low and retesting_low and holding_low and regime.trend in ("downtrend", "sideways"):
            stop   = round(swing_low + atr, 4)
            target = round(price - (stop - price) * 2.0, 4)
            return StrategySpec(
                strategy_family="breakout_retest",
                timeframe=tf,
                action="SELL",
                entry_price=round(price, 4),
                stop_loss=stop,
                take_profit=target,
                stop_type="fixed",
                confidence=0.68,
                entry_reason=f"Breakdown retest of {swing_low:.2f}",
                exit_reason=f"Stop above breakdown level {stop:.2f}",
                source="deterministic",
            )

        return None

    # ------------------------------------------------------------------
    # 6. Swing Continuation (Daily/4H)
    # ------------------------------------------------------------------
    def _swing_continuation(
        self,
        regime: RegimeContext,
        candles: List[TimeframeData],
        price: float,
        tf: str,
    ) -> Optional[StrategySpec]:
        if len(candles) < 5:
            return None

        atr = _atr(candles)
        if atr is None:
            return None

        trend = regime.trend
        sma   = regime.sma_alignment

        if trend == "uptrend" and sma == "bullish":
            last = candles[-1]
            # Momentum candle (close in top 30% of range)
            candle_range = last.high - last.low
            if candle_range > 0 and (last.close - last.low) / candle_range > 0.7:
                stop   = round(last.low - atr * 0.2, 4)
                target = round(price + (price - stop) * 2.5, 4)
                return StrategySpec(
                    strategy_family="swing_continuation",
                    timeframe=tf,
                    action="BUY",
                    entry_price=round(price, 4),
                    stop_loss=stop,
                    take_profit=target,
                    stop_type="atr_trail",
                    confidence=0.62,
                    regime_required="uptrend",
                    entry_reason="Daily/4H momentum continuation, SMA bullish aligned",
                    exit_reason=f"ATR trail stop, initial stop {stop:.2f}",
                    source="deterministic",
                )

        if trend == "downtrend" and sma == "bearish":
            last = candles[-1]
            candle_range = last.high - last.low
            if candle_range > 0 and (last.high - last.close) / candle_range > 0.7:
                stop   = round(last.high + atr * 0.2, 4)
                target = round(price - (stop - price) * 2.5, 4)
                return StrategySpec(
                    strategy_family="swing_continuation",
                    timeframe=tf,
                    action="SELL",
                    entry_price=round(price, 4),
                    stop_loss=stop,
                    take_profit=target,
                    stop_type="atr_trail",
                    confidence=0.62,
                    regime_required="downtrend",
                    entry_reason="Daily/4H momentum continuation, SMA bearish aligned",
                    exit_reason=f"ATR trail stop, initial stop {stop:.2f}",
                    source="deterministic",
                )

        return None

    # ------------------------------------------------------------------
    # 7. Mean Reversion To Moving Average
    # ------------------------------------------------------------------
    def _mean_reversion(
        self,
        regime: RegimeContext,
        candles: List[TimeframeData],
        price: float,
        tf: str,
    ) -> Optional[StrategySpec]:
        if len(candles) < 20:
            return None

        atr = _atr(candles)
        if atr is None:
            return None

        closes = [c.close for c in candles[-20:]]
        sma20  = statistics.mean(closes)
        std    = statistics.stdev(closes) if len(closes) > 1 else 0

        deviation_pct = abs(price - sma20) / sma20 if sma20 > 0 else 0

        # Only trigger when price is 1.5–3 std devs away from mean
        if std > 0:
            z_score = (price - sma20) / std
        else:
            return None

        if regime.volatility == "high":
            return None  # Mean reversion unreliable in high volatility

        # Price too far above SMA — short back to mean
        if z_score > 2.0 and candles[-1].close < candles[-2].close:
            stop   = round(price + atr * 0.5, 4)
            target = round(sma20, 4)
            if target >= price:
                return None  # Target must be below entry for short
            return StrategySpec(
                strategy_family="mean_reversion",
                timeframe=tf,
                action="SELL",
                entry_price=round(price, 4),
                stop_loss=stop,
                take_profit=target,
                stop_type="fixed",
                confidence=0.58,
                entry_reason=f"Mean reversion: {deviation_pct*100:.1f}% above SMA20 ({sma20:.2f}), z={z_score:.1f}",
                exit_reason=f"Target SMA20 {sma20:.2f}",
                source="deterministic",
            )

        # Price too far below SMA — long back to mean
        if z_score < -2.0 and candles[-1].close > candles[-2].close:
            stop   = round(price - atr * 0.5, 4)
            target = round(sma20, 4)
            if target <= price:
                return None
            return StrategySpec(
                strategy_family="mean_reversion",
                timeframe=tf,
                action="BUY",
                entry_price=round(price, 4),
                stop_loss=stop,
                take_profit=target,
                stop_type="fixed",
                confidence=0.58,
                entry_reason=f"Mean reversion: {deviation_pct*100:.1f}% below SMA20 ({sma20:.2f}), z={z_score:.1f}",
                exit_reason=f"Target SMA20 {sma20:.2f}",
                source="deterministic",
            )

        return None
