"""
Stochastic RSI Signal Generator

Monitors for Stochastic RSI extreme levels (more sensitive than regular RSI).
"""
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class StochRSISignalGenerator(BaseSignalGenerator):
    """
    Stochastic RSI signal generator.
    
    Applies Stochastic oscillator to RSI values for more sensitive signals:
    - FastK < oversold (default 20): BULLISH signal
    - FastK > overbought (default 80): BEARISH signal
    - FastK crosses above FastD: BULLISH
    - FastK crosses below FastD: BEARISH
    
    Configuration:
        - tickers: List of tickers to monitor
        - timeperiod: RSI period for calculation (default: 14)
        - fastk_period: Stochastic K period (default: 14)
        - fastd_period: Stochastic D period (default: 3)
        - overbought: Overbought level (default: 80)
        - oversold: Oversold level (default: 20)
        - timeframe: Candle resolution (default: "D")
        - confidence: Confidence level (default: 0.75)
    
    Example config:
        {
            "tickers": ["AAPL", "MSFT", "GOOGL"],
            "timeperiod": 14,
            "fastk_period": 14,
            "fastd_period": 3,
            "overbought": 80,
            "oversold": 20,
            "timeframe": "D",
            "confidence": 0.75
        }
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_data = MarketDataFetcher()
        self.timeperiod = self.config.get("timeperiod", 14)
        self.fastk_period = self.config.get("fastk_period", 14)
        self.fastd_period = self.config.get("fastd_period", 3)
        self.overbought = self.config.get("overbought", 80)
        self.oversold = self.config.get("oversold", 20)
        self.timeframe = self.config.get("timeframe", "D")
        self.confidence = self.config.get("confidence", 0.75)
    
    def _validate_config(self):
        """Validate StochRSI generator configuration."""
        overbought = self.config.get("overbought", 80)
        oversold = self.config.get("oversold", 20)
        
        if not 0 <= overbought <= 100:
            raise ValueError(f"overbought must be 0-100, got {overbought}")
        if not 0 <= oversold <= 100:
            raise ValueError(f"oversold must be 0-100, got {oversold}")
        if oversold >= overbought:
            raise ValueError("oversold must be < overbought")
    
    async def generate(self) -> List[Signal]:
        """Generate Stochastic RSI signals."""
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "stochrsi_scan_started",
            tickers=tickers,
            timeperiod=self.timeperiod,
            fastk_period=self.fastk_period
        )
        
        for ticker in tickers:
            try:
                # Fetch StochRSI from Finnhub
                lookback_days = 90
                stochrsi_data = await self.market_data.fetch_indicator(
                    symbol=ticker,
                    indicator="stochrsi",
                    resolution=self.timeframe,
                    lookback_days=lookback_days,
                    timeperiod=self.timeperiod,
                    fastk_period=self.fastk_period,
                    fastd_period=self.fastd_period
                )
                
                if not stochrsi_data or "fastk" not in stochrsi_data:
                    logger.warning("stochrsi_data_unavailable", ticker=ticker)
                    continue
                
                fastk_values = stochrsi_data["fastk"]
                fastd_values = stochrsi_data.get("fastd", [])
                
                if len(fastk_values) < 2:
                    logger.warning("insufficient_stochrsi_data", ticker=ticker)
                    continue
                
                current_k = fastk_values[-1]
                previous_k = fastk_values[-2]
                current_d = fastd_values[-1] if fastd_values and len(fastd_values) >= 1 else None
                previous_d = fastd_values[-2] if fastd_values and len(fastd_values) >= 2 else None
                
                current_price = stochrsi_data.get("c", [None])[-1] if "c" in stochrsi_data else None
                
                # Oversold condition (bullish)
                if current_k < self.oversold and previous_k >= self.oversold:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BULLISH,
                        confidence=self.confidence * 100,
                        reasoning=(
                            f"StochRSI oversold: FastK ({current_k:.1f}) crossed below {self.oversold}. "
                            f"Potential reversal up."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.STOCHRSI_OVERSOLD,
                        source="stochrsi_generator",
                        tickers=[ticker_signal],
                        metadata={
                            "current_k": round(current_k, 2),
                            "previous_k": round(previous_k, 2),
                            "current_d": round(current_d, 2) if current_d else None,
                            "oversold_threshold": self.oversold,
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        }
                    )
                    
                    signals.append(signal)
                    logger.info("stochrsi_oversold_signal", ticker=ticker, k=round(current_k, 1))
                
                # Overbought condition (bearish)
                elif current_k > self.overbought and previous_k <= self.overbought:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BEARISH,
                        confidence=self.confidence * 100,
                        reasoning=(
                            f"StochRSI overbought: FastK ({current_k:.1f}) crossed above {self.overbought}. "
                            f"Potential reversal down."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.STOCHRSI_OVERBOUGHT,
                        source="stochrsi_generator",
                        tickers=[ticker_signal],
                        metadata={
                            "current_k": round(current_k, 2),
                            "previous_k": round(previous_k, 2),
                            "current_d": round(current_d, 2) if current_d else None,
                            "overbought_threshold": self.overbought,
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        }
                    )
                    
                    signals.append(signal)
                    logger.info("stochrsi_overbought_signal", ticker=ticker, k=round(current_k, 1))
                
                # Bullish crossover (K crosses above D)
                elif current_d and previous_d and current_k > current_d and previous_k <= previous_d:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BULLISH,
                        confidence=self.confidence * 0.9 * 100,
                        reasoning=(
                            f"StochRSI bullish crossover: FastK ({current_k:.1f}) crossed above "
                            f"FastD ({current_d:.1f})"
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.STOCHRSI_BULLISH_CROSS,
                        source="stochrsi_generator",
                        tickers=[ticker_signal],
                        metadata={
                            "current_k": round(current_k, 2),
                            "current_d": round(current_d, 2),
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        }
                    )
                    
                    signals.append(signal)
                    logger.info("stochrsi_bullish_cross", ticker=ticker)
                
                # Bearish crossover (K crosses below D)
                elif current_d and previous_d and current_k < current_d and previous_k >= previous_d:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BEARISH,
                        confidence=self.confidence * 0.9 * 100,
                        reasoning=(
                            f"StochRSI bearish crossover: FastK ({current_k:.1f}) crossed below "
                            f"FastD ({current_d:.1f})"
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.STOCHRSI_BEARISH_CROSS,
                        source="stochrsi_generator",
                        tickers=[ticker_signal],
                        metadata={
                            "current_k": round(current_k, 2),
                            "current_d": round(current_d, 2),
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        }
                    )
                    
                    signals.append(signal)
                    logger.info("stochrsi_bearish_cross", ticker=ticker)
            
            except Exception as e:
                logger.error("stochrsi_check_failed", ticker=ticker, error=str(e), exc_info=True)
                continue
        
        logger.info("stochrsi_scan_completed", signals_generated=len(signals))
        return signals

