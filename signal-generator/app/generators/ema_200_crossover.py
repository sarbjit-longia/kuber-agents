"""
200 EMA Crossover Signal Generator

Monitors for price crossing above/below the 200 EMA - a classic trend following signal.
"""
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class EMA200CrossoverSignalGenerator(BaseSignalGenerator):
    """
    200 EMA Crossover signal generator.
    
    Monitors for price crossing the 200-period EMA:
    - Price crosses above 200 EMA: BULLISH (trend reversal/continuation)
    - Price crosses below 200 EMA: BEARISH (trend reversal/continuation)
    
    This is a classic trend-following signal used by institutions.
    
    Configuration:
        - tickers: List of tickers to monitor
        - ema_period: EMA period (default: 200)
        - timeframe: Candle resolution (default: "D")
        - lookback_periods: Periods to check for crossover (default: 3)
        - confidence: Confidence level (default: 0.75)
    
    Example config:
        {
            "tickers": ["EUR_USD", "GBP_USD", "AAPL"],
            "ema_period": 200,
            "timeframe": "60",
            "lookback_periods": 3,
            "confidence": 0.75
        }
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_data = MarketDataFetcher()
        self.ema_period = self.config.get("ema_period", 200)
        self.timeframe = self.config.get("timeframe", "D")
        self.lookback_periods = self.config.get("lookback_periods", 3)
        self.confidence = self.config.get("confidence", 0.75)
    
    def _validate_config(self):
        """Validate 200 EMA crossover configuration."""
        ema_period = self.config.get("ema_period", 200)
        if ema_period < 50:
            raise ValueError(f"ema_period should be >= 50 for trend following, got {ema_period}")
        
        lookback = self.config.get("lookback_periods", 3)
        if lookback < 1:
            raise ValueError("lookback_periods must be >= 1")
    
    async def generate(self) -> List[Signal]:
        """Generate 200 EMA crossover signals."""
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "ema_200_crossover_scan_started",
            tickers=tickers,
            ema_period=self.ema_period,
            timeframe=self.timeframe
        )
        
        for ticker in tickers:
            try:
                # Fetch price data and 200 EMA
                lookback_days = self.ema_period + self.lookback_periods + 50
                
                # Fetch 200 EMA
                ema_data = await self.market_data.fetch_indicator(
                    symbol=ticker,
                    indicator="ema",
                    resolution=self.timeframe,
                    lookback_days=lookback_days,
                    timeperiod=self.ema_period,
                    seriestype="c"
                )
                
                # Fetch recent candles for close prices
                candles_df = await self.market_data.fetch_candles(
                    symbol=ticker,
                    resolution=self.timeframe,
                    lookback_days=self.lookback_periods + 10
                )
                
                # Convert DataFrame to list of dicts
                candles = self._dataframe_to_candles(candles_df)
                
                if not ema_data or "ema" not in ema_data:
                    logger.debug("ema_200_data_unavailable", ticker=ticker)
                    continue
                
                if not candles or len(candles) < self.lookback_periods + 1:
                    logger.debug("insufficient_candle_data", ticker=ticker)
                    continue
                
                ema_values = ema_data["ema"]
                
                # Filter out None values
                valid_ema = [v for v in ema_values if v is not None]
                if len(valid_ema) < self.lookback_periods + 1:
                    logger.debug("insufficient_ema_values", ticker=ticker)
                    continue
                
                # Get latest EMA values and close prices
                current_ema = valid_ema[-1]
                previous_ema = valid_ema[-2]
                
                current_close = candles[-1]["c"]
                previous_close = candles[-2]["c"]
                
                # Detect crossover
                bullish_crossover = (
                    current_close > current_ema and 
                    previous_close <= previous_ema
                )
                
                bearish_crossover = (
                    current_close < current_ema and 
                    previous_close >= previous_ema
                )
                
                if bullish_crossover:
                    logger.info(
                        "ema_200_bullish_crossover_detected",
                        ticker=ticker,
                        current_close=current_close,
                        current_ema=current_ema,
                        previous_close=previous_close,
                        previous_ema=previous_ema
                    )
                    
                    # Calculate confidence based on how strong the crossover is
                    crossover_strength = abs(current_close - current_ema) / current_ema
                    confidence = min(self.confidence + crossover_strength * 10, 0.95)
                    
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BULLISH,
                        confidence=confidence * 100,
                        reasoning=(
                            f"Price crossed above 200 EMA. "
                            f"Close: {current_close:.5f}, EMA200: {current_ema:.5f}. "
                            f"Classic bullish trend signal."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.EMA_200_BULLISH_CROSSOVER,
                        source="ema_200_generator",
                        tickers=[ticker_signal]
                    )
                    signals.append(signal)
                
                elif bearish_crossover:
                    logger.info(
                        "ema_200_bearish_crossover_detected",
                        ticker=ticker,
                        current_close=current_close,
                        current_ema=current_ema,
                        previous_close=previous_close,
                        previous_ema=previous_ema
                    )
                    
                    # Calculate confidence
                    crossover_strength = abs(current_close - current_ema) / current_ema
                    confidence = min(self.confidence + crossover_strength * 10, 0.95)
                    
                    ticker_signal = TickerSignal(
                        ticker=ticker,
                        signal=BiasType.BEARISH,
                        confidence=confidence * 100,
                        reasoning=(
                            f"Price crossed below 200 EMA. "
                            f"Close: {current_close:.5f}, EMA200: {current_ema:.5f}. "
                            f"Classic bearish trend signal."
                        )
                    )
                    
                    signal = Signal(
                        signal_type=SignalType.EMA_200_BEARISH_CROSSOVER,
                        source="ema_200_generator",
                        tickers=[ticker_signal]
                    )
                    signals.append(signal)
                
            except Exception as e:
                logger.error(
                    "ema_200_crossover_error",
                    ticker=ticker,
                    error=str(e),
                    exc_info=True
                )
                continue
        
        logger.info(
            "ema_200_crossover_scan_completed",
            signals_generated=len(signals),
            tickers_with_signal=[s.tickers[0].ticker for s in signals] if signals else []
        )
        
        return signals
