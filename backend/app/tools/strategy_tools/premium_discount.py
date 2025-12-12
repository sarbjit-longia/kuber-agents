"""
Premium/Discount Zone Tool - Identifies fair value zones

In ICT trading:
- Premium zone (70-100%): Area where price is considered expensive, good for sells
- Equilibrium (40-60%): Fair value area
- Discount zone (0-30%): Area where price is considered cheap, good for buys

Calculated from recent swing high/low range on higher timeframe.
"""
import structlog
from typing import List, Dict, Any, Optional

logger = structlog.get_logger()


class PremiumDiscountAnalyzer:
    """Analyzes premium/discount zones based on recent range."""
    
    def __init__(
        self,
        timeframe: str,
        lookback_periods: int = 50
    ):
        """
        Initialize Premium/Discount Analyzer.
        
        Args:
            timeframe: Timeframe to analyze (typically higher TF like 4h, D)
            lookback_periods: Number of candles for range (default: 50)
        """
        self.timeframe = timeframe
        self.lookback_periods = lookback_periods
    
    async def analyze(self, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze premium/discount zones.
        
        Args:
            candles: List of OHLC candles
        
        Returns:
            {
                "current_price": float,
                "range_high": float,
                "range_low": float,
                "price_level_percent": float,  # 0-100, where in range
                "zone": "premium" | "equilibrium" | "discount",
                "zones": {
                    "premium": {"high": float, "low": float},
                    "equilibrium": {"high": float, "low": float},
                    "discount": {"high": float, "low": float}
                },
                "is_in_discount": bool,
                "is_in_premium": bool,
                "is_in_equilibrium": bool
            }
        """
        
        if len(candles) < 10:
            logger.warning("insufficient_candles_for_zones", count=len(candles))
            return self._empty_result()
        
        candles_to_analyze = candles[-self.lookback_periods:]
        
        # 1. Find range high and low
        range_high = max(c["high"] for c in candles_to_analyze)
        range_low = min(c["low"] for c in candles_to_analyze)
        
        current_price = candles[-1]["close"]
        
        # 2. Calculate price level as percentage of range
        if range_high == range_low:
            # No range, can't determine zones
            logger.warning("no_price_range_detected")
            return self._empty_result()
        
        price_level_percent = ((current_price - range_low) / (range_high - range_low)) * 100
        
        # 3. Define zones
        # Premium: 70-100% of range (upper 30%)
        # Equilibrium: 40-60% of range (middle 20%)
        # Discount: 0-30% of range (lower 30%)
        
        range_size = range_high - range_low
        
        zones = {
            "premium": {
                "high": range_high,
                "low": range_low + (range_size * 0.70)
            },
            "equilibrium": {
                "high": range_low + (range_size * 0.60),
                "low": range_low + (range_size * 0.40)
            },
            "discount": {
                "high": range_low + (range_size * 0.30),
                "low": range_low
            }
        }
        
        # 4. Determine current zone
        if price_level_percent >= 70:
            zone = "premium"
        elif price_level_percent <= 30:
            zone = "discount"
        else:
            zone = "equilibrium"
        
        # 5. Add Fibonacci-like levels for precision
        fib_levels = {
            "100": range_high,
            "79": range_low + (range_size * 0.786),  # Premium entry
            "70": range_low + (range_size * 0.70),
            "62": range_low + (range_size * 0.618),  # Golden pocket
            "50": range_low + (range_size * 0.50),   # Equilibrium
            "38": range_low + (range_size * 0.382),  # Golden pocket
            "30": range_low + (range_size * 0.30),
            "21": range_low + (range_size * 0.214),  # Discount entry
            "0": range_low
        }
        
        result = {
            "current_price": round(current_price, 5),
            "range_high": round(range_high, 5),
            "range_low": round(range_low, 5),
            "range_size_pips": round((range_high - range_low) * 100, 2),
            "price_level_percent": round(price_level_percent, 2),
            "zone": zone,
            "zones": {
                k: {
                    "high": round(v["high"], 5),
                    "low": round(v["low"], 5)
                }
                for k, v in zones.items()
            },
            "fib_levels": {k: round(v, 5) for k, v in fib_levels.items()},
            "is_in_discount": zone == "discount",
            "is_in_premium": zone == "premium",
            "is_in_equilibrium": zone == "equilibrium",
            "timeframe": self.timeframe
        }
        
        logger.info(
            "premium_discount_complete",
            timeframe=self.timeframe,
            zone=zone,
            price_level=price_level_percent
        )
        
        return result
    
    def _empty_result(self) -> Dict[str, Any]:
        """Return empty result structure."""
        return {
            "current_price": 0.0,
            "range_high": 0.0,
            "range_low": 0.0,
            "range_size_pips": 0.0,
            "price_level_percent": 50.0,
            "zone": "equilibrium",
            "zones": {
                "premium": {"high": 0.0, "low": 0.0},
                "equilibrium": {"high": 0.0, "low": 0.0},
                "discount": {"high": 0.0, "low": 0.0}
            },
            "fib_levels": {},
            "is_in_discount": False,
            "is_in_premium": False,
            "is_in_equilibrium": True,
            "timeframe": self.timeframe
        }

