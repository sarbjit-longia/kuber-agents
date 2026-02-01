"""
HTF Trend Alignment Signal Generator

Confirms trend alignment across multiple higher timeframes.
"""
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class HTFTrendAlignmentSignalGenerator(BaseSignalGenerator):
    """
    Higher Timeframe (HTF) Trend Alignment signal generator.
    
    Confirms when multiple higher timeframes align:
    - Bullish Alignment: HTF EMAs all pointing up
    - Bearish Alignment: HTF EMAs all pointing down
    
    Strong confluence signal for trend following.
    
    Configuration:
        - tickers: List of tickers to monitor
        - ema_period: EMA period to use (default: 50)
        - htf_timeframes: List of HTF to check (default: ["60", "240", "D"])
        - min_alignment: Minimum TFs that must align (default: 2)
        - timeframe: Current timeframe (default: "15")
        - confidence: Confidence level (default: 0.85)
    
    Example config:
        {
            "tickers": ["EUR_USD", "GBP_USD"],
            "ema_period": 50,
            "htf_timeframes": ["60", "240", "D"],
            "min_alignment": 2,
            "timeframe": "15",
            "confidence": 0.85
        }
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_data = MarketDataFetcher()
        self.ema_period = self.config.get("ema_period", 50)
        self.htf_timeframes = self.config.get("htf_timeframes", ["60", "240", "D"])
        self.min_alignment = self.config.get("min_alignment", 2)
        self.timeframe = self.config.get("timeframe", "15")
        self.confidence = self.config.get("confidence", 0.85)
    
    def _validate_config(self):
        """Validate HTF trend alignment configuration."""
        min_align = self.config.get("min_alignment", 2)
        htf_count = len(self.config.get("htf_timeframes", ["60", "240", "D"]))
        
        if min_align > htf_count:
            raise ValueError(f"min_alignment ({min_align}) cannot exceed htf_timeframes count ({htf_count})")
    
    async def _get_ema_slope(self, ticker: str, timeframe: str, lookback: int = 3) -> float:
        """Get EMA slope for a timeframe (positive = uptrend, negative = downtrend)."""
        try:
            ema_data = await self.market_data.fetch_indicator(
                symbol=ticker,
                indicator="ema",
                resolution=timeframe,
                lookback_days=self.ema_period + lookback + 10,
                timeperiod=self.ema_period,
                seriestype="c"
            )
            
            if not ema_data or "ema" not in ema_data:
                return 0
            
            ema_values = ema_data["ema"]
            valid_ema = [v for v in ema_values if v is not None]
            
            if len(valid_ema) < lookback + 1:
                return 0
            
            # Calculate slope: (current - previous) / previous
            current = valid_ema[-1]
            previous = valid_ema[-(lookback+1)]
            
            if previous == 0:
                return 0
            
            slope = (current - previous) / previous
            return slope
            
        except Exception as e:
            logger.debug("ema_slope_fetch_error", ticker=ticker, timeframe=timeframe, error=str(e))
            return 0
    
    async def generate(self) -> List[Signal]:
        """Generate HTF trend alignment signals."""
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "htf_trend_alignment_scan_started",
            tickers=tickers,
            htf_timeframes=self.htf_timeframes,
            ema_period=self.ema_period,
            min_alignment=self.min_alignment
        )
        
        for ticker in tickers:
            try:
                # Get EMA slopes for all HTF timeframes
                slopes = {}
                for tf in self.htf_timeframes:
                    slope = await self._get_ema_slope(ticker, tf)
                    slopes[tf] = slope
                
                # Count bullish and bearish alignments
                bullish_count = sum(1 for slope in slopes.values() if slope > 0.001)
                bearish_count = sum(1 for slope in slopes.values() if slope < -0.001)
                
                # Check for bullish alignment
                if bullish_count >= self.min_alignment:
                    aligned_tfs = [tf for tf, slope in slopes.items() if slope > 0.001]
                    avg_slope = sum([slopes[tf] for tf in aligned_tfs]) / len(aligned_tfs)
                    slope_pct = avg_slope * 100
                    
                    logger.info(
                        "bullish_htf_alignment_detected",
                        ticker=ticker,
                        aligned_timeframes=aligned_tfs,
                        alignment_count=bullish_count,
                        avg_slope_pct=slope_pct
                    )
                    
                    confidence_boost = (bullish_count / len(self.htf_timeframes)) * 15
                    
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BULLISH,
                        confidence=min(self.confidence * 100 + confidence_boost, 95),
                        reasoning=(
                            f"Bullish HTF Alignment: {bullish_count}/{len(self.htf_timeframes)} higher timeframes aligned. "
                            f"Timeframes: {', '.join(aligned_tfs)}. "
                            f"Average slope: {slope_pct:.2f}%. Strong uptrend confirmation."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.HTF_TREND_ALIGNED_BULLISH,
                        source="htf_trend_alignment_generator",
                        tickers=[ticker_signal],
                        metadata=self._enrich_metadata({
                            "aligned_timeframes": aligned_tfs,
                            "alignment_count": bullish_count,
                            "total_timeframes": len(self.htf_timeframes),
                            "avg_slope_pct": slope_pct,
                            "ema_period": self.ema_period
                        })
                    )
                    signals.append(signal)
                
                # Check for bearish alignment
                elif bearish_count >= self.min_alignment:
                    aligned_tfs = [tf for tf, slope in slopes.items() if slope < -0.001]
                    avg_slope = sum([slopes[tf] for tf in aligned_tfs]) / len(aligned_tfs)
                    slope_pct = avg_slope * 100
                    
                    logger.info(
                        "bearish_htf_alignment_detected",
                        ticker=ticker,
                        aligned_timeframes=aligned_tfs,
                        alignment_count=bearish_count,
                        avg_slope_pct=slope_pct
                    )
                    
                    confidence_boost = (bearish_count / len(self.htf_timeframes)) * 15
                    
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BEARISH,
                        confidence=min(self.confidence * 100 + confidence_boost, 95),
                        reasoning=(
                            f"Bearish HTF Alignment: {bearish_count}/{len(self.htf_timeframes)} higher timeframes aligned. "
                            f"Timeframes: {', '.join(aligned_tfs)}. "
                            f"Average slope: {slope_pct:.2f}%. Strong downtrend confirmation."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.HTF_TREND_ALIGNED_BEARISH,
                        source="htf_trend_alignment_generator",
                        tickers=[ticker_signal],
                        metadata=self._enrich_metadata({
                            "aligned_timeframes": aligned_tfs,
                            "alignment_count": bearish_count,
                            "total_timeframes": len(self.htf_timeframes),
                            "avg_slope_pct": slope_pct,
                            "ema_period": self.ema_period
                        })
                    )
                    signals.append(signal)
                
            except Exception as e:
                logger.error(
                    "htf_trend_alignment_error",
                    ticker=ticker,
                    error=str(e),
                    exc_info=True
                )
                continue
        
        logger.info(
            "htf_trend_alignment_scan_completed",
            signals_generated=len(signals),
            tickers_with_signal=[s.tickers[0].ticker for s in signals] if signals else []
        )
        
        return signals
