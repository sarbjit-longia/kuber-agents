"""
Bollinger Bands Signal Generator

Monitors for Bollinger Bands breakouts and bounces.
"""
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType
from app.utils.market_data import MarketDataFetcher


logger = structlog.get_logger()


class BollingerBandsSignalGenerator(BaseSignalGenerator):
    """
    Bollinger Bands signal generator.
    
    Monitors a watchlist of tickers for Bollinger Bands signals:
    - Price breaks above upper band: BULLISH breakout signal
    - Price breaks below lower band: BEARISH breakdown signal
    - Price bounces off bands: Mean reversion signals
    
    Configuration:
        - tickers: List of tickers to monitor
        - timeperiod: BB period (default: 20)
        - nbdevup: Upper band standard deviations (default: 2)
        - nbdevdn: Lower band standard deviations (default: 2)
        - timeframe: Candle resolution (default: "D" for daily)
        - confidence: Confidence level (default: 0.75)
        - signal_type: "breakout" or "bounce" (default: "breakout")
    
    Example config:
        {
            "tickers": ["AAPL", "MSFT", "GOOGL"],
            "timeperiod": 20,
            "nbdevup": 2,
            "nbdevdn": 2,
            "timeframe": "D",
            "confidence": 0.75,
            "signal_type": "breakout"
        }
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_data = MarketDataFetcher()
        self.timeperiod = self.config.get("timeperiod", 20)
        self.nbdevup = self.config.get("nbdevup", 2)
        self.nbdevdn = self.config.get("nbdevdn", 2)
        self.timeframe = self.config.get("timeframe", "D")
        self.confidence = self.config.get("confidence", 0.75)
        self.signal_type_mode = self.config.get("signal_type", "breakout")
    
    def _validate_config(self):
        """Validate Bollinger Bands generator configuration."""
        timeperiod = self.config.get("timeperiod", 20)
        if timeperiod < 2:
            raise ValueError(f"timeperiod must be >= 2, got {timeperiod}")
        
        confidence = self.config.get("confidence", 0.75)
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        
        signal_type = self.config.get("signal_type", "breakout")
        if signal_type not in ["breakout", "bounce"]:
            raise ValueError(f"signal_type must be 'breakout' or 'bounce', got {signal_type}")
    
    async def generate(self) -> List[Signal]:
        """
        Check for Bollinger Bands signals and generate signals.
        
        Returns:
            List of Signal objects for tickers with BB signals
        """
        tickers = self.config.get("tickers", ["AAPL"])
        signals = []
        
        logger.info(
            "bollinger_bands_scan_started",
            tickers=tickers,
            timeperiod=self.timeperiod,
            signal_type=self.signal_type_mode
        )
        
        for ticker in tickers:
            try:
                # Fetch Bollinger Bands from Finnhub
                lookback_days = 90
                bb_data = await self.market_data.fetch_indicator(
                    symbol=ticker,
                    indicator="bbands",
                    resolution=self.timeframe,
                    lookback_days=lookback_days,
                    timeperiod=self.timeperiod,
                    nbdevup=self.nbdevup,
                    nbdevdn=self.nbdevdn,
                    seriestype="c"
                )
                
                if not bb_data or "upperband" not in bb_data or "lowerband" not in bb_data:
                    logger.warning(
                        "bollinger_bands_data_unavailable",
                        ticker=ticker
                    )
                    continue
                
                upper_band = bb_data["upperband"]
                middle_band = bb_data.get("middleband", [])
                lower_band = bb_data["lowerband"]
                close_prices = bb_data.get("c", [])
                
                if len(upper_band) < 2 or len(lower_band) < 2 or len(close_prices) < 2:
                    logger.warning(
                        "insufficient_bb_data",
                        ticker=ticker,
                        available=len(upper_band)
                    )
                    continue
                
                current_price = close_prices[-1]
                previous_price = close_prices[-2]
                current_upper = upper_band[-1]
                current_lower = lower_band[-1]
                current_middle = middle_band[-1] if middle_band else (current_upper + current_lower) / 2
                previous_upper = upper_band[-2]
                previous_lower = lower_band[-2]
                
                # Calculate band width for context
                band_width = ((current_upper - current_lower) / current_middle) * 100
                
                # Breakout signals
                if self.signal_type_mode == "breakout":
                    # Upper band breakout (BULLISH)
                    if current_price > current_upper and previous_price <= previous_upper:
                        ticker_signal = TickerSignal(
                            ticker=ticker,
                            signal=BiasType.BULLISH,
                            confidence=self.confidence * 100,
                            reasoning=(
                                f"Bollinger Bands upper breakout: Price ${current_price:.2f} "
                                f"broke above upper band ${current_upper:.2f}. Band width: {band_width:.1f}%"
                            )
                        )
                        
                        signal = Signal(
                            signal_type=SignalType.BBANDS_UPPER_BREAKOUT,
                            source="bollinger_bands_generator",
                            tickers=[ticker_signal],
                            metadata=self._enrich_metadata({
                                "timeperiod": self.timeperiod,
                                "current_price": round(current_price, 2),
                                "upper_band": round(current_upper, 2),
                                "middle_band": round(current_middle, 2),
                                "lower_band": round(current_lower, 2),
                                "band_width_pct": round(band_width, 2),
                                "timeframe": self.timeframe
                            })
                        )
                        
                        signals.append(signal)
                        logger.info("bbands_upper_breakout_signal", ticker=ticker, price=round(current_price, 2))
                    
                    # Lower band breakdown (BEARISH)
                    elif current_price < current_lower and previous_price >= previous_lower:
                        ticker_signal = TickerSignal(
                            ticker=ticker,
                            signal=BiasType.BEARISH,
                            confidence=self.confidence * 100,
                            reasoning=(
                                f"Bollinger Bands lower breakdown: Price ${current_price:.2f} "
                                f"broke below lower band ${current_lower:.2f}. Band width: {band_width:.1f}%"
                            )
                        )
                        
                        signal = Signal(
                            signal_type=SignalType.BBANDS_LOWER_BREAKOUT,
                            source="bollinger_bands_generator",
                            tickers=[ticker_signal],
                            metadata=self._enrich_metadata({
                                "timeperiod": self.timeperiod,
                                "current_price": round(current_price, 2),
                                "upper_band": round(current_upper, 2),
                                "middle_band": round(current_middle, 2),
                                "lower_band": round(current_lower, 2),
                                "band_width_pct": round(band_width, 2),
                                "timeframe": self.timeframe
                            })
                        )
                        
                        signals.append(signal)
                        logger.info("bbands_lower_breakout_signal", ticker=ticker, price=round(current_price, 2))
                
                # Bounce signals (mean reversion)
                elif self.signal_type_mode == "bounce":
                    # Bounce off lower band (BULLISH)
                    if previous_price <= previous_lower and current_price > current_lower:
                        ticker_signal = TickerSignal(
                            ticker=ticker,
                            signal=BiasType.BULLISH,
                            confidence=self.confidence * 100,
                            reasoning=(
                                f"Bollinger Bands lower bounce: Price ${current_price:.2f} "
                                f"bounced off lower band ${current_lower:.2f}"
                            )
                        )
                        
                        signal = Signal(
                            signal_type=SignalType.BBANDS_LOWER_BOUNCE,
                            source="bollinger_bands_generator",
                            tickers=[ticker_signal],
                            metadata=self._enrich_metadata({
                                "timeperiod": self.timeperiod,
                                "current_price": round(current_price, 2),
                                "upper_band": round(current_upper, 2),
                                "middle_band": round(current_middle, 2),
                                "lower_band": round(current_lower, 2),
                                "band_width_pct": round(band_width, 2),
                                "timeframe": self.timeframe
                            })
                        )
                        
                        signals.append(signal)
                        logger.info("bbands_lower_bounce_signal", ticker=ticker, price=round(current_price, 2))
                    
                    # Bounce off upper band (BEARISH)
                    elif previous_price >= previous_upper and current_price < current_upper:
                        ticker_signal = TickerSignal(
                            ticker=ticker,
                            signal=BiasType.BEARISH,
                            confidence=self.confidence * 100,
                            reasoning=(
                                f"Bollinger Bands upper bounce: Price ${current_price:.2f} "
                                f"bounced off upper band ${current_upper:.2f}"
                            )
                        )
                        
                        signal = Signal(
                            signal_type=SignalType.BBANDS_UPPER_BOUNCE,
                            source="bollinger_bands_generator",
                            tickers=[ticker_signal],
                            metadata=self._enrich_metadata({
                                "timeperiod": self.timeperiod,
                                "current_price": round(current_price, 2),
                                "upper_band": round(current_upper, 2),
                                "middle_band": round(current_middle, 2),
                                "lower_band": round(current_lower, 2),
                                "band_width_pct": round(band_width, 2),
                                "timeframe": self.timeframe
                            })
                        )
                        
                        signals.append(signal)
                        logger.info("bbands_upper_bounce_signal", ticker=ticker, price=round(current_price, 2))
            
            except Exception as e:
                logger.error(
                    "bollinger_bands_check_failed",
                    ticker=ticker,
                    error=str(e),
                    exc_info=True
                )
                continue
        
        logger.info(
            "bollinger_bands_scan_completed",
            signals_generated=len(signals)
        )
        
        return signals

