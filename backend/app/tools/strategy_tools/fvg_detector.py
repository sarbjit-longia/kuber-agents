"""
FVG Detector Tool - Detects Fair Value Gaps in price action

A Fair Value Gap (FVG) is a 3-candle wick imbalance:
- Bullish FVG: candle 2 low > candle 0 high
- Bearish FVG: candle 2 high < candle 0 low

The middle candle is the displacement candle, while the outer candles define the
actual gap that the strategy and chart should reference.
"""
import structlog
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = structlog.get_logger()


class FVGDetector:
    """Detects Fair Value Gaps in OHLC data."""
    
    def __init__(self, timeframe: str, min_gap_pips: float = 10, lookback_periods: int = 100):
        """
        Initialize FVG Detector.
        
        Args:
            timeframe: Timeframe to analyze (5m, 15m, 1h, 4h, D)
            min_gap_pips: Minimum gap size in pips to be valid (default: 10)
            lookback_periods: Number of candles to analyze (default: 100)
        """
        self.timeframe = timeframe
        self.min_gap_pips = min_gap_pips
        self.lookback_periods = lookback_periods
    
    async def detect(self, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Detect FVGs in the provided candles.
        
        Args:
            candles: List of OHLC candles (from Data Plane)
                     Each candle: {timestamp, open, high, low, close, volume}
        
        Returns:
            {
                "fvgs": [
                    {
                        "type": "bullish" | "bearish",
                        "high": float,
                        "low": float,
                        "gap_size_pips": float,
                        "formed_at": timestamp,
                        "formed_at_index": int,
                        "is_filled": bool,
                        "fill_percentage": float
                    }
                ],
                "latest_bullish_fvg": {...} or None,
                "latest_bearish_fvg": {...} or None,
                "total_fvgs": int,
                "timeframe": str
            }
        """
        
        if len(candles) < 3:
            logger.warning("insufficient_candles_for_fvg", count=len(candles))
            return self._empty_result()
        
        # Limit to lookback periods
        candles_to_analyze = candles[-self.lookback_periods:]
        
        fvgs: List[Dict[str, Any]] = []
        current_price = candles[-1]["close"]
        
        # Iterate through candles (need 3 candles for pattern)
        for i in range(2, len(candles_to_analyze)):
            candle_0 = candles_to_analyze[i - 2]  # First candle
            candle_1 = candles_to_analyze[i - 1]  # Middle candle
            candle_2 = candles_to_analyze[i]      # Current candle
            
            # ICT FVGs are defined by the wick gap between candle 1 and candle 3.
            # We still require the middle candle to show displacement so tiny noise
            # candles do not produce low-quality gaps.
            candle_0_high = float(candle_0["high"])
            candle_0_low = float(candle_0["low"])
            candle_2_high = float(candle_2["high"])
            candle_2_low = float(candle_2["low"])

            middle_body = abs(float(candle_1["close"]) - float(candle_1["open"]))
            outer_body_0 = abs(float(candle_0["close"]) - float(candle_0["open"]))
            outer_body_2 = abs(float(candle_2["close"]) - float(candle_2["open"]))
            displacement_confirmed = middle_body >= max(outer_body_0, outer_body_2)

            # Check for Bullish FVG using outer candle wicks.
            if displacement_confirmed and candle_2_low > candle_0_high:
                gap_size = candle_2_low - candle_0_high
                gap_size_pips = gap_size * 100  # Approximate pip conversion
                
                if gap_size_pips >= self.min_gap_pips:
                    future_candles = candles_to_analyze[i + 1:]
                    future_low = min((float(c["low"]) for c in future_candles), default=current_price)
                    fill_percentage = self._bullish_fill_percentage(
                        lower_edge=candle_0_high,
                        upper_edge=candle_2_low,
                        revisited_low=future_low,
                    )
                    is_tapped = fill_percentage > 0
                    is_filled = fill_percentage >= 100.0
                    
                    fvg = {
                        "type": "bullish",
                        "high": candle_2_low,
                        "low": candle_0_high,
                        "gap_size_pips": round(gap_size_pips, 2),
                        "formed_at": candle_2.get("timestamp", ""),
                        "formed_at_index": i,
                        "middle_candle_at": candle_1.get("timestamp", ""),
                        "is_tapped": is_tapped,
                        "is_filled": is_filled,
                        "fill_percentage": round(fill_percentage, 2),
                        "gap_basis": "wick",
                        "displacement_confirmed": displacement_confirmed,
                    }
                    
                    fvgs.append(fvg)
                    
                    logger.debug(
                        "bullish_fvg_detected",
                        gap_size_pips=gap_size_pips,
                        is_filled=is_filled
                    )
            
            # Check for Bearish FVG using outer candle wicks.
            elif displacement_confirmed and candle_2_high < candle_0_low:
                gap_size = candle_0_low - candle_2_high
                gap_size_pips = gap_size * 100
                
                if gap_size_pips >= self.min_gap_pips:
                    future_candles = candles_to_analyze[i + 1:]
                    future_high = max((float(c["high"]) for c in future_candles), default=current_price)
                    fill_percentage = self._bearish_fill_percentage(
                        lower_edge=candle_2_high,
                        upper_edge=candle_0_low,
                        revisited_high=future_high,
                    )
                    is_tapped = fill_percentage > 0
                    is_filled = fill_percentage >= 100.0
                    
                    fvg = {
                        "type": "bearish",
                        "high": candle_0_low,
                        "low": candle_2_high,
                        "gap_size_pips": round(gap_size_pips, 2),
                        "formed_at": candle_2.get("timestamp", ""),
                        "formed_at_index": i,
                        "middle_candle_at": candle_1.get("timestamp", ""),
                        "is_tapped": is_tapped,
                        "is_filled": is_filled,
                        "fill_percentage": round(fill_percentage, 2),
                        "gap_basis": "wick",
                        "displacement_confirmed": displacement_confirmed,
                    }
                    
                    fvgs.append(fvg)
                    
                    logger.debug(
                        "bearish_fvg_detected",
                        gap_size_pips=gap_size_pips,
                        is_filled=is_filled
                    )
        
        # Find latest unfilled FVGs
        latest_bullish = self._get_latest_unfilled(fvgs, "bullish")
        latest_bearish = self._get_latest_unfilled(fvgs, "bearish")
        
        result = {
            "fvgs": fvgs,
            "latest_bullish_fvg": latest_bullish,
            "latest_bearish_fvg": latest_bearish,
            "total_fvgs": len(fvgs),
            "unfilled_fvgs": len([f for f in fvgs if not f["is_filled"]]),
            "timeframe": self.timeframe
        }
        
        logger.info(
            "fvg_detection_complete",
            timeframe=self.timeframe,
            total_fvgs=len(fvgs),
            bullish=len([f for f in fvgs if f["type"] == "bullish"]),
            bearish=len([f for f in fvgs if f["type"] == "bearish"])
        )
        
        return result
    
    def _get_latest_unfilled(self, fvgs: List[Dict], fvg_type: str) -> Optional[Dict]:
        """Get the latest unfilled FVG of a specific type."""
        matching = [f for f in fvgs if f["type"] == fvg_type and not f["is_filled"]]
        return matching[-1] if matching else None

    def _bullish_fill_percentage(
        self,
        *,
        lower_edge: float,
        upper_edge: float,
        revisited_low: float,
    ) -> float:
        gap_range = upper_edge - lower_edge
        if gap_range <= 0 or revisited_low >= upper_edge:
            return 0.0
        filled_amount = upper_edge - max(revisited_low, lower_edge)
        if revisited_low <= lower_edge:
            return 100.0
        return min((filled_amount / gap_range) * 100, 100.0)

    def _bearish_fill_percentage(
        self,
        *,
        lower_edge: float,
        upper_edge: float,
        revisited_high: float,
    ) -> float:
        gap_range = upper_edge - lower_edge
        if gap_range <= 0 or revisited_high <= lower_edge:
            return 0.0
        filled_amount = min(revisited_high, upper_edge) - lower_edge
        if revisited_high >= upper_edge:
            return 100.0
        return min((filled_amount / gap_range) * 100, 100.0)
    
    def _empty_result(self) -> Dict[str, Any]:
        """Return empty result structure."""
        return {
            "fvgs": [],
            "latest_bullish_fvg": None,
            "latest_bearish_fvg": None,
            "total_fvgs": 0,
            "unfilled_fvgs": 0,
            "timeframe": self.timeframe
        }
