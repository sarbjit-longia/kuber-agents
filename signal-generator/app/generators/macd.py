"""
MACD Signal Generator

Monitors for MACD crossover signals.
"""
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class MACDSignalGenerator(BaseSignalGenerator):
    """
    MACD (Moving Average Convergence Divergence) signal generator.
    
    Monitors a watchlist of tickers for MACD crossover patterns:
    - MACD line crosses above signal line: Generates BULLISH signal
    - MACD line crosses below signal line: Generates BEARISH signal
    
    Configuration:
        - tickers: List of tickers to monitor
        - fast_period: Fast EMA period (default: 12)
        - slow_period: Slow EMA period (default: 26)
        - signal_period: Signal line EMA period (default: 9)
        - timeframe: Candle resolution (default: "D" for daily)
        - confidence: Confidence level for generated signals (default: 0.80)
        - require_histogram_confirmation: Require histogram to be positive/negative (default: True)
    
    Example config:
        {
            "tickers": ["AAPL", "MSFT", "GOOGL"],
            "fast_period": 12,
            "slow_period": 26,
            "signal_period": 9,
            "timeframe": "D",
            "confidence": 0.80,
            "require_histogram_confirmation": True
        }
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_data = MarketDataFetcher()
        self.fast_period = self.config.get("fast_period", 12)
        self.slow_period = self.config.get("slow_period", 26)
        self.signal_period = self.config.get("signal_period", 9)
        self.timeframe = self.config.get("timeframe", "D")
        self.confidence = self.config.get("confidence", 0.80)
        self.require_histogram = self.config.get("require_histogram_confirmation", True)
    
    def _validate_config(self):
        """Validate MACD generator configuration."""
        fast = self.config.get("fast_period", 12)
        slow = self.config.get("slow_period", 26)
        signal = self.config.get("signal_period", 9)
        
        if fast >= slow:
            raise ValueError(f"fast_period ({fast}) must be less than slow_period ({slow})")
        
        if signal < 1:
            raise ValueError(f"signal_period must be >= 1, got {signal}")
        
        confidence = self.config.get("confidence", 0.80)
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
    
    async def generate(self) -> List[Signal]:
        """
        Check for MACD crossovers and generate signals.
        
        Returns:
            List of Signal objects for tickers with MACD crossovers
        """
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "macd_scan_started",
            tickers=tickers,
            fast=self.fast_period,
            slow=self.slow_period,
            signal=self.signal_period
        )
        
        for ticker in tickers:
            try:
                # Fetch MACD from Finnhub (pre-calculated)
                lookback_days = 120  # Enough for MACD analysis
                macd_data = await self.market_data.fetch_indicator(
                    symbol=ticker,
                    indicator="macd",
                    resolution=self.timeframe,
                    lookback_days=lookback_days,
                    fastperiod=self.fast_period,
                    slowperiod=self.slow_period,
                    signalperiod=self.signal_period,
                    seriestype="c"  # close price
                )
                
                if not macd_data or "macd" not in macd_data or "macdSignal" not in macd_data:
                    logger.warning(
                        "macd_data_unavailable",
                        ticker=ticker
                    )
                    continue
                
                macd_values = macd_data["macd"]
                signal_values = macd_data["macdSignal"]
                histogram_values = macd_data.get("macdHist", [])
                
                # Need at least 2 values to detect crossover
                if len(macd_values) < 2 or len(signal_values) < 2:
                    logger.warning(
                        "insufficient_macd_data",
                        ticker=ticker,
                        available=len(macd_values)
                    )
                    continue
                
                # Get current and previous values
                current_macd = macd_values[-1]
                current_signal = signal_values[-1]
                current_histogram = histogram_values[-1] if histogram_values else (current_macd - current_signal)
                
                previous_macd = macd_values[-2]
                previous_signal = signal_values[-2]
                previous_histogram = histogram_values[-2] if len(histogram_values) > 1 else (previous_macd - previous_signal)
                
                # Get current price
                current_price = macd_data.get("c", [None])[-1] if "c" in macd_data else None
                
                # Detect bullish crossover (MACD crosses above signal line)
                if current_macd > current_signal and previous_macd <= previous_signal:
                    # Optional: Require histogram to be positive for confirmation
                    if self.require_histogram and current_histogram <= 0:
                        logger.debug(
                            "macd_bullish_crossover_rejected",
                            ticker=ticker,
                            reason="histogram not positive",
                            histogram=round(current_histogram, 4)
                        )
                        continue
                    
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BULLISH,
                        confidence=self.confidence * 100,
                        reasoning=(
                            f"MACD bullish crossover: MACD line ({current_macd:.4f}) crossed above "
                            f"signal line ({current_signal:.4f}). Histogram: {current_histogram:.4f}"
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.MACD_BULLISH,
                        source="macd_generator",
                        tickers=[ticker_signal],
                        metadata=self._enrich_metadata({
                            "fast_period": self.fast_period,
                            "slow_period": self.slow_period,
                            "signal_period": self.signal_period,
                            "current_macd": round(current_macd, 4),
                            "current_signal": round(current_signal, 4),
                            "current_histogram": round(current_histogram, 4),
                            "previous_macd": round(previous_macd, 4),
                            "previous_signal": round(previous_signal, 4),
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        })
                    )
                    
                    signals.append(signal)
                    
                    logger.info(
                        "macd_bullish_signal_generated",
                        signal_id=str(signal.signal_id),
                        ticker=ticker,
                        macd=round(current_macd, 4),
                        signal_line=round(current_signal, 4)
                    )
                
                # Detect bearish crossover (MACD crosses below signal line)
                elif current_macd < current_signal and previous_macd >= previous_signal:
                    # Optional: Require histogram to be negative for confirmation
                    if self.require_histogram and current_histogram >= 0:
                        logger.debug(
                            "macd_bearish_crossover_rejected",
                            ticker=ticker,
                            reason="histogram not negative",
                            histogram=round(current_histogram, 4)
                        )
                        continue
                    
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BEARISH,
                        confidence=self.confidence * 100,
                        reasoning=(
                            f"MACD bearish crossover: MACD line ({current_macd:.4f}) crossed below "
                            f"signal line ({current_signal:.4f}). Histogram: {current_histogram:.4f}"
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.MACD_BEARISH,
                        source="macd_generator",
                        tickers=[ticker_signal],
                        metadata=self._enrich_metadata({
                            "fast_period": self.fast_period,
                            "slow_period": self.slow_period,
                            "signal_period": self.signal_period,
                            "current_macd": round(current_macd, 4),
                            "current_signal": round(current_signal, 4),
                            "current_histogram": round(current_histogram, 4),
                            "previous_macd": round(previous_macd, 4),
                            "previous_signal": round(previous_signal, 4),
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        })
                    )
                    
                    signals.append(signal)
                    
                    logger.info(
                        "macd_bearish_signal_generated",
                        signal_id=str(signal.signal_id),
                        ticker=ticker,
                        macd=round(current_macd, 4),
                        signal_line=round(current_signal, 4)
                    )
            
            except Exception as e:
                logger.error(
                    "macd_check_failed",
                    ticker=ticker,
                    error=str(e),
                    exc_info=True
                )
                continue
        
        if signals:
            logger.info(
                "macd_scan_completed",
                signals_generated=len(signals),
                tickers_with_signal=[s.tickers[0].ticker for s in signals]
            )
        else:
            logger.info(
                "macd_scan_completed",
                signals_generated=0,
                message="No MACD crossovers detected"
            )
        
        return signals

