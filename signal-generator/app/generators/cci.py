"""
CCI Signal Generator

Monitors for CCI (Commodity Channel Index) overbought/oversold conditions.
"""
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class CCISignalGenerator(BaseSignalGenerator):
    """
    CCI (Commodity Channel Index) signal generator.
    
    Monitors for overbought/oversold conditions:
    - CCI > +100: Overbought (potential reversal down)
    - CCI < -100: Oversold (potential reversal up)
    - CCI crossing zero line: Trend change
    
    Configuration:
        - tickers: List of tickers to monitor
        - timeperiod: CCI period (default: 20)
        - overbought: Overbought threshold (default: +100)
        - oversold: Oversold threshold (default: -100)
        - timeframe: Candle resolution (default: "D")
        - confidence: Confidence level (default: 0.70)
    
    Example config:
        {
            "tickers": ["AAPL", "MSFT", "GOOGL"],
            "timeperiod": 20,
            "overbought": 100,
            "oversold": -100,
            "timeframe": "D",
            "confidence": 0.70
        }
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_data = MarketDataFetcher()
        self.timeperiod = self.config.get("timeperiod", 20)
        self.overbought = self.config.get("overbought", 100)
        self.oversold = self.config.get("oversold", -100)
        self.timeframe = self.config.get("timeframe", "D")
        self.confidence = self.config.get("confidence", 0.70)
    
    def _validate_config(self):
        """Validate CCI generator configuration."""
        oversold = self.config.get("oversold", -100)
        overbought = self.config.get("overbought", 100)
        
        if oversold >= overbought:
            raise ValueError("oversold must be < overbought")
        if overbought <= 0:
            raise ValueError("overbought must be > 0")
        if oversold >= 0:
            raise ValueError("oversold must be < 0")
    
    async def generate(self) -> List[Signal]:
        """Generate CCI overbought/oversold signals."""
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "cci_scan_started",
            tickers=tickers,
            timeperiod=self.timeperiod,
            overbought=self.overbought,
            oversold=self.oversold
        )
        
        for ticker in tickers:
            try:
                # Fetch CCI from Finnhub
                lookback_days = 90
                cci_data = await self.market_data.fetch_indicator(
                    symbol=ticker,
                    indicator="cci",
                    resolution=self.timeframe,
                    lookback_days=lookback_days,
                    timeperiod=self.timeperiod
                )
                
                if not cci_data or "cci" not in cci_data:
                    logger.warning("cci_data_unavailable", ticker=ticker)
                    continue
                
                cci_values = cci_data["cci"]
                
                if len(cci_values) < 2:
                    logger.warning("insufficient_cci_data", ticker=ticker)
                    continue
                
                current_cci = cci_values[-1]
                previous_cci = cci_values[-2]
                
                current_price = cci_data.get("c", [None])[-1] if "c" in cci_data else None
                
                # CCI entering oversold zone (bullish reversal potential)
                if current_cci < self.oversold and previous_cci >= self.oversold:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BULLISH,
                        confidence=self.confidence * 100,
                        reasoning=(
                            f"CCI oversold: CCI ({current_cci:.1f}) crossed below {self.oversold}. "
                            f"Potential bullish reversal."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.CCI_OVERSOLD,
                        source="cci_generator",
                        tickers=[ticker_signal],
                        metadata={
                            "timeperiod": self.timeperiod,
                            "current_cci": round(current_cci, 2),
                            "previous_cci": round(previous_cci, 2),
                            "oversold_threshold": self.oversold,
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        }
                    )
                    
                    signals.append(signal)
                    logger.info("cci_oversold_signal", ticker=ticker, cci=round(current_cci, 1))
                
                # CCI entering overbought zone (bearish reversal potential)
                elif current_cci > self.overbought and previous_cci <= self.overbought:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BEARISH,
                        confidence=self.confidence * 100,
                        reasoning=(
                            f"CCI overbought: CCI ({current_cci:.1f}) crossed above {self.overbought}. "
                            f"Potential bearish reversal."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.CCI_OVERBOUGHT,
                        source="cci_generator",
                        tickers=[ticker_signal],
                        metadata={
                            "timeperiod": self.timeperiod,
                            "current_cci": round(current_cci, 2),
                            "previous_cci": round(previous_cci, 2),
                            "overbought_threshold": self.overbought,
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        }
                    )
                    
                    signals.append(signal)
                    logger.info("cci_overbought_signal", ticker=ticker, cci=round(current_cci, 1))
                
                # CCI crossing zero line upward (bullish momentum)
                elif current_cci > 0 and previous_cci <= 0:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BULLISH,
                        confidence=self.confidence * 0.9 * 100,  # Slightly lower confidence
                        reasoning=(
                            f"CCI bullish zero cross: CCI ({current_cci:.1f}) crossed above zero. "
                            f"Uptrend momentum."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.CCI_BULLISH_ZERO_CROSS,
                        source="cci_generator",
                        tickers=[ticker_signal],
                        metadata={
                            "timeperiod": self.timeperiod,
                            "current_cci": round(current_cci, 2),
                            "previous_cci": round(previous_cci, 2),
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        }
                    )
                    
                    signals.append(signal)
                    logger.info("cci_bullish_zero_cross", ticker=ticker, cci=round(current_cci, 1))
                
                # CCI crossing zero line downward (bearish momentum)
                elif current_cci < 0 and previous_cci >= 0:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BEARISH,
                        confidence=self.confidence * 0.9 * 100,  # Slightly lower confidence
                        reasoning=(
                            f"CCI bearish zero cross: CCI ({current_cci:.1f}) crossed below zero. "
                            f"Downtrend momentum."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.CCI_BEARISH_ZERO_CROSS,
                        source="cci_generator",
                        tickers=[ticker_signal],
                        metadata={
                            "timeperiod": self.timeperiod,
                            "current_cci": round(current_cci, 2),
                            "previous_cci": round(previous_cci, 2),
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        }
                    )
                    
                    signals.append(signal)
                    logger.info("cci_bearish_zero_cross", ticker=ticker, cci=round(current_cci, 1))
            
            except Exception as e:
                logger.error("cci_check_failed", ticker=ticker, error=str(e), exc_info=True)
                continue
        
        logger.info("cci_scan_completed", signals_generated=len(signals))
        return signals

