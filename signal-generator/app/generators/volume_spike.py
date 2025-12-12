"""
Volume Spike Signal Generator

Monitors for unusual volume activity (volume spikes).
"""
from typing import Dict, Any, List
import structlog
import pandas as pd

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class VolumeSpikeSignalGenerator(BaseSignalGenerator):
    """
    Volume Spike signal generator.
    
    Monitors a watchlist of tickers for unusual volume activity:
    - Current volume > average volume * threshold: Generates BULLISH or NEUTRAL signal
    - Can be combined with price direction for bias
    
    Configuration:
        - tickers: List of tickers to monitor
        - volume_period: Period for average volume calculation (default: 20)
        - spike_threshold: Multiplier for volume spike (default: 2.0 = 200% of average)
        - timeframe: Candle resolution (default: "D" for daily)
        - confidence: Confidence level for generated signals (default: 0.70)
        - use_price_direction: Use price direction for bias (default: True)
        - min_price_change_pct: Minimum price change % to consider (default: 1.0%)
    
    Example config:
        {
            "tickers": ["AAPL", "MSFT", "GOOGL"],
            "volume_period": 20,
            "spike_threshold": 2.0,
            "timeframe": "D",
            "confidence": 0.70,
            "use_price_direction": True,
            "min_price_change_pct": 1.0
        }
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_data = MarketDataFetcher()
        self.volume_period = self.config.get("volume_period", 20)
        self.spike_threshold = self.config.get("spike_threshold", 2.0)
        self.timeframe = self.config.get("timeframe", "D")
        self.confidence = self.config.get("confidence", 0.70)
        self.use_price_direction = self.config.get("use_price_direction", True)
        self.min_price_change_pct = self.config.get("min_price_change_pct", 1.0)
    
    def _validate_config(self):
        """Validate volume spike generator configuration."""
        period = self.config.get("volume_period", 20)
        if period < 5:
            raise ValueError(f"volume_period must be >= 5, got {period}")
        
        threshold = self.config.get("spike_threshold", 2.0)
        if threshold < 1.0:
            raise ValueError(f"spike_threshold must be >= 1.0, got {threshold}")
        
        confidence = self.config.get("confidence", 0.70)
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
    
    async def generate(self) -> List[Signal]:
        """
        Check for volume spikes and generate signals.
        
        Returns:
            List of Signal objects for tickers with volume spikes
        """
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "volume_spike_scan_started",
            tickers=tickers,
            period=self.volume_period,
            threshold=self.spike_threshold
        )
        
        for ticker in tickers:
            try:
                # Fetch historical data
                lookback_days = self.volume_period + 50
                df = await self.market_data.fetch_candles(
                    symbol=ticker,
                    resolution=self.timeframe,
                    lookback_days=lookback_days
                )
                
                if df is None or len(df) < self.volume_period + 1:
                    logger.warning(
                        "insufficient_data_for_volume_spike",
                        ticker=ticker,
                        required=self.volume_period + 1,
                        available=len(df) if df is not None else 0
                    )
                    continue
                
                # Calculate average volume
                avg_volume = df["volume"].rolling(window=self.volume_period).mean()
                current_volume = df.iloc[-1]["volume"]
                avg_volume_value = avg_volume.iloc[-1]
                
                # Check for volume spike
                volume_ratio = current_volume / avg_volume_value if avg_volume_value > 0 else 0
                
                if volume_ratio >= self.spike_threshold:
                    # Determine bias based on price direction
                    current_close = df.iloc[-1]["close"]
                    current_open = df.iloc[-1]["open"]
                    price_change_pct = ((current_close - current_open) / current_open) * 100
                    
                    if self.use_price_direction:
                        if abs(price_change_pct) < self.min_price_change_pct:
                            # Price change too small, use NEUTRAL
                            bias = BiasType.NEUTRAL
                            bias_reason = "neutral price action"
                        elif price_change_pct > 0:
                            bias = BiasType.BULLISH
                            bias_reason = f"price up {price_change_pct:.1f}%"
                        else:
                            bias = BiasType.BEARISH
                            bias_reason = f"price down {abs(price_change_pct):.1f}%"
                    else:
                        bias = BiasType.NEUTRAL
                        bias_reason = "price direction not considered"
                    
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=bias,
                        confidence=self.confidence * 100,
                        reasoning=(
                            f"Volume spike detected: {volume_ratio:.2f}x average volume "
                            f"({int(current_volume):,} vs {int(avg_volume_value):,}). "
                            f"Price: {bias_reason}"
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.VOLUME_SPIKE,
                        source="volume_spike_generator",
                        tickers=[ticker_signal],
                        metadata={
                            "volume_period": self.volume_period,
                            "spike_threshold": self.spike_threshold,
                            "current_volume": int(current_volume),
                            "average_volume": int(avg_volume_value),
                            "volume_ratio": round(volume_ratio, 2),
                            "price_change_pct": round(price_change_pct, 2),
                            "timeframe": self.timeframe,
                            "current_price": round(current_close, 2)
                        }
                    )
                    
                    signals.append(signal)
                    
                    logger.info(
                        "volume_spike_signal_generated",
                        signal_id=str(signal.signal_id),
                        ticker=ticker,
                        volume_ratio=round(volume_ratio, 2),
                        bias=bias.value
                    )
            
            except Exception as e:
                logger.error(
                    "volume_spike_check_failed",
                    ticker=ticker,
                    error=str(e),
                    exc_info=True
                )
                continue
        
        if signals:
            logger.info(
                "volume_spike_scan_completed",
                signals_generated=len(signals),
                tickers_with_signal=[s.tickers[0].ticker for s in signals]
            )
        else:
            logger.info(
                "volume_spike_scan_completed",
                signals_generated=0,
                message="No volume spikes detected"
            )
        
        return signals

