"""
OBV Signal Generator

Monitors On Balance Volume for accumulation/distribution signals.
"""
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class OBVSignalGenerator(BaseSignalGenerator):
    """
    OBV (On Balance Volume) signal generator.
    
    Leading indicator that uses volume to predict price movements:
    - OBV rising + price flat/down: Bullish divergence (accumulation)
    - OBV falling + price flat/up: Bearish divergence (distribution)
    - OBV breakout: Volume confirmation of price move
    
    Configuration:
        - tickers: List of tickers to monitor
        - sma_period: SMA period for OBV smoothing (default: 20)
        - divergence_lookback: Days to check for divergence (default: 10)
        - min_price_change: Min price change % for divergence (default: 2%)
        - timeframe: Candle resolution (default: "D")
        - confidence: Confidence level (default: 0.70)
    
    Example config:
        {
            "tickers": ["AAPL", "MSFT", "GOOGL"],
            "sma_period": 20,
            "divergence_lookback": 10,
            "min_price_change": 2.0,
            "timeframe": "D",
            "confidence": 0.70
        }
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_data = MarketDataFetcher()
        self.sma_period = self.config.get("sma_period", 20)
        self.divergence_lookback = self.config.get("divergence_lookback", 10)
        self.min_price_change = self.config.get("min_price_change", 2.0)
        self.timeframe = self.config.get("timeframe", "D")
        self.confidence = self.config.get("confidence", 0.70)
    
    def _validate_config(self):
        """Validate OBV generator configuration."""
        sma_period = self.config.get("sma_period", 20)
        if sma_period < 2:
            raise ValueError("sma_period must be >= 2")
    
    async def generate(self) -> List[Signal]:
        """Generate OBV signals."""
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "obv_scan_started",
            tickers=tickers,
            sma_period=self.sma_period,
            divergence_lookback=self.divergence_lookback
        )
        
        for ticker in tickers:
            try:
                # Fetch OBV from Finnhub
                lookback_days = self.sma_period + self.divergence_lookback + 50
                obv_data = await self.market_data.fetch_indicator(
                    symbol=ticker,
                    indicator="obv",
                    resolution=self.timeframe,
                    lookback_days=lookback_days
                )
                
                if not obv_data or "obv" not in obv_data:
                    logger.warning("obv_data_unavailable", ticker=ticker)
                    continue
                
                obv_values = obv_data["obv"]
                close_prices = obv_data.get("c", [])
                
                if len(obv_values) < self.divergence_lookback + 1 or len(close_prices) < self.divergence_lookback + 1:
                    logger.warning("insufficient_obv_data", ticker=ticker)
                    continue
                
                current_obv = obv_values[-1]
                lookback_obv = obv_values[-(self.divergence_lookback + 1)]
                
                current_price = close_prices[-1]
                lookback_price = close_prices[-(self.divergence_lookback + 1)]
                
                obv_change_pct = ((current_obv - lookback_obv) / abs(lookback_obv)) * 100 if lookback_obv != 0 else 0
                price_change_pct = ((current_price - lookback_price) / lookback_price) * 100
                
                # Bullish divergence (OBV rising, price falling/flat)
                if obv_change_pct > 5 and price_change_pct < -self.min_price_change:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BULLISH,
                        confidence=self.confidence * 100,
                        reasoning=(
                            f"OBV bullish divergence: OBV up {obv_change_pct:.1f}% while "
                            f"price down {abs(price_change_pct):.1f}%. Accumulation phase."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.OBV_BULLISH_DIVERGENCE,
                        source="obv_generator",
                        tickers=[ticker_signal],
                        metadata={
                            "current_obv": int(current_obv),
                            "obv_change_pct": round(obv_change_pct, 2),
                            "price_change_pct": round(price_change_pct, 2),
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2)
                        }
                    )
                    
                    signals.append(signal)
                    logger.info("obv_bullish_divergence", ticker=ticker, obv_change=round(obv_change_pct, 1))
                
                # Bearish divergence (OBV falling, price rising/flat)
                elif obv_change_pct < -5 and price_change_pct > self.min_price_change:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BEARISH,
                        confidence=self.confidence * 100,
                        reasoning=(
                            f"OBV bearish divergence: OBV down {abs(obv_change_pct):.1f}% while "
                            f"price up {price_change_pct:.1f}%. Distribution phase."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.OBV_BEARISH_DIVERGENCE,
                        source="obv_generator",
                        tickers=[ticker_signal],
                        metadata={
                            "current_obv": int(current_obv),
                            "obv_change_pct": round(obv_change_pct, 2),
                            "price_change_pct": round(price_change_pct, 2),
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2)
                        }
                    )
                    
                    signals.append(signal)
                    logger.info("obv_bearish_divergence", ticker=ticker, obv_change=round(obv_change_pct, 1))
                
                # Strong OBV breakout (confirming price move)
                elif obv_change_pct > 10 and price_change_pct > self.min_price_change:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BULLISH,
                        confidence=self.confidence * 0.9 * 100,
                        reasoning=(
                            f"OBV bullish breakout: OBV up {obv_change_pct:.1f}% with "
                            f"price up {price_change_pct:.1f}%. Strong volume confirmation."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.OBV_BULLISH_BREAKOUT,
                        source="obv_generator",
                        tickers=[ticker_signal],
                        metadata={
                            "current_obv": int(current_obv),
                            "obv_change_pct": round(obv_change_pct, 2),
                            "price_change_pct": round(price_change_pct, 2),
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2)
                        }
                    )
                    
                    signals.append(signal)
                    logger.info("obv_bullish_breakout", ticker=ticker)
                
                # Strong OBV breakdown
                elif obv_change_pct < -10 and price_change_pct < -self.min_price_change:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BEARISH,
                        confidence=self.confidence * 0.9 * 100,
                        reasoning=(
                            f"OBV bearish breakdown: OBV down {abs(obv_change_pct):.1f}% with "
                            f"price down {abs(price_change_pct):.1f}%. Strong volume confirmation."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.OBV_BEARISH_BREAKDOWN,
                        source="obv_generator",
                        tickers=[ticker_signal],
                        metadata={
                            "current_obv": int(current_obv),
                            "obv_change_pct": round(obv_change_pct, 2),
                            "price_change_pct": round(price_change_pct, 2),
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2)
                        }
                    )
                    
                    signals.append(signal)
                    logger.info("obv_bearish_breakdown", ticker=ticker)
            
            except Exception as e:
                logger.error("obv_check_failed", ticker=ticker, error=str(e), exc_info=True)
                continue
        
        logger.info("obv_scan_completed", signals_generated=len(signals))
        return signals

