"""
ADX Signal Generator

Monitors for trend strength using Average Directional Index.
"""
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class ADXSignalGenerator(BaseSignalGenerator):
    """
    ADX (Average Directional Index) signal generator.
    
    Monitors trend strength:
    - ADX crossing above strong_trend threshold (default 25): Strong trend starting
    - ADX crossing below weak_trend threshold (default 20): Weak/no trend
    
    ADX doesn't indicate direction, only strength. Use with +DI/-DI for direction.
    
    Configuration:
        - tickers: List of tickers to monitor
        - timeperiod: ADX period (default: 14)
        - strong_trend: Strong trend threshold (default: 25)
        - weak_trend: Weak trend threshold (default: 20)
        - timeframe: Candle resolution (default: "D")
        - confidence: Confidence level (default: 0.70)
    
    Example config:
        {
            "tickers": ["AAPL", "MSFT", "GOOGL"],
            "timeperiod": 14,
            "strong_trend": 25,
            "weak_trend": 20,
            "timeframe": "D",
            "confidence": 0.70
        }
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_data = MarketDataFetcher()
        self.timeperiod = self.config.get("timeperiod", 14)
        self.strong_trend = self.config.get("strong_trend", 25)
        self.weak_trend = self.config.get("weak_trend", 20)
        self.timeframe = self.config.get("timeframe", "D")
        self.confidence = self.config.get("confidence", 0.70)
    
    def _validate_config(self):
        """Validate ADX generator configuration."""
        weak_trend = self.config.get("weak_trend", 20)
        strong_trend = self.config.get("strong_trend", 25)
        
        if weak_trend >= strong_trend:
            raise ValueError("weak_trend must be < strong_trend")
        if not 0 < strong_trend <= 100:
            raise ValueError("strong_trend must be 0-100")
    
    async def generate(self) -> List[Signal]:
        """Generate ADX trend strength signals."""
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "adx_scan_started",
            tickers=tickers,
            timeperiod=self.timeperiod,
            strong_threshold=self.strong_trend,
            weak_threshold=self.weak_trend
        )
        
        for ticker in tickers:
            try:
                # Fetch ADX from Finnhub
                lookback_days = 90
                adx_data = await self.market_data.fetch_indicator(
                    symbol=ticker,
                    indicator="adx",
                    resolution=self.timeframe,
                    lookback_days=lookback_days,
                    timeperiod=self.timeperiod
                )
                
                if not adx_data or "adx" not in adx_data:
                    logger.warning("adx_data_unavailable", ticker=ticker)
                    continue
                
                adx_values = adx_data["adx"]
                
                if len(adx_values) < 2:
                    logger.warning("insufficient_adx_data", ticker=ticker)
                    continue
                
                current_adx = adx_values[-1]
                previous_adx = adx_values[-2]
                
                current_price = adx_data.get("c", [None])[-1] if "c" in adx_data else None
                
                # Strong trend emerging
                if current_adx > self.strong_trend and previous_adx <= self.strong_trend:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.NEUTRAL,  # ADX doesn't indicate direction
                        confidence=self.confidence * 100,
                        reasoning=(
                            f"ADX strong trend detected: ADX ({current_adx:.1f}) crossed above "
                            f"{self.strong_trend}. Strong trend starting - confirm direction with price action."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.ADX_STRONG_TREND,
                        source="adx_generator",
                        tickers=[ticker_signal],
                        metadata=self._enrich_metadata({
                            "current_adx": round(current_adx, 2),
                            "previous_adx": round(previous_adx, 2),
                            "strong_threshold": self.strong_trend,
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        })
                    )
                    
                    signals.append(signal)
                    logger.info("adx_strong_trend_signal", ticker=ticker, adx=round(current_adx, 1))
                
                # Weak trend / choppy market
                elif current_adx < self.weak_trend and previous_adx >= self.weak_trend:
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.NEUTRAL,
                        confidence=self.confidence * 100,
                        reasoning=(
                            f"ADX weak trend detected: ADX ({current_adx:.1f}) crossed below "
                            f"{self.weak_trend}. Choppy/weak trend - avoid trend-following strategies."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.ADX_WEAK_TREND,
                        source="adx_generator",
                        tickers=[ticker_signal],
                        metadata=self._enrich_metadata({
                            "current_adx": round(current_adx, 2),
                            "previous_adx": round(previous_adx, 2),
                            "weak_threshold": self.weak_trend,
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        })
                    )
                    
                    signals.append(signal)
                    logger.info("adx_weak_trend_signal", ticker=ticker, adx=round(current_adx, 1))
            
            except Exception as e:
                logger.error("adx_check_failed", ticker=ticker, error=str(e), exc_info=True)
                continue
        
        logger.info("adx_scan_completed", signals_generated=len(signals))
        return signals

