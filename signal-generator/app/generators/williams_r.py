"""
Williams %R Signal Generator

Monitors for Williams %R overbought/oversold conditions.
"""
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class WilliamsRSignalGenerator(BaseSignalGenerator):
    """
    Williams %R signal generator.
    
    Momentum indicator similar to Stochastic but with inverted scale (-100 to 0):
    - WillR > -20: Overbought (potential reversal down)
    - WillR < -80: Oversold (potential reversal up)
    - WillR crosses -50: Momentum shift
    
    Configuration:
        - tickers: List of tickers to monitor
        - timeperiod: Lookback period (default: 14)
        - overbought: Overbought level (default: -20)
        - oversold: Oversold level (default: -80)
        - timeframe: Candle resolution (default: "D")
        - confidence: Confidence level (default: 0.70)
    
    Example config:
        {
            "tickers": ["AAPL", "MSFT", "GOOGL"],
            "timeperiod": 14,
            "overbought": -20,
            "oversold": -80,
            "timeframe": "D",
            "confidence": 0.70
        }
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_data = MarketDataFetcher()
        self.timeperiod = self.config.get("timeperiod", 14)
        self.overbought = self.config.get("overbought", -20)
        self.oversold = self.config.get("oversold", -80)
        self.timeframe = self.config.get("timeframe", "D")
        self.confidence = self.config.get("confidence", 0.70)
    
    def _validate_config(self):
        """Validate Williams %R generator configuration."""
        overbought = self.config.get("overbought", -20)
        oversold = self.config.get("oversold", -80)
        
        if not -100 <= overbought <= 0:
            raise ValueError(f"overbought must be -100 to 0, got {overbought}")
        if not -100 <= oversold <= 0:
            raise ValueError(f"oversold must be -100 to 0, got {oversold}")
        if oversold >= overbought:
            raise ValueError("oversold must be < overbought")
    
    async def generate(self) -> List[Signal]:
        """Generate Williams %R signals."""
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "willr_scan_started",
            tickers=tickers,
            timeperiod=self.timeperiod,
            overbought=self.overbought,
            oversold=self.oversold
        )
        
        for ticker in tickers:
            try:
                # Fetch Williams %R from Finnhub
                lookback_days = 90
                willr_data = await self.market_data.fetch_indicator(
                    symbol=ticker,
                    indicator="willr",
                    resolution=self.timeframe,
                    lookback_days=lookback_days,
                    timeperiod=self.timeperiod
                )
                
                if not willr_data or "willr" not in willr_data:
                    logger.warning("willr_data_unavailable", ticker=ticker)
                    continue
                
                willr_values = willr_data["willr"]
                
                if len(willr_values) < 2:
                    logger.warning("insufficient_willr_data", ticker=ticker)
                    continue
                
                current_willr = willr_values[-1]
                previous_willr = willr_values[-2]
                
                current_price = willr_data.get("c", [None])[-1] if "c" in willr_data else None
                
                # Oversold condition (bullish)
                if current_willr < self.oversold and previous_willr >= self.oversold:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BULLISH,
                        confidence=self.confidence * 100,
                        reasoning=(
                            f"Williams %R oversold: WillR ({current_willr:.1f}) crossed below {self.oversold}. "
                            f"Potential reversal up."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.WILLR_OVERSOLD,
                        source="willr_generator",
                        tickers=[ticker_signal],
                        metadata={
                            "current_willr": round(current_willr, 2),
                            "previous_willr": round(previous_willr, 2),
                            "oversold_threshold": self.oversold,
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        }
                    )
                    
                    signals.append(signal)
                    logger.info("willr_oversold_signal", ticker=ticker, willr=round(current_willr, 1))
                
                # Overbought condition (bearish)
                elif current_willr > self.overbought and previous_willr <= self.overbought:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BEARISH,
                        confidence=self.confidence * 100,
                        reasoning=(
                            f"Williams %R overbought: WillR ({current_willr:.1f}) crossed above {self.overbought}. "
                            f"Potential reversal down."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.WILLR_OVERBOUGHT,
                        source="willr_generator",
                        tickers=[ticker_signal],
                        metadata={
                            "current_willr": round(current_willr, 2),
                            "previous_willr": round(previous_willr, 2),
                            "overbought_threshold": self.overbought,
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        }
                    )
                    
                    signals.append(signal)
                    logger.info("willr_overbought_signal", ticker=ticker, willr=round(current_willr, 1))
                
                # Crossing -50 midline upward (bullish momentum)
                elif current_willr > -50 and previous_willr <= -50:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BULLISH,
                        confidence=self.confidence * 0.85 * 100,
                        reasoning=(
                            f"Williams %R bullish momentum: WillR ({current_willr:.1f}) crossed above -50 midline"
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.WILLR_BULLISH_MOMENTUM,
                        source="willr_generator",
                        tickers=[ticker_signal],
                        metadata={
                            "current_willr": round(current_willr, 2),
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        }
                    )
                    
                    signals.append(signal)
                    logger.info("willr_bullish_momentum", ticker=ticker)
                
                # Crossing -50 midline downward (bearish momentum)
                elif current_willr < -50 and previous_willr >= -50:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BEARISH,
                        confidence=self.confidence * 0.85 * 100,
                        reasoning=(
                            f"Williams %R bearish momentum: WillR ({current_willr:.1f}) crossed below -50 midline"
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.WILLR_BEARISH_MOMENTUM,
                        source="willr_generator",
                        tickers=[ticker_signal],
                        metadata={
                            "current_willr": round(current_willr, 2),
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        }
                    )
                    
                    signals.append(signal)
                    logger.info("willr_bearish_momentum", ticker=ticker)
            
            except Exception as e:
                logger.error("willr_check_failed", ticker=ticker, error=str(e), exc_info=True)
                continue
        
        logger.info("willr_scan_completed", signals_generated=len(signals))
        return signals

