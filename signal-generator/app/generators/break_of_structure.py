"""
Break of Structure (BOS) Signal Generator

Detects when price breaks market structure (higher highs/lower lows).
"""
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class BreakOfStructureSignalGenerator(BaseSignalGenerator):
    """
    Break of Structure (BOS) signal generator.
    
    Detects market structure breaks:
    - Bullish BOS: Price breaks above most recent structure high (continuation)
    - Bearish BOS: Price breaks below most recent structure low (continuation)
    
    Indicates trend continuation.
    
    Configuration:
        - tickers: List of tickers to monitor
        - lookback_periods: Periods to track structure (default: 20)
        - min_swing_strength: Bars on each side of swing (default: 3)
        - timeframe: Candle resolution (default: "60")
        - confidence: Confidence level (default: 0.75)
    
    Example config:
        {
            "tickers": ["EUR_USD", "GBP_USD"],
            "lookback_periods": 20,
            "min_swing_strength": 3,
            "timeframe": "60",
            "confidence": 0.75
        }
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_data = MarketDataFetcher()
        self.lookback_periods = self.config.get("lookback_periods", 20)
        self.min_swing_strength = self.config.get("min_swing_strength", 3)
        self.timeframe = self.config.get("timeframe", "60")
        self.confidence = self.config.get("confidence", 0.75)
    
    def _validate_config(self):
        """Validate BOS configuration."""
        lookback = self.config.get("lookback_periods", 20)
        if lookback < 10:
            raise ValueError(f"lookback_periods should be >= 10, got {lookback}")
    
    def _find_structure_points(self, highs: List[float], lows: List[float], strength: int) -> tuple:
        """Find all swing highs and lows that define structure."""
        swing_highs = []
        swing_lows = []
        
        for i in range(strength, len(highs) - strength):
            # Check for swing high
            is_high = all(highs[i] >= highs[i-j] for j in range(1, strength+1)) and \
                     all(highs[i] >= highs[i+j] for j in range(1, strength+1))
            
            if is_high:
                swing_highs.append((i, highs[i]))
            
            # Check for swing low
            is_low = all(lows[i] <= lows[i-j] for j in range(1, strength+1)) and \
                    all(lows[i] <= lows[i+j] for j in range(1, strength+1))
            
            if is_low:
                swing_lows.append((i, lows[i]))
        
        return swing_highs, swing_lows
    
    async def generate(self) -> List[Signal]:
        """Generate break of structure signals."""
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "break_of_structure_scan_started",
            tickers=tickers,
            lookback_periods=self.lookback_periods,
            swing_strength=self.min_swing_strength
        )
        
        for ticker in tickers:
            try:
                # Fetch candles
                lookback_days = self.lookback_periods + self.min_swing_strength + 10
                candles_df = await self.market_data.fetch_candles(
                    symbol=ticker,
                    resolution=self.timeframe,
                    lookback_days=lookback_days
                )
                
                # Convert DataFrame to list of dicts
                candles = self._dataframe_to_candles(candles_df)
                
                if not candles or len(candles) < self.lookback_periods:
                    logger.debug("insufficient_candle_data", ticker=ticker)
                    continue
                
                highs = [c["h"] for c in candles]
                lows = [c["l"] for c in candles]
                closes = [c["c"] for c in candles]
                
                # Find all swing points
                swing_highs, swing_lows = self._find_structure_points(
                    highs, lows, self.min_swing_strength
                )
                
                if len(swing_highs) < 2 and len(swing_lows) < 2:
                    logger.debug("insufficient_structure_points", ticker=ticker)
                    continue
                
                current_close = closes[-1]
                previous_close = closes[-2]
                
                # Bullish BOS: Price breaks above most recent structure high
                if len(swing_highs) >= 2:
                    # Get most recent confirmed swing high
                    most_recent_high = swing_highs[-1][1]
                    most_recent_high_idx = swing_highs[-1][0]
                    
                    # Check if current price breaks above it
                    bullish_bos = (
                        current_close > most_recent_high and 
                        previous_close <= most_recent_high
                    )
                    
                    if bullish_bos:
                        bars_since = len(highs) - most_recent_high_idx - 1
                        
                        logger.info(
                            "bullish_bos_detected",
                            ticker=ticker,
                            structure_high=most_recent_high,
                            current_close=current_close,
                            bars_since=bars_since
                        )
                        
                        # Check if this is part of higher high pattern
                        if len(swing_highs) >= 2:
                            previous_high = swing_highs[-2][1]
                            is_higher_high = most_recent_high > previous_high
                            confidence_boost = 0.10 if is_higher_high else 0
                        else:
                            confidence_boost = 0
                        
                        ticker_signal = TickerSignal(
                            ticker=ticker,
                            signal=BiasType.BULLISH,
                            confidence=min((self.confidence + confidence_boost) * 100, 90),
                            reasoning=(
                                f"Bullish Break of Structure: Price broke above structure high "
                                f"at {most_recent_high:.5f} ({bars_since} bars ago). "
                                f"Current: {current_close:.5f}. Trend continuation confirmed."
                            )
                        )
                        
                        signal = Signal(
                            signal_type=SignalType.BREAK_OF_STRUCTURE_BULLISH,
                            source="bos_generator",
                            tickers=[ticker_signal],
                            metadata={
                                "structure_high": most_recent_high,
                                "current_price": current_close,
                                "bars_since": bars_since
                            }
                        )
                        signals.append(signal)
                
                # Bearish BOS: Price breaks below most recent structure low
                if len(swing_lows) >= 2:
                    # Get most recent confirmed swing low
                    most_recent_low = swing_lows[-1][1]
                    most_recent_low_idx = swing_lows[-1][0]
                    
                    # Check if current price breaks below it
                    bearish_bos = (
                        current_close < most_recent_low and 
                        previous_close >= most_recent_low
                    )
                    
                    if bearish_bos:
                        bars_since = len(lows) - most_recent_low_idx - 1
                        
                        logger.info(
                            "bearish_bos_detected",
                            ticker=ticker,
                            structure_low=most_recent_low,
                            current_close=current_close,
                            bars_since=bars_since
                        )
                        
                        # Check if this is part of lower low pattern
                        if len(swing_lows) >= 2:
                            previous_low = swing_lows[-2][1]
                            is_lower_low = most_recent_low < previous_low
                            confidence_boost = 0.10 if is_lower_low else 0
                        else:
                            confidence_boost = 0
                        
                        ticker_signal = TickerSignal(
                            ticker=ticker,
                            signal=BiasType.BEARISH,
                            confidence=min((self.confidence + confidence_boost) * 100, 90),
                            reasoning=(
                                f"Bearish Break of Structure: Price broke below structure low "
                                f"at {most_recent_low:.5f} ({bars_since} bars ago). "
                                f"Current: {current_close:.5f}. Trend continuation confirmed."
                            )
                        )
                        
                        signal = Signal(
                            signal_type=SignalType.BREAK_OF_STRUCTURE_BEARISH,
                            source="bos_generator",
                            tickers=[ticker_signal],
                            metadata={
                                "structure_low": most_recent_low,
                                "current_price": current_close,
                                "bars_since": bars_since
                            }
                        )
                        signals.append(signal)
                
            except Exception as e:
                logger.error(
                    "break_of_structure_error",
                    ticker=ticker,
                    error=str(e),
                    exc_info=True
                )
                continue
        
        logger.info(
            "break_of_structure_scan_completed",
            signals_generated=len(signals),
            tickers_with_signal=[s.tickers[0].ticker for s in signals] if signals else []
        )
        
        return signals
