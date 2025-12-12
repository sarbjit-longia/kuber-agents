"""
AROON Signal Generator

Monitors for trend changes and strength using AROON indicator.
"""
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class AroonSignalGenerator(BaseSignalGenerator):
    """
    AROON signal generator.
    
    Measures time since highest high (Aroon Up) and lowest low (Aroon Down):
    - Aroon Up > 70 & Aroon Down < 30: Strong uptrend
    - Aroon Down > 70 & Aroon Up < 30: Strong downtrend
    - Aroon Up crosses above Aroon Down: Bullish trend change
    - Both < 50: Consolidation/no trend
    
    Configuration:
        - tickers: List of tickers to monitor
        - timeperiod: Lookback period (default: 25)
        - trend_threshold: Strong trend level (default: 70)
        - timeframe: Candle resolution (default: "D")
        - confidence: Confidence level (default: 0.75)
    
    Example config:
        {
            "tickers": ["AAPL", "MSFT", "GOOGL"],
            "timeperiod": 25,
            "trend_threshold": 70,
            "timeframe": "D",
            "confidence": 0.75
        }
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_data = MarketDataFetcher()
        self.timeperiod = self.config.get("timeperiod", 25)
        self.trend_threshold = self.config.get("trend_threshold", 70)
        self.timeframe = self.config.get("timeframe", "D")
        self.confidence = self.config.get("confidence", 0.75)
    
    def _validate_config(self):
        """Validate AROON generator configuration."""
        trend_threshold = self.config.get("trend_threshold", 70)
        if not 0 < trend_threshold <= 100:
            raise ValueError("trend_threshold must be 0-100")
    
    async def generate(self) -> List[Signal]:
        """Generate AROON signals."""
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "aroon_scan_started",
            tickers=tickers,
            timeperiod=self.timeperiod,
            trend_threshold=self.trend_threshold
        )
        
        for ticker in tickers:
            try:
                # Fetch AROON from Finnhub
                lookback_days = 90
                aroon_data = await self.market_data.fetch_indicator(
                    symbol=ticker,
                    indicator="aroon",
                    resolution=self.timeframe,
                    lookback_days=lookback_days,
                    timeperiod=self.timeperiod
                )
                
                if not aroon_data or "aroonup" not in aroon_data or "aroondown" not in aroon_data:
                    logger.warning("aroon_data_unavailable", ticker=ticker)
                    continue
                
                aroon_up = aroon_data["aroonup"]
                aroon_down = aroon_data["aroondown"]
                
                if len(aroon_up) < 2 or len(aroon_down) < 2:
                    logger.warning("insufficient_aroon_data", ticker=ticker)
                    continue
                
                current_up = aroon_up[-1]
                current_down = aroon_down[-1]
                previous_up = aroon_up[-2]
                previous_down = aroon_down[-2]
                
                current_price = aroon_data.get("c", [None])[-1] if "c" in aroon_data else None
                
                # Strong uptrend
                if current_up > self.trend_threshold and current_down < (100 - self.trend_threshold):
                    if not (previous_up > self.trend_threshold and previous_down < (100 - self.trend_threshold)):
                        ticker_signal = TickerSignal(
                            ticker=ticker,
                            signal=BiasType.BULLISH,
                            confidence=self.confidence * 100,
                            reasoning=(
                                f"AROON strong uptrend: Aroon Up ({current_up:.0f}) > {self.trend_threshold}, "
                                f"Aroon Down ({current_down:.0f}) < {100 - self.trend_threshold}"
                            )
                        )
                        
                        signal = Signal(
                            signal_type=SignalType.AROON_UPTREND,
                            source="aroon_generator",
                            tickers=[ticker_signal],
                            metadata={
                                "aroon_up": round(current_up, 2),
                                "aroon_down": round(current_down, 2),
                                "timeframe": self.timeframe,
                                "current_price": round(current_price, 2) if current_price else None
                            }
                        )
                        
                        signals.append(signal)
                        logger.info("aroon_uptrend_signal", ticker=ticker)
                
                # Strong downtrend
                elif current_down > self.trend_threshold and current_up < (100 - self.trend_threshold):
                    if not (previous_down > self.trend_threshold and previous_up < (100 - self.trend_threshold)):
                        ticker_signal = TickerSignal(
                            ticker=ticker,
                            signal=BiasType.BEARISH,
                            confidence=self.confidence * 100,
                            reasoning=(
                                f"AROON strong downtrend: Aroon Down ({current_down:.0f}) > {self.trend_threshold}, "
                                f"Aroon Up ({current_up:.0f}) < {100 - self.trend_threshold}"
                            )
                        )
                        
                        signal = Signal(
                            signal_type=SignalType.AROON_DOWNTREND,
                            source="aroon_generator",
                            tickers=[ticker_signal],
                            metadata={
                                "aroon_up": round(current_up, 2),
                                "aroon_down": round(current_down, 2),
                                "timeframe": self.timeframe,
                                "current_price": round(current_price, 2) if current_price else None
                            }
                        )
                        
                        signals.append(signal)
                        logger.info("aroon_downtrend_signal", ticker=ticker)
                
                # Bullish crossover (Up crosses above Down)
                elif current_up > current_down and previous_up <= previous_down:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BULLISH,
                        confidence=self.confidence * 0.9 * 100,
                        reasoning=(
                            f"AROON bullish crossover: Aroon Up ({current_up:.0f}) crossed above "
                            f"Aroon Down ({current_down:.0f})"
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.AROON_BULLISH_CROSS,
                        source="aroon_generator",
                        tickers=[ticker_signal],
                        metadata={
                            "aroon_up": round(current_up, 2),
                            "aroon_down": round(current_down, 2),
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        }
                    )
                    
                    signals.append(signal)
                    logger.info("aroon_bullish_cross", ticker=ticker)
                
                # Bearish crossover (Down crosses above Up)
                elif current_down > current_up and previous_down <= previous_up:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BEARISH,
                        confidence=self.confidence * 0.9 * 100,
                        reasoning=(
                            f"AROON bearish crossover: Aroon Down ({current_down:.0f}) crossed above "
                            f"Aroon Up ({current_up:.0f})"
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.AROON_BEARISH_CROSS,
                        source="aroon_generator",
                        tickers=[ticker_signal],
                        metadata={
                            "aroon_up": round(current_up, 2),
                            "aroon_down": round(current_down, 2),
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        }
                    )
                    
                    signals.append(signal)
                    logger.info("aroon_bearish_cross", ticker=ticker)
                
                # Consolidation (both low)
                elif current_up < 50 and current_down < 50:
                    if not (previous_up < 50 and previous_down < 50):
                        ticker_signal = TickerSignal(
                            ticker=ticker,
                            signal=BiasType.NEUTRAL,
                            confidence=self.confidence * 0.8 * 100,
                            reasoning=(
                                f"AROON consolidation: Both Aroon Up ({current_up:.0f}) and "
                                f"Aroon Down ({current_down:.0f}) < 50. Choppy market."
                            )
                        )
                        
                        signal = Signal(
                            signal_type=SignalType.AROON_CONSOLIDATION,
                            source="aroon_generator",
                            tickers=[ticker_signal],
                            metadata={
                                "aroon_up": round(current_up, 2),
                                "aroon_down": round(current_down, 2),
                                "timeframe": self.timeframe,
                                "current_price": round(current_price, 2) if current_price else None
                            }
                        )
                        
                        signals.append(signal)
                        logger.info("aroon_consolidation", ticker=ticker)
            
            except Exception as e:
                logger.error("aroon_check_failed", ticker=ticker, error=str(e), exc_info=True)
                continue
        
        logger.info("aroon_scan_completed", signals_generated=len(signals))
        return signals

