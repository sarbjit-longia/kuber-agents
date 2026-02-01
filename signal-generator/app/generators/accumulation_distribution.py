"""
Accumulation/Distribution Signal Generator

Detects accumulation and distribution phases using A/D Line.
"""
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class AccumulationDistributionSignalGenerator(BaseSignalGenerator):
    """
    Accumulation/Distribution signal generator.
    
    Uses A/D Line to detect:
    - Accumulation: A/D line rising (buying pressure)
    - Distribution: A/D line falling (selling pressure)
    
    Strong signal when A/D diverges from price.
    
    Configuration:
        - tickers: List of tickers to monitor
        - lookback_periods: Periods to analyze trend (default: 14)
        - min_slope_threshold: Minimum A/D slope change (default: 0.001)
        - timeframe: Candle resolution (default: "60")
        - confidence: Confidence level (default: 0.75)
    
    Example config:
        {
            "tickers": ["EUR_USD", "GBP_USD"],
            "lookback_periods": 14,
            "min_slope_threshold": 0.001,
            "timeframe": "60",
            "confidence": 0.75
        }
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_data = MarketDataFetcher()
        self.lookback_periods = self.config.get("lookback_periods", 14)
        self.min_slope_threshold = self.config.get("min_slope_threshold", 0.001)
        self.timeframe = self.config.get("timeframe", "60")
        self.confidence = self.config.get("confidence", 0.75)
    
    def _validate_config(self):
        """Validate A/D configuration."""
        lookback = self.config.get("lookback_periods", 14)
        if lookback < 5:
            raise ValueError(f"lookback_periods should be >= 5, got {lookback}")
    
    def _calculate_ad_line(self, candles: List[Dict]) -> List[float]:
        """Calculate Accumulation/Distribution Line."""
        ad_line = []
        ad_value = 0
        
        for candle in candles:
            high = candle["h"]
            low = candle["l"]
            close = candle["c"]
            volume = candle.get("v", 1)  # Default to 1 if no volume
            
            # Money Flow Multiplier
            if high == low:
                mfm = 0
            else:
                mfm = ((close - low) - (high - close)) / (high - low)
            
            # Money Flow Volume
            mfv = mfm * volume
            
            # Accumulate
            ad_value += mfv
            ad_line.append(ad_value)
        
        return ad_line
    
    def _calculate_slope(self, values: List[float]) -> float:
        """Calculate slope of recent values using simple linear regression."""
        n = len(values)
        if n < 2:
            return 0
        
        # Simple slope: (last - first) / n
        return (values[-1] - values[0]) / n
    
    async def generate(self) -> List[Signal]:
        """Generate accumulation/distribution signals."""
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "accumulation_distribution_scan_started",
            tickers=tickers,
            lookback_periods=self.lookback_periods
        )
        
        for ticker in tickers:
            try:
                # Fetch candles
                lookback_days = self.lookback_periods + 10
                candles_df = await self.market_data.fetch_candles(
                    symbol=ticker,
                    resolution=self.timeframe,
                    lookback_days=lookback_days
                )
                
                # Convert DataFrame to list of dicts
                candles = self._dataframe_to_candles(candles_df)
                
                if not candles or len(candles) < self.lookback_periods:
                    logger.debug("insufficient_candle_data", ticker=ticker)
                    continue
                
                # Calculate A/D Line
                ad_line = self._calculate_ad_line(candles)
                
                if len(ad_line) < self.lookback_periods:
                    continue
                
                # Calculate recent slope
                recent_ad = ad_line[-self.lookback_periods:]
                ad_slope = self._calculate_slope(recent_ad)
                
                # Normalize slope by price for comparison
                avg_price = sum([c["c"] for c in candles[-self.lookback_periods:]]) / self.lookback_periods
                normalized_slope = ad_slope / avg_price if avg_price != 0 else 0
                
                # Check for accumulation (strong positive slope)
                if normalized_slope > self.min_slope_threshold:
                    current_price = candles[-1]["c"]
                    ad_change_pct = ((recent_ad[-1] - recent_ad[0]) / abs(recent_ad[0]) * 100) if recent_ad[0] != 0 else 0
                    
                    logger.info(
                        "accumulation_detected",
                        ticker=ticker,
                        ad_slope=ad_slope,
                        normalized_slope=normalized_slope,
                        ad_change_pct=ad_change_pct,
                        current_price=current_price
                    )
                    
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BULLISH,
                        confidence=min(self.confidence * 100 + abs(ad_change_pct), 95),
                        reasoning=(
                            f"Accumulation Phase: A/D line rising ({ad_change_pct:.1f}% over {self.lookback_periods} periods). "
                            f"Strong buying pressure detected at {current_price:.5f}. "
                            f"Institutional accumulation likely."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.ACCUMULATION_SIGNAL,
                        source="accumulation_distribution_generator",
                        tickers=[ticker_signal],
                        metadata=self._enrich_metadata({
                            "ad_slope": ad_slope,
                            "normalized_slope": normalized_slope,
                            "ad_change_pct": ad_change_pct,
                            "current_price": current_price,
                            "lookback_periods": self.lookback_periods
                        })
                    )
                    signals.append(signal)
                
                # Check for distribution (strong negative slope)
                elif normalized_slope < -self.min_slope_threshold:
                    current_price = candles[-1]["c"]
                    ad_change_pct = ((recent_ad[-1] - recent_ad[0]) / abs(recent_ad[0]) * 100) if recent_ad[0] != 0 else 0
                    
                    logger.info(
                        "distribution_detected",
                        ticker=ticker,
                        ad_slope=ad_slope,
                        normalized_slope=normalized_slope,
                        ad_change_pct=ad_change_pct,
                        current_price=current_price
                    )
                    
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BEARISH,
                        confidence=min(self.confidence * 100 + abs(ad_change_pct), 95),
                        reasoning=(
                            f"Distribution Phase: A/D line falling ({ad_change_pct:.1f}% over {self.lookback_periods} periods). "
                            f"Strong selling pressure detected at {current_price:.5f}. "
                            f"Institutional distribution likely."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.DISTRIBUTION_SIGNAL,
                        source="accumulation_distribution_generator",
                        tickers=[ticker_signal],
                        metadata=self._enrich_metadata({
                            "ad_slope": ad_slope,
                            "normalized_slope": normalized_slope,
                            "ad_change_pct": ad_change_pct,
                            "current_price": current_price,
                            "lookback_periods": self.lookback_periods
                        })
                    )
                    signals.append(signal)
                
            except Exception as e:
                logger.error(
                    "accumulation_distribution_error",
                    ticker=ticker,
                    error=str(e),
                    exc_info=True
                )
                continue
        
        logger.info(
            "accumulation_distribution_scan_completed",
            signals_generated=len(signals),
            tickers_with_signal=[s.tickers[0].ticker for s in signals] if signals else []
        )
        
        return signals
