"""
Liquidity Sweep Signal Generator

Detects when price sweeps liquidity zones (stop hunts) and reverses.
"""
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class LiquiditySweepSignalGenerator(BaseSignalGenerator):
    """
    Liquidity Sweep signal generator.
    
    Detects stop hunts where price:
    1. Breaks above/below a significant level (swing high/low)
    2. Quickly reverses back inside the range
    
    This indicates institutional liquidity grab before real move.
    
    Configuration:
        - tickers: List of tickers to monitor
        - lookback_periods: Periods to identify swing points (default: 20)
        - sweep_tolerance_pips: Pips beyond level for sweep (default: 5)
        - timeframe: Candle resolution (default: "60")
        - confidence: Confidence level (default: 0.85)
    
    Example config:
        {
            "tickers": ["EUR_USD", "GBP_USD"],
            "lookback_periods": 20,
            "sweep_tolerance_pips": 5,
            "timeframe": "60",
            "confidence": 0.85
        }
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_data = MarketDataFetcher()
        self.lookback_periods = self.config.get("lookback_periods", 20)
        self.sweep_tolerance_pips = self.config.get("sweep_tolerance_pips", 5)
        self.timeframe = self.config.get("timeframe", "60")
        self.confidence = self.config.get("confidence", 0.85)
    
    def _validate_config(self):
        """Validate liquidity sweep configuration."""
        lookback = self.config.get("lookback_periods", 20)
        if lookback < 10:
            raise ValueError(f"lookback_periods should be >= 10, got {lookback}")
    
    def _calculate_pip_value(self, symbol: str) -> float:
        """Calculate pip value for the symbol."""
        if "JPY" in symbol.upper():
            return 0.01
        return 0.0001
    
    def _find_recent_swing_points(self, highs: List[float], lows: List[float], window: int = 3) -> tuple:
        """Find most recent swing high and low."""
        swing_high = None
        swing_low = None
        swing_high_idx = None
        swing_low_idx = None
        
        for i in range(len(highs) - window - 1, window, -1):
            # Check for swing high
            if swing_high is None:
                is_high = all(highs[i] >= highs[i-j] for j in range(1, window+1)) and \
                         all(highs[i] >= highs[i+j] for j in range(1, window+1))
                if is_high:
                    swing_high = highs[i]
                    swing_high_idx = i
            
            # Check for swing low
            if swing_low is None:
                is_low = all(lows[i] <= lows[i-j] for j in range(1, window+1)) and \
                        all(lows[i] <= lows[i+j] for j in range(1, window+1))
                if is_low:
                    swing_low = lows[i]
                    swing_low_idx = i
            
            if swing_high is not None and swing_low is not None:
                break
        
        return swing_high, swing_low, swing_high_idx, swing_low_idx
    
    async def generate(self) -> List[Signal]:
        """Generate liquidity sweep signals."""
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "liquidity_sweep_scan_started",
            tickers=tickers,
            lookback_periods=self.lookback_periods,
            sweep_tolerance=self.sweep_tolerance_pips
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
                
                pip_value = self._calculate_pip_value(ticker)
                sweep_distance = self.sweep_tolerance_pips * pip_value
                
                highs = [c["h"] for c in candles]
                lows = [c["l"] for c in candles]
                closes = [c["c"] for c in candles]
                
                # Find recent swing points
                swing_high, swing_low, sh_idx, sl_idx = self._find_recent_swing_points(
                    highs, lows, window=3
                )
                
                if swing_high is None and swing_low is None:
                    continue
                
                # Check last 2 candles for sweep
                prev_candle = candles[-2]
                curr_candle = candles[-1]
                
                # Bullish liquidity sweep: Price swept below swing low, then closed back above
                if swing_low is not None:
                    swept_low = prev_candle["l"] < (swing_low - sweep_distance)
                    closed_inside = curr_candle["c"] > swing_low
                    
                    if swept_low and closed_inside:
                        bars_since_swing = len(lows) - sl_idx - 1
                        sweep_pips = (swing_low - prev_candle["l"]) / pip_value
                        
                        logger.info(
                            "bullish_liquidity_sweep_detected",
                            ticker=ticker,
                            swing_low=swing_low,
                            sweep_low=prev_candle["l"],
                            current_close=curr_candle["c"],
                            sweep_pips=sweep_pips,
                            bars_since_swing=bars_since_swing
                        )
                        
                        ticker_signal = TickerSignal(
                            ticker=ticker,
                            signal=BiasType.BULLISH,
                            confidence=self.confidence * 100,
                            reasoning=(
                                f"Bullish liquidity sweep: Price swept {sweep_pips:.1f} pips below "
                                f"swing low at {swing_low:.5f} ({bars_since_swing} bars ago), "
                                f"then reversed to close at {curr_candle['c']:.5f}. "
                                f"Institutional stop hunt completed."
                            )
                        )
                        
                        signal = Signal(
                            signal_type=SignalType.LIQUIDITY_SWEEP_BULLISH,
                            source="liquidity_sweep_generator",
                            tickers=[ticker_signal],
                            metadata=self._enrich_metadata({
                                "swing_low": swing_low,
                                "sweep_low": prev_candle["l"],
                                "current_close": curr_candle["c"],
                                "sweep_pips": sweep_pips,
                                "bars_since_swing": bars_since_swing
                            })
                        )
                        signals.append(signal)
                
                # Bearish liquidity sweep: Price swept above swing high, then closed back below
                if swing_high is not None:
                    swept_high = prev_candle["h"] > (swing_high + sweep_distance)
                    closed_inside = curr_candle["c"] < swing_high
                    
                    if swept_high and closed_inside:
                        bars_since_swing = len(highs) - sh_idx - 1
                        sweep_pips = (prev_candle["h"] - swing_high) / pip_value
                        
                        logger.info(
                            "bearish_liquidity_sweep_detected",
                            ticker=ticker,
                            swing_high=swing_high,
                            sweep_high=prev_candle["h"],
                            current_close=curr_candle["c"],
                            sweep_pips=sweep_pips,
                            bars_since_swing=bars_since_swing
                        )
                        
                        ticker_signal = TickerSignal(
                            ticker=ticker,
                            signal=BiasType.BEARISH,
                            confidence=self.confidence * 100,
                            reasoning=(
                                f"Bearish liquidity sweep: Price swept {sweep_pips:.1f} pips above "
                                f"swing high at {swing_high:.5f} ({bars_since_swing} bars ago), "
                                f"then reversed to close at {curr_candle['c']:.5f}. "
                                f"Institutional stop hunt completed."
                            )
                        )
                        
                        signal = Signal(
                            signal_type=SignalType.LIQUIDITY_SWEEP_BEARISH,
                            source="liquidity_sweep_generator",
                            tickers=[ticker_signal],
                            metadata=self._enrich_metadata({
                                "swing_high": swing_high,
                                "sweep_high": prev_candle["h"],
                                "current_close": curr_candle["c"],
                                "sweep_pips": sweep_pips,
                                "bars_since_swing": bars_since_swing
                            })
                        )
                        signals.append(signal)
                
            except Exception as e:
                logger.error(
                    "liquidity_sweep_error",
                    ticker=ticker,
                    error=str(e),
                    exc_info=True
                )
                continue
        
        logger.info(
            "liquidity_sweep_scan_completed",
            signals_generated=len(signals),
            tickers_with_signal=[s.tickers[0].ticker for s in signals] if signals else []
        )
        
        return signals
