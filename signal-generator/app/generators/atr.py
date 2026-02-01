"""
ATR Signal Generator

Monitors for volatility expansion/contraction using Average True Range.
"""
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class ATRSignalGenerator(BaseSignalGenerator):
    """
    ATR (Average True Range) signal generator.
    
    Monitors for volatility changes:
    - ATR spike (volatility expansion): Potential trend change/breakout
    - ATR compression: Consolidation, potential breakout coming
    
    Configuration:
        - tickers: List of tickers to monitor
        - timeperiod: ATR period (default: 14)
        - spike_multiplier: ATR spike threshold (default: 1.5x average)
        - compression_multiplier: ATR compression threshold (default: 0.7x average)
        - lookback_for_average: Days to calculate ATR average (default: 30)
        - timeframe: Candle resolution (default: "D")
        - confidence: Confidence level (default: 0.65)
    
    Example config:
        {
            "tickers": ["AAPL", "MSFT", "GOOGL"],
            "timeperiod": 14,
            "spike_multiplier": 1.5,
            "compression_multiplier": 0.7,
            "lookback_for_average": 30,
            "timeframe": "D",
            "confidence": 0.65
        }
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_data = MarketDataFetcher()
        self.timeperiod = self.config.get("timeperiod", 14)
        self.spike_multiplier = self.config.get("spike_multiplier", 1.5)
        self.compression_multiplier = self.config.get("compression_multiplier", 0.7)
        self.lookback_for_average = self.config.get("lookback_for_average", 30)
        self.timeframe = self.config.get("timeframe", "D")
        self.confidence = self.config.get("confidence", 0.65)
    
    def _validate_config(self):
        """Validate ATR generator configuration."""
        spike_multiplier = self.config.get("spike_multiplier", 1.5)
        compression_multiplier = self.config.get("compression_multiplier", 0.7)
        
        if spike_multiplier <= 1.0:
            raise ValueError("spike_multiplier must be > 1.0")
        if compression_multiplier >= 1.0:
            raise ValueError("compression_multiplier must be < 1.0")
    
    async def generate(self) -> List[Signal]:
        """Generate ATR volatility signals."""
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "atr_scan_started",
            tickers=tickers,
            timeperiod=self.timeperiod,
            spike_multiplier=self.spike_multiplier
        )
        
        for ticker in tickers:
            try:
                # Fetch ATR from Finnhub
                lookback_days = self.timeperiod + self.lookback_for_average + 50
                atr_data = await self.market_data.fetch_indicator(
                    symbol=ticker,
                    indicator="atr",
                    resolution=self.timeframe,
                    lookback_days=lookback_days,
                    timeperiod=self.timeperiod
                )
                
                if not atr_data or "atr" not in atr_data:
                    logger.warning("atr_data_unavailable", ticker=ticker)
                    continue
                
                atr_values = atr_data["atr"]
                
                if len(atr_values) < self.lookback_for_average + 2:
                    logger.warning("insufficient_atr_data", ticker=ticker)
                    continue
                
                current_atr = atr_values[-1]
                previous_atr = atr_values[-2]
                
                # Calculate average ATR over lookback period
                recent_atr_values = atr_values[-(self.lookback_for_average + 1):-1]
                average_atr = sum(recent_atr_values) / len(recent_atr_values)
                
                current_price = atr_data.get("c", [None])[-1] if "c" in atr_data else None
                
                # ATR spike (volatility expansion)
                if current_atr > average_atr * self.spike_multiplier and previous_atr <= average_atr * self.spike_multiplier:
                    atr_increase_pct = ((current_atr - average_atr) / average_atr) * 100
                    
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.NEUTRAL,  # ATR doesn't indicate direction
                        confidence=self.confidence * 100,
                        reasoning=(
                            f"ATR volatility spike: ATR ({current_atr:.2f}) spiked {atr_increase_pct:.1f}% "
                            f"above {self.lookback_for_average}-day average ({average_atr:.2f}). "
                            f"Potential breakout or trend change."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.ATR_VOLATILITY_SPIKE,
                        source="atr_generator",
                        tickers=[ticker_signal],
                        metadata=self._enrich_metadata({
                            "current_atr": round(current_atr, 2),
                            "average_atr": round(average_atr, 2),
                            "atr_increase_pct": round(atr_increase_pct, 1),
                            "spike_multiplier": self.spike_multiplier,
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        })
                    )
                    
                    signals.append(signal)
                    logger.info("atr_spike_signal", ticker=ticker, atr=round(current_atr, 2))
                
                # ATR compression (volatility contraction)
                elif current_atr < average_atr * self.compression_multiplier and previous_atr >= average_atr * self.compression_multiplier:
                    atr_decrease_pct = ((average_atr - current_atr) / average_atr) * 100
                    
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.NEUTRAL,
                        confidence=self.confidence * 100,
                        reasoning=(
                            f"ATR volatility compression: ATR ({current_atr:.2f}) compressed {atr_decrease_pct:.1f}% "
                            f"below {self.lookback_for_average}-day average ({average_atr:.2f}). "
                            f"Consolidation phase - breakout may be coming."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.ATR_VOLATILITY_COMPRESSION,
                        source="atr_generator",
                        tickers=[ticker_signal],
                        metadata=self._enrich_metadata({
                            "current_atr": round(current_atr, 2),
                            "average_atr": round(average_atr, 2),
                            "atr_decrease_pct": round(atr_decrease_pct, 1),
                            "compression_multiplier": self.compression_multiplier,
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        })
                    )
                    
                    signals.append(signal)
                    logger.info("atr_compression_signal", ticker=ticker, atr=round(current_atr, 2))
            
            except Exception as e:
                logger.error("atr_check_failed", ticker=ticker, error=str(e), exc_info=True)
                continue
        
        logger.info("atr_scan_completed", signals_generated=len(signals))
        return signals

