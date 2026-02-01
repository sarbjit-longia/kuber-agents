"""
Momentum Divergence Signal Generator

Detects divergence between price and momentum indicators (RSI/MACD).
"""
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class MomentumDivergenceSignalGenerator(BaseSignalGenerator):
    """
    Momentum Divergence signal generator.
    
    Detects divergence between price and momentum indicators:
    - Bullish divergence: Price makes lower low, but RSI/MACD makes higher low
    - Bearish divergence: Price makes higher high, but RSI/MACD makes lower high
    
    Strong reversal signal when detected.
    
    Configuration:
        - tickers: List of tickers to monitor
        - indicator: Indicator to use ("rsi" or "macd", default: "rsi")
        - rsi_period: RSI period if using RSI (default: 14)
        - lookback_periods: Periods to scan for divergence (default: 14)
        - timeframe: Candle resolution (default: "60")
        - confidence: Base confidence level (default: 0.85)
    
    Example config:
        {
            "tickers": ["EUR_USD", "GBP_USD"],
            "indicator": "rsi",
            "rsi_period": 14,
            "lookback_periods": 14,
            "timeframe": "60",
            "confidence": 0.85
        }
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_data = MarketDataFetcher()
        self.indicator = self.config.get("indicator", "rsi")
        self.rsi_period = self.config.get("rsi_period", 14)
        self.lookback_periods = self.config.get("lookback_periods", 14)
        self.timeframe = self.config.get("timeframe", "60")
        self.confidence = self.config.get("confidence", 0.85)
    
    def _validate_config(self):
        """Validate divergence configuration."""
        indicator = self.config.get("indicator", "rsi")
        if indicator not in ["rsi", "macd"]:
            raise ValueError(f"indicator must be 'rsi' or 'macd', got {indicator}")
        
        lookback = self.config.get("lookback_periods", 14)
        if lookback < 5:
            raise ValueError(f"lookback_periods should be >= 5, got {lookback}")
    
    def _find_local_extremes(self, values: List[float], window: int = 3) -> tuple:
        """Find local highs and lows in a series."""
        highs = []
        lows = []
        
        for i in range(window, len(values) - window):
            is_high = all(values[i] >= values[i-j] for j in range(1, window+1)) and \
                     all(values[i] >= values[i+j] for j in range(1, window+1))
            
            is_low = all(values[i] <= values[i-j] for j in range(1, window+1)) and \
                    all(values[i] <= values[i+j] for j in range(1, window+1))
            
            if is_high:
                highs.append((i, values[i]))
            if is_low:
                lows.append((i, values[i]))
        
        return highs, lows
    
    async def generate(self) -> List[Signal]:
        """Generate momentum divergence signals."""
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "momentum_divergence_scan_started",
            tickers=tickers,
            indicator=self.indicator,
            lookback_periods=self.lookback_periods
        )
        
        for ticker in tickers:
            try:
                # Fetch price data
                lookback_days = self.lookback_periods + 20
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
                
                # Fetch indicator data
                if self.indicator == "rsi":
                    indicator_data = await self.market_data.fetch_indicator(
                        symbol=ticker,
                        indicator="rsi",
                        resolution=self.timeframe,
                        lookback_days=lookback_days,
                        timeperiod=self.rsi_period
                    )
                    
                    if not indicator_data or "rsi" not in indicator_data:
                        logger.debug("rsi_data_unavailable", ticker=ticker)
                        continue
                    
                    indicator_values = indicator_data["rsi"]
                    signal_type_bullish = SignalType.RSI_BULLISH_DIVERGENCE
                    signal_type_bearish = SignalType.RSI_BEARISH_DIVERGENCE
                
                else:  # macd
                    indicator_data = await self.market_data.fetch_indicator(
                        symbol=ticker,
                        indicator="macd",
                        resolution=self.timeframe,
                        lookback_days=lookback_days
                    )
                    
                    if not indicator_data or "macd" not in indicator_data:
                        logger.debug("macd_data_unavailable", ticker=ticker)
                        continue
                    
                    indicator_values = indicator_data["macd"]
                    signal_type_bullish = SignalType.MACD_BULLISH_DIVERGENCE
                    signal_type_bearish = SignalType.MACD_BEARISH_DIVERGENCE
                
                # Filter out None values
                valid_indicator = [(i, v) for i, v in enumerate(indicator_values) if v is not None]
                if len(valid_indicator) < self.lookback_periods:
                    logger.debug("insufficient_indicator_values", ticker=ticker)
                    continue
                
                # Align price and indicator data
                closes = [c["c"] for c in candles[-len(valid_indicator):]]
                indicator_clean = [v for _, v in valid_indicator]
                
                if len(closes) != len(indicator_clean):
                    logger.debug("data_alignment_mismatch", ticker=ticker)
                    continue
                
                # Find local extremes in both series
                price_highs, price_lows = self._find_local_extremes(closes, window=2)
                ind_highs, ind_lows = self._find_local_extremes(indicator_clean, window=2)
                
                # Check for bullish divergence (price lower low, indicator higher low)
                if len(price_lows) >= 2 and len(ind_lows) >= 2:
                    recent_price_lows = price_lows[-2:]
                    recent_ind_lows = ind_lows[-2:]
                    
                    # Price makes lower low
                    if recent_price_lows[1][1] < recent_price_lows[0][1]:
                        # Indicator makes higher low
                        if recent_ind_lows[1][1] > recent_ind_lows[0][1]:
                            logger.info(
                                "bullish_divergence_detected",
                                ticker=ticker,
                                indicator=self.indicator,
                                price_low_1=recent_price_lows[0][1],
                                price_low_2=recent_price_lows[1][1],
                                ind_low_1=recent_ind_lows[0][1],
                                ind_low_2=recent_ind_lows[1][1]
                            )
                            
                            ticker_signal = TickerSignal(
                                ticker=ticker,
                                signal=BiasType.BULLISH,
                                confidence=self.confidence * 100,
                                reasoning=(
                                    f"Bullish divergence: Price made lower low ({recent_price_lows[0][1]:.5f} → {recent_price_lows[1][1]:.5f}), "
                                    f"but {self.indicator.upper()} made higher low ({recent_ind_lows[0][1]:.2f} → {recent_ind_lows[1][1]:.2f}). "
                                    f"Strong reversal signal."
                                )
                            )
                            
                            signal = Signal(
                                signal_type=signal_type_bullish,
                                source=f"{self.indicator}_divergence_generator",
                                tickers=[ticker_signal],
                                metadata=self._enrich_metadata({
                                    "indicator": self.indicator,
                                    "price_low_1": recent_price_lows[0][1],
                                    "price_low_2": recent_price_lows[1][1],
                                    "indicator_low_1": recent_ind_lows[0][1],
                                    "indicator_low_2": recent_ind_lows[1][1]
                                })
                            )
                            signals.append(signal)
                
                # Check for bearish divergence (price higher high, indicator lower high)
                if len(price_highs) >= 2 and len(ind_highs) >= 2:
                    recent_price_highs = price_highs[-2:]
                    recent_ind_highs = ind_highs[-2:]
                    
                    # Price makes higher high
                    if recent_price_highs[1][1] > recent_price_highs[0][1]:
                        # Indicator makes lower high
                        if recent_ind_highs[1][1] < recent_ind_highs[0][1]:
                            logger.info(
                                "bearish_divergence_detected",
                                ticker=ticker,
                                indicator=self.indicator,
                                price_high_1=recent_price_highs[0][1],
                                price_high_2=recent_price_highs[1][1],
                                ind_high_1=recent_ind_highs[0][1],
                                ind_high_2=recent_ind_highs[1][1]
                            )
                            
                            ticker_signal = TickerSignal(
                                ticker=ticker,
                                signal=BiasType.BEARISH,
                                confidence=self.confidence * 100,
                                reasoning=(
                                    f"Bearish divergence: Price made higher high ({recent_price_highs[0][1]:.5f} → {recent_price_highs[1][1]:.5f}), "
                                    f"but {self.indicator.upper()} made lower high ({recent_ind_highs[0][1]:.2f} → {recent_ind_highs[1][1]:.2f}). "
                                    f"Strong reversal signal."
                                )
                            )
                            
                            signal = Signal(
                                signal_type=signal_type_bearish,
                                source=f"{self.indicator}_divergence_generator",
                                tickers=[ticker_signal],
                                metadata=self._enrich_metadata({
                                    "indicator": self.indicator,
                                    "price_high_1": recent_price_highs[0][1],
                                    "price_high_2": recent_price_highs[1][1],
                                    "indicator_high_1": recent_ind_highs[0][1],
                                    "indicator_high_2": recent_ind_highs[1][1]
                                })
                            )
                            signals.append(signal)
                
            except Exception as e:
                logger.error(
                    "momentum_divergence_error",
                    ticker=ticker,
                    error=str(e),
                    exc_info=True
                )
                continue
        
        logger.info(
            "momentum_divergence_scan_completed",
            signals_generated=len(signals),
            tickers_with_signal=[s.tickers[0].ticker for s in signals] if signals else []
        )
        
        return signals
