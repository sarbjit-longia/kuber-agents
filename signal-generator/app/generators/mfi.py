"""
MFI Signal Generator

Monitors Money Flow Index (volume-weighted RSI).
"""
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class MFISignalGenerator(BaseSignalGenerator):
    """
    MFI (Money Flow Index) signal generator.
    
    Volume-weighted version of RSI - shows money flowing in/out:
    - MFI > 80: Overbought (money flowing in, potential reversal)
    - MFI < 20: Oversold (money flowing out, potential reversal)
    - MFI divergence from price: Strong reversal signal
    
    Configuration:
        - tickers: List of tickers to monitor
        - timeperiod: MFI period (default: 14)
        - overbought: Overbought level (default: 80)
        - oversold: Oversold level (default: 20)
        - timeframe: Candle resolution (default: "D")
        - confidence: Confidence level (default: 0.75)
    
    Example config:
        {
            "tickers": ["AAPL", "MSFT", "GOOGL"],
            "timeperiod": 14,
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
        self.overbought = self.config.get("overbought", 80)
        self.oversold = self.config.get("oversold", 20)
        self.timeframe = self.config.get("timeframe", "D")
        self.confidence = self.config.get("confidence", 0.75)
    
    def _validate_config(self):
        """Validate MFI generator configuration."""
        overbought = self.config.get("overbought", 80)
        oversold = self.config.get("oversold", 20)
        
        if not 0 <= overbought <= 100:
            raise ValueError(f"overbought must be 0-100, got {overbought}")
        if not 0 <= oversold <= 100:
            raise ValueError(f"oversold must be 0-100, got {oversold}")
        if oversold >= overbought:
            raise ValueError("oversold must be < overbought")
    
    async def generate(self) -> List[Signal]:
        """Generate MFI signals."""
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "mfi_scan_started",
            tickers=tickers,
            timeperiod=self.timeperiod,
            overbought=self.overbought,
            oversold=self.oversold
        )
        
        for ticker in tickers:
            try:
                # Fetch MFI from Finnhub
                lookback_days = 90
                mfi_data = await self.market_data.fetch_indicator(
                    symbol=ticker,
                    indicator="mfi",
                    resolution=self.timeframe,
                    lookback_days=lookback_days,
                    timeperiod=self.timeperiod
                )
                
                if not mfi_data or "mfi" not in mfi_data:
                    logger.warning("mfi_data_unavailable", ticker=ticker)
                    continue
                
                mfi_values = mfi_data["mfi"]
                
                if len(mfi_values) < 2:
                    logger.warning("insufficient_mfi_data", ticker=ticker)
                    continue
                
                current_mfi = mfi_values[-1]
                previous_mfi = mfi_values[-2]
                
                current_price = mfi_data.get("c", [None])[-1] if "c" in mfi_data else None
                
                # Oversold condition (bullish - money flowing out, potential reversal)
                if current_mfi < self.oversold and previous_mfi >= self.oversold:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BULLISH,
                        confidence=self.confidence * 100,
                        reasoning=(
                            f"MFI oversold: MFI ({current_mfi:.1f}) crossed below {self.oversold}. "
                            f"Heavy selling, potential reversal up."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.MFI_OVERSOLD,
                        source="mfi_generator",
                        tickers=[ticker_signal],
                        metadata={
                            "current_mfi": round(current_mfi, 2),
                            "previous_mfi": round(previous_mfi, 2),
                            "oversold_threshold": self.oversold,
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        }
                    )
                    
                    signals.append(signal)
                    logger.info("mfi_oversold_signal", ticker=ticker, mfi=round(current_mfi, 1))
                
                # Overbought condition (bearish - money flowing in, potential reversal)
                elif current_mfi > self.overbought and previous_mfi <= self.overbought:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BEARISH,
                        confidence=self.confidence * 100,
                        reasoning=(
                            f"MFI overbought: MFI ({current_mfi:.1f}) crossed above {self.overbought}. "
                            f"Heavy buying, potential reversal down."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.MFI_OVERBOUGHT,
                        source="mfi_generator",
                        tickers=[ticker_signal],
                        metadata={
                            "current_mfi": round(current_mfi, 2),
                            "previous_mfi": round(previous_mfi, 2),
                            "overbought_threshold": self.overbought,
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        }
                    )
                    
                    signals.append(signal)
                    logger.info("mfi_overbought_signal", ticker=ticker, mfi=round(current_mfi, 1))
            
            except Exception as e:
                logger.error("mfi_check_failed", ticker=ticker, error=str(e), exc_info=True)
                continue
        
        logger.info("mfi_scan_completed", signals_generated=len(signals))
        return signals

