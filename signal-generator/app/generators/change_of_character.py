"""
Change of Character (CHoCH) Signal Generator

Detects market structure reversals (trend changes).
"""
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class ChangeOfCharacterSignalGenerator(BaseSignalGenerator):
    """
    Change of Character (CHoCH) signal generator.
    
    Detects trend reversals:
    - Bullish CHoCH: In downtrend, price breaks above previous lower high
    - Bearish CHoCH: In uptrend, price breaks below previous higher low
    
    This signals potential trend reversal.
    
    Configuration:
        - tickers: List of tickers to monitor
        - lookback_periods: Periods to identify trend (default: 30)
        - min_swing_strength: Bars on each side of swing (default: 3)
        - timeframe: Candle resolution (default: "60")
        - confidence: Confidence level (default: 0.85)
    
    Example config:
        {
            "tickers": ["EUR_USD", "GBP_USD"],
            "lookback_periods": 30,
            "min_swing_strength": 3,
            "timeframe": "60",
            "confidence": 0.85
        }
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_data = MarketDataFetcher()
        self.lookback_periods = self.config.get("lookback_periods", 30)
        self.min_swing_strength = self.config.get("min_swing_strength", 3)
        self.timeframe = self.config.get("timeframe", "60")
        self.confidence = self.config.get("confidence", 0.85)
    
    def _validate_config(self):
        """Validate CHoCH configuration."""
        lookback = self.config.get("lookback_periods", 30)
        if lookback < 15:
            raise ValueError(f"lookback_periods should be >= 15, got {lookback}")
    
    def _find_swing_points(self, highs: List[float], lows: List[float], strength: int) -> tuple:
        """Find all swing highs and lows."""
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
    
    def _is_downtrend(self, swing_highs: List[tuple], swing_lows: List[tuple]) -> bool:
        """Check if we're in a downtrend (lower highs, lower lows)."""
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return False
        
        recent_highs = swing_highs[-3:]
        recent_lows = swing_lows[-3:]
        
        # Check for lower highs
        lower_highs = all(recent_highs[i][1] > recent_highs[i+1][1] for i in range(len(recent_highs)-1))
        
        # Check for lower lows
        lower_lows = all(recent_lows[i][1] > recent_lows[i+1][1] for i in range(len(recent_lows)-1))
        
        return lower_highs and lower_lows
    
    def _is_uptrend(self, swing_highs: List[tuple], swing_lows: List[tuple]) -> bool:
        """Check if we're in an uptrend (higher highs, higher lows)."""
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return False
        
        recent_highs = swing_highs[-3:]
        recent_lows = swing_lows[-3:]
        
        # Check for higher highs
        higher_highs = all(recent_highs[i][1] < recent_highs[i+1][1] for i in range(len(recent_highs)-1))
        
        # Check for higher lows
        higher_lows = all(recent_lows[i][1] < recent_lows[i+1][1] for i in range(len(recent_lows)-1))
        
        return higher_highs and higher_lows
    
    async def generate(self) -> List[Signal]:
        """Generate CHoCH signals."""
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "choch_scan_started",
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
                swing_highs, swing_lows = self._find_swing_points(
                    highs, lows, self.min_swing_strength
                )
                
                if len(swing_highs) < 2 or len(swing_lows) < 2:
                    logger.debug("insufficient_swing_points", ticker=ticker)
                    continue
                
                current_close = closes[-1]
                previous_close = closes[-2]
                
                # Check for Bullish CHoCH (in downtrend, price breaks previous lower high)
                if self._is_downtrend(swing_highs, swing_lows):
                    if len(swing_highs) >= 2:
                        previous_lower_high = swing_highs[-2][1]
                        
                        # Check if price just broke above previous lower high
                        bullish_choch = (
                            current_close > previous_lower_high and 
                            previous_close <= previous_lower_high
                        )
                        
                        if bullish_choch:
                            logger.info(
                                "bullish_choch_detected",
                                ticker=ticker,
                                previous_lower_high=previous_lower_high,
                                current_close=current_close
                            )
                            
                            ticker_signal = TickerSignal(
                                ticker=ticker,
                                signal=BiasType.BULLISH,
                                confidence=self.confidence * 100,
                                reasoning=(
                                    f"Bullish CHoCH: In downtrend, price broke above previous lower high "
                                    f"at {previous_lower_high:.5f}. Current: {current_close:.5f}. "
                                    f"Trend reversal signal - potential shift to uptrend."
                                )
                            )
                            
                            signal = Signal(
                                signal_type=SignalType.CHOCH_BULLISH,
                                source="choch_generator",
                                tickers=[ticker_signal],
                                metadata={
                                    "previous_lower_high": previous_lower_high,
                                    "current_price": current_close,
                                    "trend": "downtrend_to_uptrend"
                                }
                            )
                            signals.append(signal)
                
                # Check for Bearish CHoCH (in uptrend, price breaks previous higher low)
                if self._is_uptrend(swing_highs, swing_lows):
                    if len(swing_lows) >= 2:
                        previous_higher_low = swing_lows[-2][1]
                        
                        # Check if price just broke below previous higher low
                        bearish_choch = (
                            current_close < previous_higher_low and 
                            previous_close >= previous_higher_low
                        )
                        
                        if bearish_choch:
                            logger.info(
                                "bearish_choch_detected",
                                ticker=ticker,
                                previous_higher_low=previous_higher_low,
                                current_close=current_close
                            )
                            
                            ticker_signal = TickerSignal(
                                ticker=ticker,
                                signal=BiasType.BEARISH,
                                confidence=self.confidence * 100,
                                reasoning=(
                                    f"Bearish CHoCH: In uptrend, price broke below previous higher low "
                                    f"at {previous_higher_low:.5f}. Current: {current_close:.5f}. "
                                    f"Trend reversal signal - potential shift to downtrend."
                                )
                            )
                            
                            signal = Signal(
                                signal_type=SignalType.CHOCH_BEARISH,
                                source="choch_generator",
                                tickers=[ticker_signal],
                                metadata={
                                    "previous_higher_low": previous_higher_low,
                                    "current_price": current_close,
                                    "trend": "uptrend_to_downtrend"
                                }
                            )
                            signals.append(signal)
                
            except Exception as e:
                logger.error(
                    "choch_error",
                    ticker=ticker,
                    error=str(e),
                    exc_info=True
                )
                continue
        
        logger.info(
            "choch_scan_completed",
            signals_generated=len(signals),
            tickers_with_signal=[s.tickers[0].ticker for s in signals] if signals else []
        )
        
        return signals
