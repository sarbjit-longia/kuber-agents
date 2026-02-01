"""
EMA Crossover Signal Generator

Monitors for EMA crossovers (faster alternative to SMA crossovers).
"""
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class EMACrossoverSignalGenerator(BaseSignalGenerator):
    """
    EMA Crossover signal generator.
    
    Monitors for EMA crossovers (more responsive than SMA):
    - Fast EMA crosses above slow EMA: BULLISH
    - Fast EMA crosses below slow EMA: BEARISH
    
    Common periods: 9/21, 12/26, 20/50
    
    Configuration:
        - tickers: List of tickers to monitor
        - ema_fast: Fast EMA period (default: 12)
        - ema_slow: Slow EMA period (default: 26)
        - timeframe: Candle resolution (default: "D")
        - lookback_days: Days to check for crossover (default: 5)
        - confidence: Confidence level (default: 0.80)
    
    Example config:
        {
            "tickers": ["AAPL", "MSFT", "GOOGL"],
            "ema_fast": 12,
            "ema_slow": 26,
            "timeframe": "D",
            "lookback_days": 5,
            "confidence": 0.80
        }
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_data = MarketDataFetcher()
        self.ema_fast = self.config.get("ema_fast", 12)
        self.ema_slow = self.config.get("ema_slow", 26)
        self.timeframe = self.config.get("timeframe", "D")
        self.lookback_days = self.config.get("lookback_days", 5)
        self.confidence = self.config.get("confidence", 0.80)
    
    def _validate_config(self):
        """Validate EMA crossover configuration."""
        ema_fast = self.config.get("ema_fast", 12)
        ema_slow = self.config.get("ema_slow", 26)
        
        if ema_fast >= ema_slow:
            raise ValueError(f"ema_fast ({ema_fast}) must be < ema_slow ({ema_slow})")
    
    async def generate(self) -> List[Signal]:
        """Generate EMA crossover signals."""
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "ema_crossover_scan_started",
            tickers=tickers,
            ema_fast=self.ema_fast,
            ema_slow=self.ema_slow
        )
        
        for ticker in tickers:
            try:
                # Fetch both EMAs from Finnhub
                lookback_days = self.ema_slow + self.lookback_days + 50
                
                # Fetch fast EMA
                ema_fast_data = await self.market_data.fetch_indicator(
                    symbol=ticker,
                    indicator="ema",
                    resolution=self.timeframe,
                    lookback_days=lookback_days,
                    timeperiod=self.ema_fast,
                    seriestype="c"
                )
                
                # Fetch slow EMA
                ema_slow_data = await self.market_data.fetch_indicator(
                    symbol=ticker,
                    indicator="ema",
                    resolution=self.timeframe,
                    lookback_days=lookback_days,
                    timeperiod=self.ema_slow,
                    seriestype="c"
                )
                
                if not ema_fast_data or "ema" not in ema_fast_data:
                    logger.warning("fast_ema_data_unavailable", ticker=ticker)
                    continue
                
                if not ema_slow_data or "ema" not in ema_slow_data:
                    logger.warning("slow_ema_data_unavailable", ticker=ticker)
                    continue
                
                ema_fast_values = ema_fast_data["ema"]
                ema_slow_values = ema_slow_data["ema"]
                
                min_len = min(len(ema_fast_values), len(ema_slow_values))
                
                if min_len < self.lookback_days + 1:
                    logger.warning("insufficient_ema_data", ticker=ticker, available=min_len)
                    continue
                
                # Check for crossover in recent data
                bullish_crossover = False
                bearish_crossover = False
                
                for i in range(1, min(self.lookback_days + 1, min_len)):
                    idx = -i
                    prev_idx = -(i + 1)
                    
                    current_fast = ema_fast_values[idx]
                    current_slow = ema_slow_values[idx]
                    prev_fast = ema_fast_values[prev_idx]
                    prev_slow = ema_slow_values[prev_idx]
                    
                    # Bullish crossover: fast was below, now above
                    if prev_fast <= prev_slow and current_fast > current_slow:
                        bullish_crossover = True
                        break
                    
                    # Bearish crossover: fast was above, now below
                    elif prev_fast >= prev_slow and current_fast < current_slow:
                        bearish_crossover = True
                        break
                
                current_price = ema_fast_data.get("c", [None])[-1] if "c" in ema_fast_data else None
                current_fast_ema = ema_fast_values[-1]
                current_slow_ema = ema_slow_values[-1]
                
                if bullish_crossover:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BULLISH,
                        confidence=self.confidence * 100,
                        reasoning=(
                            f"EMA bullish crossover: {self.ema_fast}-EMA crossed above "
                            f"{self.ema_slow}-EMA ({current_fast_ema:.2f} > {current_slow_ema:.2f})"
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.EMA_BULLISH_CROSSOVER,
                        source="ema_crossover_generator",
                        tickers=[ticker_signal],
                        metadata=self._enrich_metadata({
                            "ema_fast": self.ema_fast,
                            "ema_slow": self.ema_slow,
                            "current_fast_ema": round(current_fast_ema, 2),
                            "current_slow_ema": round(current_slow_ema, 2),
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        })
                    )
                    
                    signals.append(signal)
                    logger.info("ema_bullish_crossover_signal", ticker=ticker)
                
                elif bearish_crossover:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BEARISH,
                        confidence=self.confidence * 100,
                        reasoning=(
                            f"EMA bearish crossover: {self.ema_fast}-EMA crossed below "
                            f"{self.ema_slow}-EMA ({current_fast_ema:.2f} < {current_slow_ema:.2f})"
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.EMA_BEARISH_CROSSOVER,
                        source="ema_crossover_generator",
                        tickers=[ticker_signal],
                        metadata=self._enrich_metadata({
                            "ema_fast": self.ema_fast,
                            "ema_slow": self.ema_slow,
                            "current_fast_ema": round(current_fast_ema, 2),
                            "current_slow_ema": round(current_slow_ema, 2),
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        })
                    )
                    
                    signals.append(signal)
                    logger.info("ema_bearish_crossover_signal", ticker=ticker)
            
            except Exception as e:
                logger.error("ema_crossover_check_failed", ticker=ticker, error=str(e), exc_info=True)
                continue
        
        logger.info("ema_crossover_scan_completed", signals_generated=len(signals))
        return signals

