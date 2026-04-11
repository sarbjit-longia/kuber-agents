"""
Deterministic Market Regime Detector (TP-007)

Classifies market regime from candle data without any LLM calls.
Outputs a RegimeContext that strategy evaluators and the risk engine consume.

Regime dimensions:
  trend     : uptrend | downtrend | sideways | unknown
  volatility: low | normal | high
  session   : pre_market | regular | lunch | power_hour | after_hours
"""
from __future__ import annotations

import statistics
from datetime import datetime, time
from typing import List, Optional, Dict, Any

from app.schemas.pipeline_state import RegimeContext, TimeframeData


# ---------------------------------------------------------------------------
# Session boundaries (Eastern Time — naive datetime assumed from candle ts)
# ---------------------------------------------------------------------------
_SESSION = {
    "pre_market":  (time(4, 0),  time(9, 30)),
    "regular":     (time(9, 30), time(12, 0)),
    "lunch":       (time(12, 0), time(14, 0)),
    "power_hour":  (time(14, 0), time(16, 0)),
    "after_hours": (time(16, 0), time(20, 0)),
}


class RegimeDetector:
    """
    Classifies market regime deterministically from OHLCV candles.

    Usage::
        detector = RegimeDetector()
        regime = detector.detect(
            candles_5m=state.market_data.timeframes.get("5m", []),
            candles_1h=state.market_data.timeframes.get("1h", []),
            current_price=state.market_data.current_price,
        )
    """

    # Volatility thresholds (ATR as % of price)
    LOW_VOLATILITY_PCT  = 0.005   # ATR/price < 0.5%
    HIGH_VOLATILITY_PCT = 0.015   # ATR/price > 1.5%

    # Trend: how many of the last N candles close above their own SMA
    TREND_LOOKBACK = 20

    def detect(
        self,
        candles_5m: List[TimeframeData],
        candles_1h: Optional[List[TimeframeData]] = None,
        current_price: float = 0.0,
        now: Optional[datetime] = None,
    ) -> RegimeContext:
        """Return a fully populated RegimeContext."""
        now = now or datetime.utcnow()

        trend      = self._classify_trend(candles_1h or candles_5m)
        volatility = self._classify_volatility(candles_5m, current_price)
        session    = self._classify_session(now)
        adr_pct    = self._average_daily_range_pct(candles_5m, current_price)
        above_vwap = self._above_vwap(candles_5m, current_price)
        sma_align  = self._sma_alignment(candles_1h or candles_5m)
        score      = self._regime_score(trend, sma_align, above_vwap)

        return RegimeContext(
            trend=trend,
            volatility=volatility,
            session=session,
            adr_pct=round(adr_pct, 4) if adr_pct else None,
            above_vwap=above_vwap,
            sma_alignment=sma_align,
            regime_score=round(score, 3),
            details={
                "candles_5m_count": len(candles_5m),
                "candles_1h_count": len(candles_1h) if candles_1h else 0,
            },
        )

    # ------------------------------------------------------------------
    # Trend
    # ------------------------------------------------------------------
    def _classify_trend(self, candles: List[TimeframeData]) -> str:
        if len(candles) < self.TREND_LOOKBACK:
            return "unknown"

        closes = [c.close for c in candles[-self.TREND_LOOKBACK:]]
        sma = statistics.mean(closes)
        current = closes[-1]

        higher_highs = sum(
            1 for i in range(1, len(closes)) if closes[i] > closes[i - 1]
        )
        lower_lows = sum(
            1 for i in range(1, len(closes)) if closes[i] < closes[i - 1]
        )

        total = len(closes) - 1
        bullish_pct = higher_highs / total if total else 0
        bearish_pct = lower_lows / total if total else 0

        # Primary: SMA slope direction
        first_half  = statistics.mean(closes[:10])
        second_half = statistics.mean(closes[10:])
        slope_up   = second_half > first_half * 1.002
        slope_down = second_half < first_half * 0.998

        if slope_up and current > sma and bullish_pct > 0.55:
            return "uptrend"
        if slope_down and current < sma and bearish_pct > 0.55:
            return "downtrend"
        return "sideways"

    # ------------------------------------------------------------------
    # Volatility
    # ------------------------------------------------------------------
    def _classify_volatility(
        self, candles: List[TimeframeData], current_price: float
    ) -> str:
        if len(candles) < 5 or current_price <= 0:
            return "normal"

        atrs = [c.high - c.low for c in candles[-14:] if c.high > 0]
        if not atrs:
            return "normal"

        avg_atr = statistics.mean(atrs)
        atr_pct = avg_atr / current_price

        if atr_pct < self.LOW_VOLATILITY_PCT:
            return "low"
        if atr_pct > self.HIGH_VOLATILITY_PCT:
            return "high"
        return "normal"

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------
    @staticmethod
    def _classify_session(now: datetime) -> str:
        t = now.time()
        for name, (start, end) in _SESSION.items():
            if start <= t < end:
                return name
        return "after_hours"

    # ------------------------------------------------------------------
    # ADR %
    # ------------------------------------------------------------------
    @staticmethod
    def _average_daily_range_pct(
        candles: List[TimeframeData], current_price: float
    ) -> Optional[float]:
        if len(candles) < 5 or current_price <= 0:
            return None
        ranges = [(c.high - c.low) / current_price for c in candles[-20:] if c.high > 0]
        return statistics.mean(ranges) if ranges else None

    # ------------------------------------------------------------------
    # VWAP position
    # ------------------------------------------------------------------
    @staticmethod
    def _above_vwap(candles: List[TimeframeData], current_price: float) -> Optional[bool]:
        """Intraday VWAP: sum(typical_price * volume) / sum(volume)."""
        if not candles or current_price <= 0:
            return None

        tpv = sum((c.high + c.low + c.close) / 3 * c.volume for c in candles if c.volume > 0)
        vol = sum(c.volume for c in candles if c.volume > 0)
        if vol == 0:
            return None
        vwap = tpv / vol
        return current_price > vwap

    # ------------------------------------------------------------------
    # SMA alignment
    # ------------------------------------------------------------------
    @staticmethod
    def _sma_alignment(candles: List[TimeframeData]) -> Optional[str]:
        """Classify SMA20 vs SMA50 alignment using built-in indicator fields."""
        if len(candles) < 2:
            return None

        last = candles[-1]
        sma20 = last.sma_20
        sma50 = last.sma_50

        if sma20 is None or sma50 is None:
            return None

        if sma20 > sma50:
            return "bullish"
        if sma20 < sma50:
            return "bearish"
        return "mixed"

    # ------------------------------------------------------------------
    # Composite score
    # ------------------------------------------------------------------
    @staticmethod
    def _regime_score(
        trend: str,
        sma_align: Optional[str],
        above_vwap: Optional[bool],
    ) -> float:
        score = 0.0

        if trend == "uptrend":
            score += 0.5
        elif trend == "downtrend":
            score -= 0.5

        if sma_align == "bullish":
            score += 0.3
        elif sma_align == "bearish":
            score -= 0.3

        if above_vwap is True:
            score += 0.2
        elif above_vwap is False:
            score -= 0.2

        return max(-1.0, min(1.0, score))
