"""
RSI Signal Generator

Monitors for RSI oversold and overbought conditions.
"""
from typing import Dict, Any, List
import structlog
import pandas as pd

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class RSISignalGenerator(BaseSignalGenerator):
    """
    RSI (Relative Strength Index) signal generator.
    
    Monitors a watchlist of tickers for RSI extreme conditions:
    - RSI < oversold_threshold (default 30): Generates BULLISH signal
    - RSI > overbought_threshold (default 70): Generates BEARISH signal
    
    Configuration:
        - tickers: List of tickers to monitor
        - period: RSI calculation period (default: 14)
        - oversold_threshold: RSI level for oversold (default: 30)
        - overbought_threshold: RSI level for overbought (default: 70)
        - timeframe: Candle resolution (default: "D" for daily)
        - confidence: Confidence level for generated signals (default: 0.75)
    
    Example config:
        {
            "tickers": ["AAPL", "MSFT", "GOOGL"],
            "period": 14,
            "oversold_threshold": 30,
            "overbought_threshold": 70,
            "timeframe": "D",
            "confidence": 0.75
        }
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_data = MarketDataFetcher()
        self.period = self.config.get("period", 14)
        self.oversold_threshold = self.config.get("oversold_threshold", 30)
        self.overbought_threshold = self.config.get("overbought_threshold", 70)
        self.timeframe = self.config.get("timeframe", "D")
        self.confidence = self.config.get("confidence", 0.75)
    
    def _validate_config(self):
        """Validate RSI generator configuration."""
        period = self.config.get("period", 14)
        if period < 2:
            raise ValueError(f"RSI period must be >= 2, got {period}")
        
        oversold = self.config.get("oversold_threshold", 30)
        overbought = self.config.get("overbought_threshold", 70)
        
        if not 0 <= oversold < overbought <= 100:
            raise ValueError(
                f"Invalid thresholds: oversold={oversold}, overbought={overbought}. "
                f"Must be: 0 <= oversold < overbought <= 100"
            )
        
        confidence = self.config.get("confidence", 0.75)
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
    
    async def generate(self) -> List[Signal]:
        """
        Check for RSI extreme conditions and generate signals.
        
        Returns:
            List of Signal objects for tickers with RSI extremes
        """
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "rsi_scan_started",
            tickers=tickers,
            period=self.period,
            oversold=self.oversold_threshold,
            overbought=self.overbought_threshold
        )
        
        for ticker in tickers:
            try:
                # Fetch RSI from Finnhub (pre-calculated)
                lookback_days = 90  # Enough for RSI analysis
                rsi_data = await self.market_data.fetch_indicator(
                    symbol=ticker,
                    indicator="rsi",
                    resolution=self.timeframe,
                    lookback_days=lookback_days,
                    timeperiod=self.period,
                    seriestype="c"  # close price
                )
                
                if not rsi_data or "rsi" not in rsi_data:
                    logger.warning(
                        "rsi_data_unavailable",
                        ticker=ticker
                    )
                    continue
                
                rsi_values = rsi_data["rsi"]
                
                # Need at least 2 values to detect crossover
                if len(rsi_values) < 2:
                    logger.warning(
                        "insufficient_rsi_data",
                        ticker=ticker,
                        available=len(rsi_values)
                    )
                    continue
                
                current_rsi = rsi_values[-1]
                previous_rsi = rsi_values[-2]
                
                # Get current price from candle data
                current_price = rsi_data.get("c", [None])[-1] if "c" in rsi_data else None
                
                # Check for oversold condition (bullish signal)
                if current_rsi < self.oversold_threshold and previous_rsi >= self.oversold_threshold:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BULLISH,
                        confidence=self.confidence * 100,
                        reasoning=(
                            f"RSI oversold: RSI={current_rsi:.1f} crossed below {self.oversold_threshold} "
                            f"(was {previous_rsi:.1f} previously)"
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.RSI_OVERSOLD,
                        source="rsi_generator",
                        tickers=[ticker_signal],
                        metadata=self._enrich_metadata({
                            "rsi_period": self.period,
                            "current_rsi": round(current_rsi, 2),
                            "previous_rsi": round(previous_rsi, 2),
                            "oversold_threshold": self.oversold_threshold,
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        })
                    )
                    
                    signals.append(signal)
                    
                    logger.info(
                        "rsi_oversold_signal_generated",
                        signal_id=str(signal.signal_id),
                        ticker=ticker,
                        rsi=round(current_rsi, 2)
                    )
                
                # Check for overbought condition (bearish signal)
                elif current_rsi > self.overbought_threshold and previous_rsi <= self.overbought_threshold:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BEARISH,
                        confidence=self.confidence * 100,
                        reasoning=(
                            f"RSI overbought: RSI={current_rsi:.1f} crossed above {self.overbought_threshold} "
                            f"(was {previous_rsi:.1f} previously)"
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.RSI_OVERBOUGHT,
                        source="rsi_generator",
                        tickers=[ticker_signal],
                        metadata=self._enrich_metadata({
                            "rsi_period": self.period,
                            "current_rsi": round(current_rsi, 2),
                            "previous_rsi": round(previous_rsi, 2),
                            "overbought_threshold": self.overbought_threshold,
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        })
                    )
                    
                    signals.append(signal)
                    
                    logger.info(
                        "rsi_overbought_signal_generated",
                        signal_id=str(signal.signal_id),
                        ticker=ticker,
                        rsi=round(current_rsi, 2)
                    )
            
            except Exception as e:
                logger.error(
                    "rsi_check_failed",
                    ticker=ticker,
                    error=str(e),
                    exc_info=True
                )
                continue
        
        if signals:
            logger.info(
                "rsi_scan_completed",
                signals_generated=len(signals),
                tickers_with_signal=[s.tickers[0].ticker for s in signals]
            )
        else:
            logger.info(
                "rsi_scan_completed",
                signals_generated=0,
                message="No RSI extremes detected"
            )
        
        return signals

