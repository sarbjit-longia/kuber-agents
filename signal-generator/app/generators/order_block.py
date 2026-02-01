"""
Order Block Signal Generator

Detects institutional order blocks (supply/demand zones).
"""
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class OrderBlockSignalGenerator(BaseSignalGenerator):
    """
    Order Block signal generator.
    
    Detects institutional supply/demand zones:
    - Bullish Order Block: Last bearish candle before strong bullish move
    - Bearish Order Block: Last bullish candle before strong bearish move
    
    These zones often act as support/resistance.
    
    Configuration:
        - tickers: List of tickers to monitor
        - lookback_periods: Periods to scan for order blocks (default: 30)
        - min_move_pips: Minimum move after order block (default: 20)
        - timeframe: Candle resolution (default: "60")
        - confidence: Confidence level (default: 0.80)
    
    Example config:
        {
            "tickers": ["EUR_USD", "GBP_USD"],
            "lookback_periods": 30,
            "min_move_pips": 20,
            "timeframe": "60",
            "confidence": 0.80
        }
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_data = MarketDataFetcher()
        self.lookback_periods = self.config.get("lookback_periods", 30)
        self.min_move_pips = self.config.get("min_move_pips", 20)
        self.timeframe = self.config.get("timeframe", "60")
        self.confidence = self.config.get("confidence", 0.80)
    
    def _validate_config(self):
        """Validate order block configuration."""
        lookback = self.config.get("lookback_periods", 30)
        if lookback < 10:
            raise ValueError(f"lookback_periods should be >= 10, got {lookback}")
    
    def _calculate_pip_value(self, symbol: str) -> float:
        """Calculate pip value for the symbol."""
        if "JPY" in symbol.upper():
            return 0.01
        return 0.0001
    
    async def generate(self) -> List[Signal]:
        """Generate order block signals."""
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "order_block_scan_started",
            tickers=tickers,
            lookback_periods=self.lookback_periods,
            min_move_pips=self.min_move_pips
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
                min_move_price = self.min_move_pips * pip_value
                
                # Look for bullish order blocks (last red candle before big green move)
                for i in range(len(candles) - 5, 5, -1):
                    current = candles[i]
                    
                    # Check if current candle is bearish
                    if current["c"] >= current["o"]:
                        continue
                    
                    # Check for strong bullish move in next 1-3 candles
                    max_high = max([candles[j]["h"] for j in range(i+1, min(i+4, len(candles)))])
                    move_size = max_high - current["l"]
                    
                    if move_size >= min_move_price:
                        # Bullish order block detected
                        current_price = candles[-1]["c"]
                        
                        # Signal when price returns to order block zone
                        if abs(current_price - current["l"]) <= (min_move_price * 0.5):
                            bars_ago = len(candles) - i - 1
                            move_pips = move_size / pip_value
                            
                            logger.info(
                                "bullish_order_block_detected",
                                ticker=ticker,
                                order_block_low=current["l"],
                                order_block_high=current["h"],
                                current_price=current_price,
                                move_pips=move_pips,
                                bars_ago=bars_ago
                            )
                            
                            ticker_signal = TickerSignal(
                                ticker=ticker,
                                signal=BiasType.BULLISH,
                                confidence=self.confidence * 100,
                                reasoning=(
                                    f"Bullish Order Block: Price returned to demand zone "
                                    f"({current['l']:.5f} - {current['h']:.5f}) from {bars_ago} bars ago. "
                                    f"Previous move: {move_pips:.1f} pips. "
                                    f"Institutional buying expected."
                                )
                            )
                            
                            signal = Signal(
                                signal_type=SignalType.ORDER_BLOCK_BULLISH,
                                source="order_block_generator",
                                tickers=[ticker_signal],
                                metadata=self._enrich_metadata({
                                    "order_block_low": current["l"],
                                    "order_block_high": current["h"],
                                    "current_price": current_price,
                                    "move_pips": move_pips,
                                    "bars_ago": bars_ago
                                })
                            )
                            signals.append(signal)
                            break  # Only one signal per ticker per scan
                
                # Look for bearish order blocks (last green candle before big red move)
                for i in range(len(candles) - 5, 5, -1):
                    current = candles[i]
                    
                    # Check if current candle is bullish
                    if current["c"] <= current["o"]:
                        continue
                    
                    # Check for strong bearish move in next 1-3 candles
                    min_low = min([candles[j]["l"] for j in range(i+1, min(i+4, len(candles)))])
                    move_size = current["h"] - min_low
                    
                    if move_size >= min_move_price:
                        # Bearish order block detected
                        current_price = candles[-1]["c"]
                        
                        # Signal when price returns to order block zone
                        if abs(current_price - current["h"]) <= (min_move_price * 0.5):
                            bars_ago = len(candles) - i - 1
                            move_pips = move_size / pip_value
                            
                            logger.info(
                                "bearish_order_block_detected",
                                ticker=ticker,
                                order_block_low=current["l"],
                                order_block_high=current["h"],
                                current_price=current_price,
                                move_pips=move_pips,
                                bars_ago=bars_ago
                            )
                            
                            ticker_signal = TickerSignal(
                                ticker=ticker,
                                signal=BiasType.BEARISH,
                                confidence=self.confidence * 100,
                                reasoning=(
                                    f"Bearish Order Block: Price returned to supply zone "
                                    f"({current['l']:.5f} - {current['h']:.5f}) from {bars_ago} bars ago. "
                                    f"Previous move: {move_pips:.1f} pips. "
                                    f"Institutional selling expected."
                                )
                            )
                            
                            signal = Signal(
                                signal_type=SignalType.ORDER_BLOCK_BEARISH,
                                source="order_block_generator",
                                tickers=[ticker_signal],
                                metadata=self._enrich_metadata({
                                    "order_block_low": current["l"],
                                    "order_block_high": current["h"],
                                    "current_price": current_price,
                                    "move_pips": move_pips,
                                    "bars_ago": bars_ago
                                })
                            )
                            signals.append(signal)
                            break  # Only one signal per ticker per scan
                
            except Exception as e:
                logger.error(
                    "order_block_error",
                    ticker=ticker,
                    error=str(e),
                    exc_info=True
                )
                continue
        
        logger.info(
            "order_block_scan_completed",
            signals_generated=len(signals),
            tickers_with_signal=[s.tickers[0].ticker for s in signals] if signals else []
        )
        
        return signals
