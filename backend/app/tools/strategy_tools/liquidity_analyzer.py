"""
Liquidity Analyzer Tool - Detects liquidity pools and liquidity grabs

In ICT trading:
- Liquidity pools form at swing highs/lows where stops are likely placed
- Liquidity grabs occur when price spikes through a level then reverses
- These are often entry triggers for institutional traders
"""
import structlog
from typing import List, Dict, Any, Optional

logger = structlog.get_logger()


class LiquidityAnalyzer:
    """Analyzes liquidity pools and grabs in price action."""
    
    def __init__(
        self,
        timeframe: str,
        swing_strength: int = 5,
        grab_threshold_pips: float = 10,
        lookback_periods: int = 100
    ):
        """
        Initialize Liquidity Analyzer.
        
        Args:
            timeframe: Timeframe to analyze (5m, 15m, 1h, 4h, D)
            swing_strength: Number of candles on each side for swing detection (default: 5)
            grab_threshold_pips: Minimum distance for a grab (default: 10 pips)
            lookback_periods: Number of candles to analyze (default: 100)
        """
        self.timeframe = timeframe
        self.swing_strength = swing_strength
        self.grab_threshold_pips = grab_threshold_pips
        self.lookback_periods = lookback_periods
    
    async def analyze(self, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze liquidity in the provided candles.
        
        Args:
            candles: List of OHLC candles
        
        Returns:
            {
                "swing_highs": [...],
                "swing_lows": [...],
                "liquidity_grabs": [
                    {
                        "type": "buy_side" | "sell_side",
                        "level": float,
                        "grabbed_at": timestamp,
                        "grab_candle_index": int,
                        "distance_pips": float,
                        "reversed": bool
                    }
                ],
                "latest_grab": {...} or None,
                "active_liquidity_pools": {
                    "above": [float],  # Buy-side liquidity
                    "below": [float]   # Sell-side liquidity
                }
            }
        """
        
        if len(candles) < self.swing_strength * 2 + 1:
            logger.warning("insufficient_candles_for_liquidity", count=len(candles))
            return self._empty_result()
        
        candles_to_analyze = candles[-self.lookback_periods:]
        
        # 1. Detect swing highs and swing lows
        swing_highs = self._detect_swing_highs(candles_to_analyze)
        swing_lows = self._detect_swing_lows(candles_to_analyze)
        
        # 2. Detect liquidity grabs
        liquidity_grabs = self._detect_liquidity_grabs(
            candles_to_analyze,
            swing_highs,
            swing_lows
        )
        
        # 3. Identify active (unfilled) liquidity pools
        current_price = candles_to_analyze[-1]["close"]
        active_pools = self._get_active_pools(
            swing_highs,
            swing_lows,
            liquidity_grabs,
            current_price
        )
        
        latest_grab = liquidity_grabs[-1] if liquidity_grabs else None
        
        result = {
            "swing_highs": swing_highs,
            "swing_lows": swing_lows,
            "liquidity_grabs": liquidity_grabs,
            "latest_grab": latest_grab,
            "active_liquidity_pools": active_pools,
            "total_grabs": len(liquidity_grabs),
            "timeframe": self.timeframe
        }
        
        logger.info(
            "liquidity_analysis_complete",
            timeframe=self.timeframe,
            swing_highs=len(swing_highs),
            swing_lows=len(swing_lows),
            grabs=len(liquidity_grabs)
        )
        
        return result
    
    def _detect_swing_highs(self, candles: List[Dict]) -> List[Dict]:
        """
        Detect swing highs: A candle high that is higher than N candles before and after.
        """
        swing_highs = []
        n = self.swing_strength
        
        for i in range(n, len(candles) - n):
            current_high = candles[i]["high"]
            
            # Check if this high is higher than all surrounding candles
            is_swing = True
            for j in range(i - n, i + n + 1):
                if j == i:
                    continue
                if candles[j]["high"] >= current_high:
                    is_swing = False
                    break
            
            if is_swing:
                swing_highs.append({
                    "price": current_high,
                    "timestamp": candles[i].get("timestamp", ""),
                    "index": i
                })
        
        return swing_highs
    
    def _detect_swing_lows(self, candles: List[Dict]) -> List[Dict]:
        """
        Detect swing lows: A candle low that is lower than N candles before and after.
        """
        swing_lows = []
        n = self.swing_strength
        
        for i in range(n, len(candles) - n):
            current_low = candles[i]["low"]
            
            # Check if this low is lower than all surrounding candles
            is_swing = True
            for j in range(i - n, i + n + 1):
                if j == i:
                    continue
                if candles[j]["low"] <= current_low:
                    is_swing = False
                    break
            
            if is_swing:
                swing_lows.append({
                    "price": current_low,
                    "timestamp": candles[i].get("timestamp", ""),
                    "index": i
                })
        
        return swing_lows
    
    def _detect_liquidity_grabs(
        self,
        candles: List[Dict],
        swing_highs: List[Dict],
        swing_lows: List[Dict]
    ) -> List[Dict]:
        """
        Detect liquidity grabs: when price quickly spikes through a swing level and reverses.
        """
        grabs = []
        
        # Check for buy-side liquidity grabs (spike above swing high)
        for swing_high in swing_highs:
            swing_index = swing_high["index"]
            swing_price = swing_high["price"]
            
            # Look for candles after the swing that spike above it
            for i in range(swing_index + 1, len(candles)):
                candle = candles[i]
                
                # Did this candle spike above the swing high?
                if candle["high"] > swing_price:
                    distance_pips = (candle["high"] - swing_price) * 100
                    
                    if distance_pips >= self.grab_threshold_pips:
                        # Check if price reversed (closed below the level)
                        reversed = candle["close"] < swing_price
                        
                        grabs.append({
                            "type": "buy_side",
                            "level": swing_price,
                            "grabbed_at": candle.get("timestamp", ""),
                            "grab_candle_index": i,
                            "distance_pips": round(distance_pips, 2),
                            "reversed": reversed
                        })
                        
                        break  # Only count first grab of this level
        
        # Check for sell-side liquidity grabs (spike below swing low)
        for swing_low in swing_lows:
            swing_index = swing_low["index"]
            swing_price = swing_low["price"]
            
            for i in range(swing_index + 1, len(candles)):
                candle = candles[i]
                
                if candle["low"] < swing_price:
                    distance_pips = (swing_price - candle["low"]) * 100
                    
                    if distance_pips >= self.grab_threshold_pips:
                        reversed = candle["close"] > swing_price
                        
                        grabs.append({
                            "type": "sell_side",
                            "level": swing_price,
                            "grabbed_at": candle.get("timestamp", ""),
                            "grab_candle_index": i,
                            "distance_pips": round(distance_pips, 2),
                            "reversed": reversed
                        })
                        
                        break
        
        # Sort by index
        grabs.sort(key=lambda x: x["grab_candle_index"])
        
        return grabs
    
    def _get_active_pools(
        self,
        swing_highs: List[Dict],
        swing_lows: List[Dict],
        grabs: List[Dict],
        current_price: float
    ) -> Dict[str, List[float]]:
        """
        Identify active (unfilled) liquidity pools.
        A pool is active if it hasn't been grabbed yet.
        """
        grabbed_levels = {grab["level"] for grab in grabs}
        
        active_above = [
            sh["price"] for sh in swing_highs
            if sh["price"] > current_price and sh["price"] not in grabbed_levels
        ]
        
        active_below = [
            sl["price"] for sl in swing_lows
            if sl["price"] < current_price and sl["price"] not in grabbed_levels
        ]
        
        # Sort and deduplicate
        active_above = sorted(list(set(active_above)))
        active_below = sorted(list(set(active_below)), reverse=True)
        
        return {
            "above": active_above,
            "below": active_below
        }
    
    def _empty_result(self) -> Dict[str, Any]:
        """Return empty result structure."""
        return {
            "swing_highs": [],
            "swing_lows": [],
            "liquidity_grabs": [],
            "latest_grab": None,
            "active_liquidity_pools": {"above": [], "below": []},
            "total_grabs": 0,
            "timeframe": self.timeframe
        }

