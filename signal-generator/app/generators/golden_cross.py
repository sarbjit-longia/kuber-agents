"""
Golden Cross Signal Generator

Monitors for golden cross patterns (short SMA crossing above long SMA).
"""
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class GoldenCrossSignalGenerator(BaseSignalGenerator):
    """
    Golden Cross signal generator.
    
    Monitors a watchlist of tickers for golden cross patterns:
    - Short-term SMA (default 50-day) crosses above long-term SMA (default 200-day)
    - Generates BULLISH bias signals when detected
    
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
        """Validate golden cross generator configuration."""
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
        Check for golden cross patterns and generate signals.
        
        Returns:
            List of Signal objects for tickers with golden cross detected
        """
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "golden_cross_scan_started",
            tickers=tickers,
            sma_short=self.sma_short,
            sma_long=self.sma_long
        )
        
        for ticker in tickers:
            try:
                # Fetch historical data
                # Need enough data for the long SMA plus lookback
                lookback_days_total = self.sma_long + self.lookback_days + 50
                df = await self.market_data.fetch_candles(
                    symbol=ticker,
                    resolution=self.timeframe,
                    lookback_days=lookback_days_total
                )
                
                if df is None or len(df) < self.sma_long:
                    logger.warning(
                        "insufficient_data_for_golden_cross",
                        ticker=ticker,
                        required=self.sma_long,
                        available=len(df) if df is not None else 0
                    )
                    continue
                
                # Check for golden cross
                has_golden_cross = self.market_data.detect_golden_cross(
                    df,
                    short_period=self.sma_short,
                    long_period=self.sma_long,
                    lookback_days=self.lookback_days
                )
                
                if has_golden_cross:
                    # Calculate current SMA values for metadata
                    df["sma_short"] = self.market_data.calculate_sma(df, self.sma_short)
                    df["sma_long"] = self.market_data.calculate_sma(df, self.sma_long)
                    latest = df.iloc[-1]
                    
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BULLISH,
                        confidence=self.confidence * 100,  # Convert to 0-100 scale
                        reasoning=(
                            f"Golden cross detected: {self.sma_short}-day SMA "
                            f"crossed above {self.sma_long}-day SMA"
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.GOLDEN_CROSS,
                        source="golden_cross_generator",
                        tickers=[ticker_signal],
                        metadata={
                            "sma_short": self.sma_short,
                            "sma_long": self.sma_long,
                            "timeframe": self.timeframe,
                            "current_sma_short": round(latest["sma_short"], 2),
                            "current_sma_long": round(latest["sma_long"], 2),
                            "current_price": round(latest["close"], 2),
                            "lookback_days": self.lookback_days
                        }
                    )
                    
                    signals.append(signal)
                    
                    logger.info(
                        "golden_cross_signal_generated",
                        signal_id=str(signal.signal_id),
                        ticker=ticker,
                        sma_short_value=round(latest["sma_short"], 2),
                        sma_long_value=round(latest["sma_long"], 2)
                    )
            
            except Exception as e:
                logger.error(
                    "golden_cross_check_failed",
                    ticker=ticker,
                    error=str(e),
                    exc_info=True
                )
                # Continue with next ticker
                continue
        
        if signals:
            logger.info(
                "golden_cross_scan_completed",
                signals_generated=len(signals),
                tickers_with_signal=[s.tickers[0] for s in signals]
            )
        else:
            logger.info(
                "golden_cross_scan_completed",
                signals_generated=0,
                message="No golden crosses detected"
            )
        
        return signals

