"""
Order Block detector for ICT-style supply and demand zones.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()


class OrderBlockDetector:
    """Detect bullish and bearish order blocks from OHLC candles."""

    def __init__(self, timeframe: str, min_move_pips: float = 10, lookback_periods: int = 100):
        self.timeframe = timeframe
        self.min_move_pips = min_move_pips
        self.lookback_periods = lookback_periods

    async def detect(self, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        if len(candles) < 6:
            return self._empty_result()

        candles_to_analyze = candles[-self.lookback_periods:]
        order_blocks: List[Dict[str, Any]] = []

        for i in range(len(candles_to_analyze) - 4):
            candidate = candles_to_analyze[i]
            future_window = candles_to_analyze[i + 1:i + 4]
            future_after_window = candles_to_analyze[i + 4:]

            candidate_open = float(candidate["open"])
            candidate_close = float(candidate["close"])
            candidate_high = float(candidate["high"])
            candidate_low = float(candidate["low"])
            body_low = min(candidate_open, candidate_close)
            body_high = max(candidate_open, candidate_close)
            body_size = abs(candidate_close - candidate_open)

            if not future_window:
                continue

            max_future_high = max(float(c["high"]) for c in future_window)
            min_future_low = min(float(c["low"]) for c in future_window)
            max_future_close = max(float(c["close"]) for c in future_window)
            min_future_close = min(float(c["close"]) for c in future_window)
            max_future_body = max(abs(float(c["close"]) - float(c["open"])) for c in future_window)

            # Bullish order block: last bearish candle before bullish displacement.
            if candidate_close < candidate_open:
                move_size_pips = (max_future_high - candidate_high) * 100
                displacement_confirmed = max_future_close > candidate_high and max_future_body >= body_size
                if displacement_confirmed and move_size_pips >= self.min_move_pips:
                    future_low_after = min(
                        (float(c["low"]) for c in future_after_window),
                        default=float(candles_to_analyze[-1]["low"]),
                    )
                    is_retested = future_low_after <= body_high
                    order_blocks.append(
                        {
                            "type": "bullish",
                            "high": body_high,
                            "low": body_low,
                            "full_high": candidate_high,
                            "full_low": candidate_low,
                            "formed_at": candidate.get("timestamp", ""),
                            "formed_at_index": i,
                            "move_size_pips": round(move_size_pips, 2),
                            "zone_basis": "body",
                            "is_retested": is_retested,
                            "displacement_confirmed": True,
                        }
                    )

            # Bearish order block: last bullish candle before bearish displacement.
            if candidate_close > candidate_open:
                move_size_pips = (candidate_low - min_future_low) * 100
                displacement_confirmed = min_future_close < candidate_low and max_future_body >= body_size
                if displacement_confirmed and move_size_pips >= self.min_move_pips:
                    future_high_after = max(
                        (float(c["high"]) for c in future_after_window),
                        default=float(candles_to_analyze[-1]["high"]),
                    )
                    is_retested = future_high_after >= body_low
                    order_blocks.append(
                        {
                            "type": "bearish",
                            "high": body_high,
                            "low": body_low,
                            "full_high": candidate_high,
                            "full_low": candidate_low,
                            "formed_at": candidate.get("timestamp", ""),
                            "formed_at_index": i,
                            "move_size_pips": round(move_size_pips, 2),
                            "zone_basis": "body",
                            "is_retested": is_retested,
                            "displacement_confirmed": True,
                        }
                    )

        latest_bullish = self._get_latest(order_blocks, "bullish")
        latest_bearish = self._get_latest(order_blocks, "bearish")
        return {
            "order_blocks": order_blocks,
            "latest_bullish_order_block": latest_bullish,
            "latest_bearish_order_block": latest_bearish,
            "total_order_blocks": len(order_blocks),
            "active_order_blocks": len([ob for ob in order_blocks if not ob["is_retested"]]),
            "timeframe": self.timeframe,
        }

    def _get_latest(self, order_blocks: List[Dict[str, Any]], block_type: str) -> Optional[Dict[str, Any]]:
        matching = [ob for ob in order_blocks if ob["type"] == block_type]
        return matching[-1] if matching else None

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "order_blocks": [],
            "latest_bullish_order_block": None,
            "latest_bearish_order_block": None,
            "total_order_blocks": 0,
            "active_order_blocks": 0,
            "timeframe": self.timeframe,
        }
