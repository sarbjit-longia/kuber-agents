"""
Market Structure Tool - Detects BOS (Break of Structure) and CHoCH (Change of Character)

In ICT trading:
- BOS (Break of Structure): Price breaks a recent high/low in the current trend direction
- CHoCH (Change of Character): Price breaks against the trend, signaling potential reversal
- Market structure helps identify trend direction and key decision points
"""
import structlog
from typing import List, Dict, Any, Optional

logger = structlog.get_logger()


class MarketStructureAnalyzer:
    """Analyzes market structure (BOS, CHoCH, trend direction)."""
    
    def __init__(
        self,
        timeframe: str,
        swing_strength: int = 5,
        lookback_periods: int = 100
    ):
        """
        Initialize Market Structure Analyzer.
        
        Args:
            timeframe: Timeframe to analyze (5m, 15m, 1h, 4h, D)
            swing_strength: Number of candles for swing detection (default: 5)
            lookback_periods: Number of candles to analyze (default: 100)
        """
        self.timeframe = timeframe
        self.swing_strength = swing_strength
        self.lookback_periods = lookback_periods
    
    async def analyze(self, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze market structure in the provided candles.
        
        Args:
            candles: List of OHLC candles
        
        Returns:
            {
                "trend": "bullish" | "bearish" | "ranging",
                "structure_events": [
                    {
                        "type": "BOS" | "CHoCH",
                        "direction": "bullish" | "bearish",
                        "level": float,
                        "timestamp": str,
                        "candle_index": int
                    }
                ],
                "latest_bos": {...} or None,
                "latest_choch": {...} or None,
                "higher_highs": int,
                "higher_lows": int,
                "lower_highs": int,
                "lower_lows": int,
                "swing_highs": [...],
                "swing_lows": [...]
            }
        """
        
        if len(candles) < self.swing_strength * 2 + 1:
            logger.warning("insufficient_candles_for_structure", count=len(candles))
            return self._empty_result()
        
        candles_to_analyze = candles[-self.lookback_periods:]
        
        # 1. Detect swing points
        swing_highs = self._detect_swing_highs(candles_to_analyze)
        swing_lows = self._detect_swing_lows(candles_to_analyze)
        
        # 2. Analyze swing patterns (HH, HL, LH, LL)
        swing_patterns = self._analyze_swing_patterns(swing_highs, swing_lows)
        
        # 3. Detect structure breaks (BOS, CHoCH)
        structure_events = self._detect_structure_breaks(
            candles_to_analyze,
            swing_highs,
            swing_lows,
            swing_patterns
        )
        
        # 4. Determine overall trend
        trend = self._determine_trend(swing_patterns, structure_events)
        
        latest_bos = self._get_latest_event(structure_events, "BOS")
        latest_choch = self._get_latest_event(structure_events, "CHoCH")
        
        result = {
            "trend": trend,
            "structure_events": structure_events,
            "latest_bos": latest_bos,
            "latest_choch": latest_choch,
            "higher_highs": swing_patterns["higher_highs"],
            "higher_lows": swing_patterns["higher_lows"],
            "lower_highs": swing_patterns["lower_highs"],
            "lower_lows": swing_patterns["lower_lows"],
            "swing_highs": swing_highs,
            "swing_lows": swing_lows,
            "timeframe": self.timeframe
        }
        
        logger.info(
            "market_structure_complete",
            timeframe=self.timeframe,
            trend=trend,
            events=len(structure_events)
        )
        
        return result
    
    def _detect_swing_highs(self, candles: List[Dict]) -> List[Dict]:
        """Detect swing highs."""
        swing_highs = []
        n = self.swing_strength
        
        for i in range(n, len(candles) - n):
            current_high = candles[i]["high"]
            
            is_swing = all(
                candles[j]["high"] < current_high
                for j in range(i - n, i + n + 1)
                if j != i
            )
            
            if is_swing:
                swing_highs.append({
                    "price": current_high,
                    "timestamp": candles[i].get("timestamp", ""),
                    "index": i
                })
        
        return swing_highs
    
    def _detect_swing_lows(self, candles: List[Dict]) -> List[Dict]:
        """Detect swing lows."""
        swing_lows = []
        n = self.swing_strength
        
        for i in range(n, len(candles) - n):
            current_low = candles[i]["low"]
            
            is_swing = all(
                candles[j]["low"] > current_low
                for j in range(i - n, i + n + 1)
                if j != i
            )
            
            if is_swing:
                swing_lows.append({
                    "price": current_low,
                    "timestamp": candles[i].get("timestamp", ""),
                    "index": i
                })
        
        return swing_lows
    
    def _analyze_swing_patterns(
        self,
        swing_highs: List[Dict],
        swing_lows: List[Dict]
    ) -> Dict[str, int]:
        """
        Analyze swing patterns:
        - Higher Highs (HH): New swing high > previous swing high
        - Higher Lows (HL): New swing low > previous swing low
        - Lower Highs (LH): New swing high < previous swing high
        - Lower Lows (LL): New swing low < previous swing low
        """
        patterns = {
            "higher_highs": 0,
            "higher_lows": 0,
            "lower_highs": 0,
            "lower_lows": 0
        }
        
        # Analyze swing highs
        for i in range(1, len(swing_highs)):
            if swing_highs[i]["price"] > swing_highs[i - 1]["price"]:
                patterns["higher_highs"] += 1
            else:
                patterns["lower_highs"] += 1
        
        # Analyze swing lows
        for i in range(1, len(swing_lows)):
            if swing_lows[i]["price"] > swing_lows[i - 1]["price"]:
                patterns["higher_lows"] += 1
            else:
                patterns["lower_lows"] += 1
        
        return patterns
    
    def _detect_structure_breaks(
        self,
        candles: List[Dict],
        swing_highs: List[Dict],
        swing_lows: List[Dict],
        swing_patterns: Dict[str, int]
    ) -> List[Dict]:
        """
        Detect BOS and CHoCH events.
        
        BOS (Break of Structure):
        - Bullish BOS: Price breaks above recent swing high in uptrend
        - Bearish BOS: Price breaks below recent swing low in downtrend
        
        CHoCH (Change of Character):
        - Bullish CHoCH: Price breaks above swing high while in downtrend
        - Bearish CHoCH: Price breaks below swing low while in uptrend
        """
        events = []
        
        # Simple trend detection based on swing patterns
        bullish_bias = (
            swing_patterns["higher_highs"] + swing_patterns["higher_lows"]
        ) > (
            swing_patterns["lower_highs"] + swing_patterns["lower_lows"]
        )
        
        current_trend = "bullish" if bullish_bias else "bearish"
        
        # Check for breaks of swing highs
        for swing_high in swing_highs:
            swing_index = swing_high["index"]
            swing_price = swing_high["price"]
            
            for i in range(swing_index + 1, len(candles)):
                candle = candles[i]
                
                # Price broke above swing high
                if candle["close"] > swing_price:
                    # BOS if in uptrend, CHoCH if in downtrend
                    event_type = "BOS" if current_trend == "bullish" else "CHoCH"
                    
                    events.append({
                        "type": event_type,
                        "direction": "bullish",
                        "level": swing_price,
                        "timestamp": candle.get("timestamp", ""),
                        "candle_index": i
                    })
                    
                    # Update trend if CHoCH
                    if event_type == "CHoCH":
                        current_trend = "bullish"
                    
                    break
        
        # Check for breaks of swing lows
        for swing_low in swing_lows:
            swing_index = swing_low["index"]
            swing_price = swing_low["price"]
            
            for i in range(swing_index + 1, len(candles)):
                candle = candles[i]
                
                # Price broke below swing low
                if candle["close"] < swing_price:
                    event_type = "BOS" if current_trend == "bearish" else "CHoCH"
                    
                    events.append({
                        "type": event_type,
                        "direction": "bearish",
                        "level": swing_price,
                        "timestamp": candle.get("timestamp", ""),
                        "candle_index": i
                    })
                    
                    if event_type == "CHoCH":
                        current_trend = "bearish"
                    
                    break
        
        # Sort by candle index
        events.sort(key=lambda x: x["candle_index"])
        
        return events
    
    def _determine_trend(
        self,
        swing_patterns: Dict[str, int],
        structure_events: List[Dict]
    ) -> str:
        """
        Determine overall trend based on swing patterns and recent structure events.
        """
        # Check most recent structure event
        if structure_events:
            recent_event = structure_events[-1]
            if recent_event["type"] == "BOS":
                return recent_event["direction"]
            elif recent_event["type"] == "CHoCH":
                return recent_event["direction"]  # Trend changed
        
        # Fallback to swing patterns
        bullish_count = swing_patterns["higher_highs"] + swing_patterns["higher_lows"]
        bearish_count = swing_patterns["lower_highs"] + swing_patterns["lower_lows"]
        
        if bullish_count > bearish_count * 1.5:
            return "bullish"
        elif bearish_count > bullish_count * 1.5:
            return "bearish"
        else:
            return "ranging"
    
    def _get_latest_event(
        self,
        events: List[Dict],
        event_type: str
    ) -> Optional[Dict]:
        """Get the latest event of a specific type."""
        matching = [e for e in events if e["type"] == event_type]
        return matching[-1] if matching else None
    
    def _empty_result(self) -> Dict[str, Any]:
        """Return empty result structure."""
        return {
            "trend": "ranging",
            "structure_events": [],
            "latest_bos": None,
            "latest_choch": None,
            "higher_highs": 0,
            "higher_lows": 0,
            "lower_highs": 0,
            "lower_lows": 0,
            "swing_highs": [],
            "swing_lows": [],
            "timeframe": self.timeframe
        }

