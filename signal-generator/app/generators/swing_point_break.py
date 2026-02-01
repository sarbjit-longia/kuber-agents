"""
Swing Point Break Signal Generator

Detects when price breaks above previous swing highs or below previous swing lows.
"""
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class SwingPointBreakSignalGenerator(BaseSignalGenerator):
    """
    Swing Point Break signal generator.
    
    Monitors for price breaking previous swing points:
    - Price breaks above swing high: BULLISH
    - Price breaks below swing low: BEARISH
    
    Swing points are local maxima/minima over a lookback period.
    
    Configuration:
        - tickers: List of tickers to monitor
        - lookback_periods: Periods to identify swing points (default: 20)
        - timeframe: Candle resolution (default: "60")
        - min_swing_strength: Minimum bars on each side of swing (default: 2)
        - confidence: Confidence level (default: 0.80)
    
    Example config:
        {
            "tickers": ["EUR_USD", "GBP_USD"],
            "lookback_periods": 20,
            "timeframe": "60",
            "min_swing_strength": 2,
            "confidence": 0.80
        }
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_data = MarketDataFetcher()
        self.lookback_periods = self.config.get("lookback_periods", 20)
        self.timeframe = self.config.get("timeframe", "60")
        self.min_swing_strength = self.config.get("min_swing_strength", 2)
        self.confidence = self.config.get("confidence", 0.80)
    
    def _validate_config(self):
        """Validate swing point configuration."""
        lookback = self.config.get("lookback_periods", 20)
        if lookback < 5:
            raise ValueError(f"lookback_periods should be >= 5, got {lookback}")
        
        swing_strength = self.config.get("min_swing_strength", 2)
        if swing_strength < 1:
            raise ValueError("min_swing_strength must be >= 1")
    
    def _find_swing_high(self, highs: List[float], idx: int, strength: int) -> bool:
        """Check if index is a swing high."""
        if idx < strength or idx >= len(highs) - strength:
            return False
        
        pivot_high = highs[idx]
        
        # Check left side
        for i in range(idx - strength, idx):
            if highs[i] >= pivot_high:
                return False
        
        # Check right side
        for i in range(idx + 1, idx + strength + 1):
            if highs[i] >= pivot_high:
                return False
        
        return True
    
    def _find_swing_low(self, lows: List[float], idx: int, strength: int) -> bool:
        """Check if index is a swing low."""
        if idx < strength or idx >= len(lows) - strength:
            return False
        
        pivot_low = lows[idx]
        
        # Check left side
        for i in range(idx - strength, idx):
            if lows[i] <= pivot_low:
                return False
        
        # Check right side
        for i in range(idx + 1, idx + strength + 1):
            if lows[i] <= pivot_low:
                return False
        
        return True
    
    async def generate(self) -> List[Signal]:
        """Generate swing point break signals."""
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "swing_point_break_scan_started",
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
                
                if not candles or len(candles) < self.lookback_periods + self.min_swing_strength:
                    logger.debug("insufficient_candle_data", ticker=ticker)
                    continue
                
                highs = [c["h"] for c in candles]
                lows = [c["l"] for c in candles]
                closes = [c["c"] for c in candles]
                
                # Find most recent swing high/low
                last_swing_high = None
                last_swing_low = None
                last_swing_high_idx = None
                last_swing_low_idx = None
                
                # Search backwards from recent (excluding last few bars which can't be confirmed swings)
                for i in range(len(highs) - self.min_swing_strength - 1, self.min_swing_strength, -1):
                    if last_swing_high is None and self._find_swing_high(highs, i, self.min_swing_strength):
                        last_swing_high = highs[i]
                        last_swing_high_idx = i
                    
                    if last_swing_low is None and self._find_swing_low(lows, i, self.min_swing_strength):
                        last_swing_low = lows[i]
                        last_swing_low_idx = i
                    
                    # Stop if we found both
                    if last_swing_high is not None and last_swing_low is not None:
                        break
                
                if last_swing_high is None and last_swing_low is None:
                    logger.debug("no_swing_points_found", ticker=ticker)
                    continue
                
                # Check if current price breaks swing points
                current_close = closes[-1]
                previous_close = closes[-2]
                
                # Bullish break: price breaks above swing high
                if last_swing_high is not None:
                    bullish_break = (
                        current_close > last_swing_high and 
                        previous_close <= last_swing_high
                    )
                    
                    if bullish_break:
                        logger.info(
                            "swing_high_break_detected",
                            ticker=ticker,
                            current_close=current_close,
                            swing_high=last_swing_high,
                            bars_ago=len(highs) - last_swing_high_idx - 1
                        )
                        
                        # Higher confidence if swing was recent and strong
                        bars_ago = len(highs) - last_swing_high_idx - 1
                        recency_factor = max(0, 1 - (bars_ago / self.lookback_periods))
                        confidence = self.confidence + recency_factor * 0.15
                        
                        ticker_signal = TickerSignal(
                            ticker=ticker,
                            signal=BiasType.BULLISH,
                            confidence=min(confidence * 100, 95),
                            reasoning=(
                                f"Price broke above swing high at {last_swing_high:.5f} "
                                f"({bars_ago} bars ago). Current: {current_close:.5f}. "
                                f"Bullish momentum confirmed."
                            )
                        )
                        
                        signal = Signal(
                            signal_type=SignalType.SWING_POINT_BREAK_BULLISH,
                            source="swing_point_generator",
                            tickers=[ticker_signal],
                            metadata=self._enrich_metadata({
                                "swing_high": last_swing_high,
                                "bars_ago": bars_ago,
                                "current_price": current_close
                            })
                        )
                        signals.append(signal)
                
                # Bearish break: price breaks below swing low
                if last_swing_low is not None:
                    bearish_break = (
                        current_close < last_swing_low and 
                        previous_close >= last_swing_low
                    )
                    
                    if bearish_break:
                        logger.info(
                            "swing_low_break_detected",
                            ticker=ticker,
                            current_close=current_close,
                            swing_low=last_swing_low,
                            bars_ago=len(lows) - last_swing_low_idx - 1
                        )
                        
                        bars_ago = len(lows) - last_swing_low_idx - 1
                        recency_factor = max(0, 1 - (bars_ago / self.lookback_periods))
                        confidence = self.confidence + recency_factor * 0.15
                        
                        ticker_signal = TickerSignal(
                            ticker=ticker,
                            signal=BiasType.BEARISH,
                            confidence=min(confidence * 100, 95),
                            reasoning=(
                                f"Price broke below swing low at {last_swing_low:.5f} "
                                f"({bars_ago} bars ago). Current: {current_close:.5f}. "
                                f"Bearish momentum confirmed."
                            )
                        )
                        
                        signal = Signal(
                            signal_type=SignalType.SWING_POINT_BREAK_BEARISH,
                            source="swing_point_generator",
                            tickers=[ticker_signal],
                            metadata=self._enrich_metadata({
                                "swing_low": last_swing_low,
                                "bars_ago": bars_ago,
                                "current_price": current_close
                            })
                        )
                        signals.append(signal)
                
            except Exception as e:
                logger.error(
                    "swing_point_break_error",
                    ticker=ticker,
                    error=str(e),
                    exc_info=True
                )
                continue
        
        logger.info(
            "swing_point_break_scan_completed",
            signals_generated=len(signals),
            tickers_with_signal=[s.tickers[0].ticker for s in signals] if signals else []
        )
        
        return signals
