"""
Volume Profile POC Break Signal Generator

Detects breaks of Point of Control (highest volume price level).
"""
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class VolumeProfilePOCSignalGenerator(BaseSignalGenerator):
    """
    Volume Profile POC Break signal generator.
    
    Approximates Point of Control (POC) using volume-weighted average price:
    - Bullish POC Break: Price breaks above POC from below
    - Bearish POC Break: Price breaks below POC from above
    
    POC often acts as strong support/resistance.
    
    Configuration:
        - tickers: List of tickers to monitor
        - lookback_periods: Periods to calculate POC (default: 20)
        - timeframe: Candle resolution (default: "60")
        - confidence: Confidence level (default: 0.75)
    
    Example config:
        {
            "tickers": ["EUR_USD", "GBP_USD"],
            "lookback_periods": 20,
            "timeframe": "60",
            "confidence": 0.75
        }
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_data = MarketDataFetcher()
        self.lookback_periods = self.config.get("lookback_periods", 20)
        self.timeframe = self.config.get("timeframe", "60")
        self.confidence = self.config.get("confidence", 0.75)
    
    def _validate_config(self):
        """Validate POC configuration."""
        lookback = self.config.get("lookback_periods", 20)
        if lookback < 10:
            raise ValueError(f"lookback_periods should be >= 10, got {lookback}")
    
    def _calculate_vwap(self, candles: List[Dict]) -> float:
        """Calculate Volume Weighted Average Price as POC approximation."""
        total_volume = 0
        total_price_volume = 0
        
        for candle in candles:
            typical_price = (candle["h"] + candle["l"] + candle["c"]) / 3
            volume = candle.get("v", 1)  # Default volume to 1 if not available
            
            total_price_volume += typical_price * volume
            total_volume += volume
        
        if total_volume == 0:
            return sum([c["c"] for c in candles]) / len(candles)
        
        return total_price_volume / total_volume
    
    async def generate(self) -> List[Signal]:
        """Generate POC break signals."""
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "poc_break_scan_started",
            tickers=tickers,
            lookback_periods=self.lookback_periods
        )
        
        for ticker in tickers:
            try:
                # Fetch candles
                lookback_days = self.lookback_periods + 10
                candles_df = await self.market_data.fetch_candles(
                    symbol=ticker,
                    resolution=self.timeframe,
                    lookback_days=lookback_days
                )
                
                # Convert DataFrame to list of dicts
                candles = self._dataframe_to_candles(candles_df)
                
                if not candles or len(candles) < self.lookback_periods + 2:
                    logger.debug("insufficient_candle_data", ticker=ticker)
                    continue
                
                # Calculate POC for lookback period (excluding last 2 candles)
                lookback_candles = candles[-(self.lookback_periods+2):-2]
                poc = self._calculate_vwap(lookback_candles)
                
                # Check current and previous close relative to POC
                current_close = candles[-1]["c"]
                previous_close = candles[-2]["c"]
                
                # Bullish POC Break (price was below, now above)
                bullish_break = previous_close < poc and current_close > poc
                
                if bullish_break:
                    distance_pips = abs(current_close - poc) / (0.01 if "JPY" in ticker.upper() else 0.0001)
                    
                    logger.info(
                        "bullish_poc_break_detected",
                        ticker=ticker,
                        poc=poc,
                        previous_close=previous_close,
                        current_close=current_close,
                        distance_pips=distance_pips
                    )
                    
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BULLISH,
                        confidence=self.confidence * 100,
                        reasoning=(
                            f"Bullish POC Break: Price broke above Point of Control at {poc:.5f}. "
                            f"Previous: {previous_close:.5f}, Current: {current_close:.5f}. "
                            f"Strong resistance turned support - bullish continuation expected."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.POC_BREAK_BULLISH,
                        source="poc_break_generator",
                        tickers=[ticker_signal],
                        metadata={
                            "poc": poc,
                            "previous_close": previous_close,
                            "current_close": current_close,
                            "distance_pips": distance_pips
                        }
                    )
                    signals.append(signal)
                
                # Bearish POC Break (price was above, now below)
                bearish_break = previous_close > poc and current_close < poc
                
                if bearish_break:
                    distance_pips = abs(current_close - poc) / (0.01 if "JPY" in ticker.upper() else 0.0001)
                    
                    logger.info(
                        "bearish_poc_break_detected",
                        ticker=ticker,
                        poc=poc,
                        previous_close=previous_close,
                        current_close=current_close,
                        distance_pips=distance_pips
                    )
                    
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BEARISH,
                        confidence=self.confidence * 100,
                        reasoning=(
                            f"Bearish POC Break: Price broke below Point of Control at {poc:.5f}. "
                            f"Previous: {previous_close:.5f}, Current: {current_close:.5f}. "
                            f"Strong support turned resistance - bearish continuation expected."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.POC_BREAK_BEARISH,
                        source="poc_break_generator",
                        tickers=[ticker_signal],
                        metadata={
                            "poc": poc,
                            "previous_close": previous_close,
                            "current_close": current_close,
                            "distance_pips": distance_pips
                        }
                    )
                    signals.append(signal)
                
            except Exception as e:
                logger.error(
                    "poc_break_error",
                    ticker=ticker,
                    error=str(e),
                    exc_info=True
                )
                continue
        
        logger.info(
            "poc_break_scan_completed",
            signals_generated=len(signals),
            tickers_with_signal=[s.tickers[0].ticker for s in signals] if signals else []
        )
        
        return signals
