"""
FVG Detector Tool - Detects Fair Value Gaps in price action

A Fair Value Gap (FVG) is a 3-candle pattern where:
- Bullish FVG: Current candle's low > Previous candle's high (gap up)
- Bearish FVG: Current candle's high < Previous candle's low (gap down)

These gaps represent inefficiencies in price and often act as support/resistance.
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
            
            # Check for Bullish FVG
            # Condition: candle_2.low > candle_0.high (gap between candle 0 and 2)
            if candle_2["low"] > candle_0["high"]:
                gap_size = candle_2["low"] - candle_0["high"]
                gap_size_pips = gap_size * 100  # Approximate pip conversion
                
                if gap_size_pips >= self.min_gap_pips:
                    # Check if FVG is filled (price came back into the gap)
                    is_filled = current_price <= candle_2["low"]
                    fill_percentage = 0.0
                    
                    if is_filled:
                        # Calculate how much of gap is filled
                        gap_range = candle_2["low"] - candle_0["high"]
                        filled_amount = candle_2["low"] - current_price
                        fill_percentage = min((filled_amount / gap_range) * 100, 100.0) if gap_range > 0 else 0.0
                    
                    fvg = {
                        "type": "bullish",
                        "high": candle_2["low"],
                        "low": candle_0["high"],
                        "gap_size_pips": round(gap_size_pips, 2),
                        "formed_at": candle_2.get("timestamp", ""),
                        "formed_at_index": i,
                        "is_filled": is_filled,
                        "fill_percentage": round(fill_percentage, 2)
                    }
                    
                    fvgs.append(fvg)
                    
                    logger.debug(
                        "bullish_fvg_detected",
                        gap_size_pips=gap_size_pips,
                        is_filled=is_filled
                    )
            
            # Check for Bearish FVG
            # Condition: candle_2.high < candle_0.low (gap down)
            elif candle_2["high"] < candle_0["low"]:
                gap_size = candle_0["low"] - candle_2["high"]
                gap_size_pips = gap_size * 100
                
                if gap_size_pips >= self.min_gap_pips:
                    # Check if FVG is filled
                    is_filled = current_price >= candle_2["high"]
                    fill_percentage = 0.0
                    
                    if is_filled:
                        gap_range = candle_0["low"] - candle_2["high"]
                        filled_amount = current_price - candle_2["high"]
                        fill_percentage = min((filled_amount / gap_range) * 100, 100.0) if gap_range > 0 else 0.0
                    
                    fvg = {
                        "type": "bearish",
                        "high": candle_0["low"],
                        "low": candle_2["high"],
                        "gap_size_pips": round(gap_size_pips, 2),
                        "formed_at": candle_2.get("timestamp", ""),
                        "formed_at_index": i,
                        "is_filled": is_filled,
                        "fill_percentage": round(fill_percentage, 2)
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

