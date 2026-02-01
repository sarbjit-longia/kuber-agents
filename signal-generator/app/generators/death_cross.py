"""
Death Cross Signal Generator

Monitors for death cross patterns (bearish crossover) using Finnhub's SMA indicator.
"""
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class DeathCrossSignalGenerator(BaseSignalGenerator):
    """
    Death Cross signal generator.
    
    Monitors a watchlist of tickers for death cross patterns:
    - Short-term SMA (default 50-day) crosses below long-term SMA (default 200-day)
    - Generates BEARISH bias signals when detected
    
    This is the opposite of the Golden Cross and indicates potential downtrend.
    
    Configuration:
        - tickers: List of tickers to monitor
        - sma_short: Short SMA period (default: 50)
        - sma_long: Long SMA period (default: 200)
        - timeframe: Candle resolution (default: "D" for daily)
        - lookback_days: How many recent days to check for crossover (default: 5)
        - confidence: Confidence level for generated bias (default: 0.85)
    
    Example config:
        {
            "tickers": ["AAPL", "MSFT", "GOOGL"],
            "sma_short": 50,
            "sma_long": 200,
            "timeframe": "D",
            "lookback_days": 5,
            "confidence": 0.85
        }
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_data = MarketDataFetcher()
        self.sma_short = self.config.get("sma_short", 50)
        self.sma_long = self.config.get("sma_long", 200)
        self.timeframe = self.config.get("timeframe", "D")
        self.lookback_days = self.config.get("lookback_days", 5)
        self.confidence = self.config.get("confidence", 0.85)
    
    def _validate_config(self):
        """Validate death cross generator configuration."""
        sma_short = self.config.get("sma_short", 50)
        sma_long = self.config.get("sma_long", 200)
        
        if sma_short >= sma_long:
            raise ValueError(
                f"sma_short ({sma_short}) must be less than sma_long ({sma_long})"
            )
        
        confidence = self.config.get("confidence", 0.85)
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
    
    async def generate(self) -> List[Signal]:
        """
        Check for death cross patterns and generate signals.
        
        Returns:
            List of Signal objects for tickers with death cross detected
        """
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "death_cross_scan_started",
            tickers=tickers,
            sma_short=self.sma_short,
            sma_long=self.sma_long
        )
        
        for ticker in tickers:
            try:
                # Fetch both SMAs from Finnhub
                lookback_days = self.sma_long + self.lookback_days + 50
                
                # Fetch short SMA
                sma_short_data = await self.market_data.fetch_indicator(
                    symbol=ticker,
                    indicator="sma",
                    resolution=self.timeframe,
                    lookback_days=lookback_days,
                    timeperiod=self.sma_short,
                    seriestype="c"
                )
                
                # Fetch long SMA
                sma_long_data = await self.market_data.fetch_indicator(
                    symbol=ticker,
                    indicator="sma",
                    resolution=self.timeframe,
                    lookback_days=lookback_days,
                    timeperiod=self.sma_long,
                    seriestype="c"
                )
                
                if not sma_short_data or "sma" not in sma_short_data:
                    logger.warning(
                        "short_sma_data_unavailable",
                        ticker=ticker
                    )
                    continue
                
                if not sma_long_data or "sma" not in sma_long_data:
                    logger.warning(
                        "long_sma_data_unavailable",
                        ticker=ticker
                    )
                    continue
                
                sma_short_values = sma_short_data["sma"]
                sma_long_values = sma_long_data["sma"]
                
                # Both should have same length, but use minimum to be safe
                min_len = min(len(sma_short_values), len(sma_long_values))
                
                if min_len < self.lookback_days + 1:
                    logger.warning(
                        "insufficient_data_for_death_cross",
                        ticker=ticker,
                        required=self.lookback_days + 1,
                        available=min_len
                    )
                    continue
                
                # Check recent data for death cross
                has_death_cross = False
                for i in range(1, min(self.lookback_days + 1, min_len)):
                    idx = -i
                    prev_idx = -(i + 1)
                    
                    current_short = sma_short_values[idx]
                    current_long = sma_long_values[idx]
                    prev_short = sma_short_values[prev_idx]
                    prev_long = sma_long_values[prev_idx]
                    
                    # Death cross: short was above, now below
                    if prev_short >= prev_long and current_short < current_long:
                        has_death_cross = True
                        logger.debug(
                            "death_cross_detected",
                            days_ago=i - 1,
                            prev_short=round(prev_short, 2),
                            prev_long=round(prev_long, 2),
                            current_short=round(current_short, 2),
                            current_long=round(current_long, 2)
                        )
                        break
                
                if has_death_cross:
                    # Get current values
                    current_short_sma = sma_short_values[-1]
                    current_long_sma = sma_long_values[-1]
                    current_price = sma_short_data.get("c", [None])[-1] if "c" in sma_short_data else None
                    
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BEARISH,
                        confidence=self.confidence * 100,
                        reasoning=(
                            f"Death cross detected: {self.sma_short}-day SMA "
                            f"crossed below {self.sma_long}-day SMA"
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.DEATH_CROSS,
                        source="death_cross_generator",
                        tickers=[ticker_signal],
                        metadata=self._enrich_metadata({
                            "sma_short": self.sma_short,
                            "sma_long": self.sma_long,
                            "timeframe": self.timeframe,
                            "current_sma_short": round(current_short_sma, 2),
                            "current_sma_long": round(current_long_sma, 2),
                            "current_price": round(current_price, 2) if current_price else None,
                            "lookback_days": self.lookback_days
                        })
                    )
                    
                    signals.append(signal)
                    
                    logger.info(
                        "death_cross_signal_generated",
                        signal_id=str(signal.signal_id),
                        ticker=ticker,
                        sma_short_value=round(current_short_sma, 2),
                        sma_long_value=round(current_long_sma, 2)
                    )
            
            except Exception as e:
                logger.error(
                    "death_cross_check_failed",
                    ticker=ticker,
                    error=str(e),
                    exc_info=True
                )
                continue
        
        if signals:
            logger.info(
                "death_cross_scan_completed",
                signals_generated=len(signals),
                tickers_with_signal=[s.tickers[0].ticker for s in signals]
            )
        else:
            logger.info(
                "death_cross_scan_completed",
                signals_generated=0,
                message="No death crosses detected"
            )
        
        return signals
