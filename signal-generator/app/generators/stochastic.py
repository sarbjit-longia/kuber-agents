"""
Stochastic Oscillator Signal Generator

Monitors for Stochastic crossovers and extreme levels.
"""
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class StochasticSignalGenerator(BaseSignalGenerator):
    """
    Stochastic Oscillator signal generator.
    
    Monitors for:
    - %K crossing above %D: BULLISH
    - %K crossing below %D: BEARISH  
    - Overbought (>80) and oversold (<20) conditions
    
    Configuration:
        - tickers: List of tickers to monitor
        - fastk_period: Fast %K period (default: 14)
        - slowk_period: Slow %K period (default: 3)
        - slowd_period: %D period (default: 3)
        - overbought: Overbought level (default: 80)
        - oversold: Oversold level (default: 20)
        - timeframe: Candle resolution (default: "D")
        - confidence: Confidence level (default: 0.75)
    
    Example config:
        {
            "tickers": ["AAPL", "MSFT", "GOOGL"],
            "fastk_period": 14,
            "slowk_period": 3,
            "slowd_period": 3,
            "overbought": 80,
            "oversold": 20,
            "timeframe": "D",
            "confidence": 0.75
        }
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_data = MarketDataFetcher()
        self.fastk_period = self.config.get("fastk_period", 14)
        self.slowk_period = self.config.get("slowk_period", 3)
        self.slowd_period = self.config.get("slowd_period", 3)
        self.overbought = self.config.get("overbought", 80)
        self.oversold = self.config.get("oversold", 20)
        self.timeframe = self.config.get("timeframe", "D")
        self.confidence = self.config.get("confidence", 0.75)
    
    def _validate_config(self):
        """Validate Stochastic generator configuration."""
        overbought = self.config.get("overbought", 80)
        oversold = self.config.get("oversold", 20)
        
        if not 0 <= overbought <= 100:
            raise ValueError(f"overbought must be 0-100, got {overbought}")
        if not 0 <= oversold <= 100:
            raise ValueError(f"oversold must be 0-100, got {oversold}")
        if oversold >= overbought:
            raise ValueError(f"oversold must be < overbought")
    
    async def generate(self) -> List[Signal]:
        """Generate Stochastic signals."""
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "stochastic_scan_started",
            tickers=tickers,
            fastk=self.fastk_period,
            slowk=self.slowk_period,
            slowd=self.slowd_period
        )
        
        for ticker in tickers:
            try:
                # Fetch Stochastic from Finnhub
                lookback_days = 90
                stoch_data = await self.market_data.fetch_indicator(
                    symbol=ticker,
                    indicator="stoch",
                    resolution=self.timeframe,
                    lookback_days=lookback_days,
                    fastk_period=self.fastk_period,
                    slowk_period=self.slowk_period,
                    slowd_period=self.slowd_period
                )
                
                if not stoch_data or "slowk" not in stoch_data or "slowd" not in stoch_data:
                    logger.warning("stochastic_data_unavailable", ticker=ticker)
                    continue
                
                slowk_values = stoch_data["slowk"]  # %K line
                slowd_values = stoch_data["slowd"]  # %D line (signal)
                
                if len(slowk_values) < 2 or len(slowd_values) < 2:
                    logger.warning("insufficient_stoch_data", ticker=ticker)
                    continue
                
                current_k = slowk_values[-1]
                current_d = slowd_values[-1]
                previous_k = slowk_values[-2]
                previous_d = slowd_values[-2]
                
                current_price = stoch_data.get("c", [None])[-1] if "c" in stoch_data else None
                
                # Bullish crossover (%K crosses above %D)
                if current_k > current_d and previous_k <= previous_d:
                    # Extra confirmation if in oversold zone
                    in_oversold = current_k < self.oversold
                    conf_boost = 1.1 if in_oversold else 1.0
                    
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BULLISH,
                        confidence=min(self.confidence * conf_boost * 100, 100),
                        reasoning=(
                            f"Stochastic bullish crossover: %K ({current_k:.1f}) crossed above "
                            f"%D ({current_d:.1f})" +
                            (" in oversold zone" if in_oversold else "")
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.STOCH_BULLISH,
                        source="stochastic_generator",
                        tickers=[ticker_signal],
                        metadata=self._enrich_metadata({
                            "current_k": round(current_k, 2),
                            "current_d": round(current_d, 2),
                            "previous_k": round(previous_k, 2),
                            "previous_d": round(previous_d, 2),
                            "in_oversold": in_oversold,
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        })
                    )
                    
                    signals.append(signal)
                    logger.info("stoch_bullish_signal", ticker=ticker, k=round(current_k, 1))
                
                # Bearish crossover (%K crosses below %D)
                elif current_k < current_d and previous_k >= previous_d:
                    # Extra confirmation if in overbought zone
                    in_overbought = current_k > self.overbought
                    conf_boost = 1.1 if in_overbought else 1.0
                    
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BEARISH,
                        confidence=min(self.confidence * conf_boost * 100, 100),
                        reasoning=(
                            f"Stochastic bearish crossover: %K ({current_k:.1f}) crossed below "
                            f"%D ({current_d:.1f})" +
                            (" in overbought zone" if in_overbought else "")
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.STOCH_BEARISH,
                        source="stochastic_generator",
                        tickers=[ticker_signal],
                        metadata=self._enrich_metadata({
                            "current_k": round(current_k, 2),
                            "current_d": round(current_d, 2),
                            "previous_k": round(previous_k, 2),
                            "previous_d": round(previous_d, 2),
                            "in_overbought": in_overbought,
                            "timeframe": self.timeframe,
                            "current_price": round(current_price, 2) if current_price else None
                        })
                    )
                    
                    signals.append(signal)
                    logger.info("stoch_bearish_signal", ticker=ticker, k=round(current_k, 1))
            
            except Exception as e:
                logger.error("stochastic_check_failed", ticker=ticker, error=str(e), exc_info=True)
                continue
        
        logger.info("stochastic_scan_completed", signals_generated=len(signals))
        return signals

