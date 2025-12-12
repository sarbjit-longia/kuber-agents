"""
SAR Signal Generator

Monitors Parabolic SAR for trend reversals and stop-loss levels.
"""
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class SARSignalGenerator(BaseSignalGenerator):
    """
    Parabolic SAR signal generator.
    
    Tracks trend direction and stop-loss levels:
    - Price crosses above SAR: Bullish trend starts
    - Price crosses below SAR: Bearish trend starts
    - SAR provides trailing stop levels
    
    Configuration:
        - tickers: List of tickers to monitor
        - acceleration: Acceleration factor (default: 0.02)
        - maximum: Maximum acceleration (default: 0.20)
        - timeframe: Candle resolution (default: "D")
        - confidence: Confidence level (default: 0.75)
    
    Example config:
        {
            "tickers": ["AAPL", "MSFT", "GOOGL"],
            "acceleration": 0.02,
            "maximum": 0.20,
            "timeframe": "D",
            "confidence": 0.75
        }
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_data = MarketDataFetcher()
        self.acceleration = self.config.get("acceleration", 0.02)
        self.maximum = self.config.get("maximum", 0.20)
        self.timeframe = self.config.get("timeframe", "D")
        self.confidence = self.config.get("confidence", 0.75)
    
    def _validate_config(self):
        """Validate SAR generator configuration."""
        acceleration = self.config.get("acceleration", 0.02)
        maximum = self.config.get("maximum", 0.20)
        
        if not 0 < acceleration < 1:
            raise ValueError("acceleration must be 0 < value < 1")
        if not 0 < maximum <= 1:
            raise ValueError("maximum must be 0 < value <= 1")
        if acceleration >= maximum:
            raise ValueError("acceleration must be < maximum")
    
    async def generate(self) -> List[Signal]:
        """Generate Parabolic SAR signals."""
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "sar_scan_started",
            tickers=tickers,
            acceleration=self.acceleration,
            maximum=self.maximum
        )
        
        for ticker in tickers:
            try:
                # Fetch SAR from Finnhub
                lookback_days = 90
                sar_data = await self.market_data.fetch_indicator(
                    symbol=ticker,
                    indicator="sar",
                    resolution=self.timeframe,
                    lookback_days=lookback_days,
                    acceleration=self.acceleration,
                    maximum=self.maximum
                )
                
                if not sar_data or "sar" not in sar_data:
                    logger.warning("sar_data_unavailable", ticker=ticker)
                    continue
                
                sar_values = sar_data["sar"]
                close_prices = sar_data.get("c", [])
                
                if len(sar_values) < 2 or len(close_prices) < 2:
                    logger.warning("insufficient_sar_data", ticker=ticker)
                    continue
                
                current_sar = sar_values[-1]
                previous_sar = sar_values[-2]
                current_price = close_prices[-1]
                previous_price = close_prices[-2]
                
                # Calculate distance to SAR (risk/stop level)
                sar_distance_pct = abs((current_price - current_sar) / current_price) * 100
                
                # Bullish reversal (price crosses above SAR)
                if current_price > current_sar and previous_price <= previous_sar:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BULLISH,
                        confidence=self.confidence * 100,
                        reasoning=(
                            f"Parabolic SAR bullish reversal: Price (${current_price:.2f}) crossed above "
                            f"SAR (${current_sar:.2f}). New uptrend starting."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.SAR_BULLISH_REVERSAL,
                        source="sar_generator",
                        tickers=[ticker_signal],
                        metadata={
                            "current_sar": round(current_sar, 2),
                            "current_price": round(current_price, 2),
                            "sar_distance_pct": round(sar_distance_pct, 2),
                            "acceleration": self.acceleration,
                            "maximum": self.maximum,
                            "timeframe": self.timeframe
                        }
                    )
                    
                    signals.append(signal)
                    logger.info("sar_bullish_reversal", ticker=ticker, price=round(current_price, 2))
                
                # Bearish reversal (price crosses below SAR)
                elif current_price < current_sar and previous_price >= previous_sar:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BEARISH,
                        confidence=self.confidence * 100,
                        reasoning=(
                            f"Parabolic SAR bearish reversal: Price (${current_price:.2f}) crossed below "
                            f"SAR (${current_sar:.2f}). New downtrend starting."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.SAR_BEARISH_REVERSAL,
                        source="sar_generator",
                        tickers=[ticker_signal],
                        metadata={
                            "current_sar": round(current_sar, 2),
                            "current_price": round(current_price, 2),
                            "sar_distance_pct": round(sar_distance_pct, 2),
                            "acceleration": self.acceleration,
                            "maximum": self.maximum,
                            "timeframe": self.timeframe
                        }
                    )
                    
                    signals.append(signal)
                    logger.info("sar_bearish_reversal", ticker=ticker, price=round(current_price, 2))
            
            except Exception as e:
                logger.error("sar_check_failed", ticker=ticker, error=str(e), exc_info=True)
                continue
        
        logger.info("sar_scan_completed", signals_generated=len(signals))
        return signals

