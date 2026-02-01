"""
Fair Value Gap (FVG) Signal Generator

Detects price imbalances (gaps) that typically get filled.
"""
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class FairValueGapSignalGenerator(BaseSignalGenerator):
    """
    Fair Value Gap (FVG) signal generator.
    
    Detects price imbalances where:
    - Bullish FVG: Candle[n-2].high < Candle[n].low (gap up)
    - Bearish FVG: Candle[n-2].low > Candle[n].high (gap down)
    
    These gaps tend to get filled, providing trading opportunities.
    
    Configuration:
        - tickers: List of tickers to monitor
        - min_gap_pips: Minimum gap size in pips (default: 10)
        - timeframe: Candle resolution (default: "60")
        - confidence: Confidence level (default: 0.80)
    
    Example config:
        {
            "tickers": ["EUR_USD", "GBP_USD"],
            "min_gap_pips": 10,
            "timeframe": "60",
            "confidence": 0.80
        }
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_data = MarketDataFetcher()
        self.min_gap_pips = self.config.get("min_gap_pips", 10)
        self.timeframe = self.config.get("timeframe", "60")
        self.confidence = self.config.get("confidence", 0.80)
    
    def _validate_config(self):
        """Validate FVG configuration."""
        min_gap = self.config.get("min_gap_pips", 10)
        if min_gap < 1:
            raise ValueError("min_gap_pips must be >= 1")
    
    def _calculate_pip_value(self, symbol: str) -> float:
        """Calculate pip value for the symbol."""
        # For JPY pairs, 1 pip = 0.01, for others 1 pip = 0.0001
        if "JPY" in symbol.upper():
            return 0.01
        return 0.0001
    
    async def generate(self) -> List[Signal]:
        """Generate fair value gap signals."""
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "fair_value_gap_scan_started",
            tickers=tickers,
            min_gap_pips=self.min_gap_pips
        )
        
        for ticker in tickers:
            try:
                # Fetch recent candles
                candles_df = await self.market_data.fetch_candles(
                    symbol=ticker,
                    resolution=self.timeframe,
                    lookback_days=10
                )
                
                # Convert DataFrame to list of dicts
                candles = self._dataframe_to_candles(candles_df)
                
                if not candles or len(candles) < 3:
                    logger.debug("insufficient_candle_data", ticker=ticker)
                    continue
                
                # Calculate pip value
                pip_value = self._calculate_pip_value(ticker)
                min_gap_price = self.min_gap_pips * pip_value
                
                # Check for FVG in recent 3 candles
                candle_n_minus_2 = candles[-3]
                candle_n_minus_1 = candles[-2]
                candle_n = candles[-1]
                
                # Bullish FVG: Gap between candle[-3].high and candle[-1].low
                bullish_gap = candle_n.get("l") - candle_n_minus_2.get("h")
                
                if bullish_gap > min_gap_price:
                    gap_pips = bullish_gap / pip_value
                    
                    logger.info(
                        "bullish_fvg_detected",
                        ticker=ticker,
                        gap_pips=gap_pips,
                        gap_low=candle_n_minus_2.get("h"),
                        gap_high=candle_n.get("l")
                    )
                    
                    # Higher confidence for larger gaps
                    confidence = min(self.confidence + (gap_pips / 100), 0.90)
                    
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BULLISH,
                        confidence=confidence * 100,
                        reasoning=(
                            f"Bullish Fair Value Gap detected: {gap_pips:.1f} pips gap "
                            f"between {candle_n_minus_2.get('h'):.5f} and {candle_n.get('l'):.5f}. "
                            f"Price likely to fill gap and continue upward."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.FVG_BULLISH,
                        source="fvg_generator",
                        tickers=[ticker_signal],
                        metadata=self._enrich_metadata({
                            "gap_pips": gap_pips,
                            "gap_low": candle_n_minus_2.get("h"),
                            "gap_high": candle_n.get("l"),
                            "middle_candle_time": str(candle_n_minus_1.get("t"))
                        })
                    )
                    signals.append(signal)
                
                # Bearish FVG: Gap between candle[-3].low and candle[-1].high
                bearish_gap = candle_n_minus_2.get("l") - candle_n.get("h")
                
                if bearish_gap > min_gap_price:
                    gap_pips = bearish_gap / pip_value
                    
                    logger.info(
                        "bearish_fvg_detected",
                        ticker=ticker,
                        gap_pips=gap_pips,
                        gap_high=candle_n_minus_2.get("l"),
                        gap_low=candle_n.get("h")
                    )
                    
                    confidence = min(self.confidence + (gap_pips / 100), 0.90)
                    
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BEARISH,
                        confidence=confidence * 100,
                        reasoning=(
                            f"Bearish Fair Value Gap detected: {gap_pips:.1f} pips gap "
                            f"between {candle_n.get('h'):.5f} and {candle_n_minus_2.get('l'):.5f}. "
                            f"Price likely to fill gap and continue downward."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.FVG_BEARISH,
                        source="fvg_generator",
                        tickers=[ticker_signal],
                        metadata=self._enrich_metadata({
                            "gap_pips": gap_pips,
                            "gap_high": candle_n_minus_2.get("l"),
                            "gap_low": candle_n.get("h"),
                            "middle_candle_time": str(candle_n_minus_1.get("t"))
                        })
                    )
                    signals.append(signal)
                
            except Exception as e:
                logger.error(
                    "fair_value_gap_error",
                    ticker=ticker,
                    error=str(e),
                    exc_info=True
                )
                continue
        
        logger.info(
            "fair_value_gap_scan_completed",
            signals_generated=len(signals),
            tickers_with_signal=[s.tickers[0].ticker for s in signals] if signals else []
        )
        
        return signals
