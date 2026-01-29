"""
Signal Schema

Defines the structure of signals emitted by signal generators and consumed by pipelines.
"""
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, field_validator


class SignalType(str, Enum):
    """Types of signals that can be generated."""
    NEWS = "news"
    GOLDEN_CROSS = "golden_cross"
    DEATH_CROSS = "death_cross"
    RSI_OVERSOLD = "rsi_oversold"
    RSI_OVERBOUGHT = "rsi_overbought"
    MACD_BULLISH = "macd_bullish"
    MACD_BEARISH = "macd_bearish"
    VOLUME_SPIKE = "volume_spike"
    # Bollinger Bands
    BBANDS_UPPER_BREAKOUT = "bbands_upper_breakout"
    BBANDS_LOWER_BREAKOUT = "bbands_lower_breakout"
    BBANDS_UPPER_BOUNCE = "bbands_upper_bounce"
    BBANDS_LOWER_BOUNCE = "bbands_lower_bounce"
    # Stochastic
    STOCH_BULLISH = "stoch_bullish"
    STOCH_BEARISH = "stoch_bearish"
    # ADX
    ADX_STRONG_TREND = "adx_strong_trend"
    ADX_WEAK_TREND = "adx_weak_trend"
    # EMA Crossover
    EMA_BULLISH_CROSSOVER = "ema_bullish_crossover"
    EMA_BEARISH_CROSSOVER = "ema_bearish_crossover"
    # ATR
    ATR_VOLATILITY_SPIKE = "atr_volatility_spike"
    ATR_VOLATILITY_COMPRESSION = "atr_volatility_compression"
    # CCI
    CCI_OVERSOLD = "cci_oversold"
    CCI_OVERBOUGHT = "cci_overbought"
    CCI_BULLISH_ZERO_CROSS = "cci_bullish_zero_cross"
    CCI_BEARISH_ZERO_CROSS = "cci_bearish_zero_cross"
    # Stochastic RSI
    STOCHRSI_OVERSOLD = "stochrsi_oversold"
    STOCHRSI_OVERBOUGHT = "stochrsi_overbought"
    STOCHRSI_BULLISH_CROSS = "stochrsi_bullish_cross"
    STOCHRSI_BEARISH_CROSS = "stochrsi_bearish_cross"
    # Williams %R
    WILLR_OVERSOLD = "willr_oversold"
    WILLR_OVERBOUGHT = "willr_overbought"
    WILLR_BULLISH_MOMENTUM = "willr_bullish_momentum"
    WILLR_BEARISH_MOMENTUM = "willr_bearish_momentum"
    # AROON
    AROON_UPTREND = "aroon_uptrend"
    AROON_DOWNTREND = "aroon_downtrend"
    AROON_BULLISH_CROSS = "aroon_bullish_cross"
    AROON_BEARISH_CROSS = "aroon_bearish_cross"
    AROON_CONSOLIDATION = "aroon_consolidation"
    # MFI
    MFI_OVERSOLD = "mfi_oversold"
    MFI_OVERBOUGHT = "mfi_overbought"
    # OBV
    OBV_BULLISH_DIVERGENCE = "obv_bullish_divergence"
    OBV_BEARISH_DIVERGENCE = "obv_bearish_divergence"
    OBV_BULLISH_BREAKOUT = "obv_bullish_breakout"
    OBV_BEARISH_BREAKDOWN = "obv_bearish_breakdown"
    # SAR
    SAR_BULLISH_REVERSAL = "sar_bullish_reversal"
    SAR_BEARISH_REVERSAL = "sar_bearish_reversal"
    # 200 EMA Crossover
    EMA_200_BULLISH_CROSSOVER = "ema_200_bullish_crossover"
    EMA_200_BEARISH_CROSSOVER = "ema_200_bearish_crossover"
    # Swing Point Break
    SWING_POINT_BREAK_BULLISH = "swing_point_break_bullish"
    SWING_POINT_BREAK_BEARISH = "swing_point_break_bearish"
    # Momentum Divergence
    RSI_BULLISH_DIVERGENCE = "rsi_bullish_divergence"
    RSI_BEARISH_DIVERGENCE = "rsi_bearish_divergence"
    MACD_BULLISH_DIVERGENCE = "macd_bullish_divergence"
    MACD_BEARISH_DIVERGENCE = "macd_bearish_divergence"
    # Fair Value Gap
    FVG_BULLISH = "fvg_bullish"
    FVG_BEARISH = "fvg_bearish"
    # Liquidity Sweep
    LIQUIDITY_SWEEP_BULLISH = "liquidity_sweep_bullish"
    LIQUIDITY_SWEEP_BEARISH = "liquidity_sweep_bearish"
    # Break of Structure
    BREAK_OF_STRUCTURE_BULLISH = "break_of_structure_bullish"
    BREAK_OF_STRUCTURE_BEARISH = "break_of_structure_bearish"
    # Order Block
    ORDER_BLOCK_BULLISH = "order_block_bullish"
    ORDER_BLOCK_BEARISH = "order_block_bearish"
    # Change of Character
    CHOCH_BULLISH = "choch_bullish"
    CHOCH_BEARISH = "choch_bearish"
    # Volume Profile POC
    POC_BREAK_BULLISH = "poc_break_bullish"
    POC_BREAK_BEARISH = "poc_break_bearish"
    # Accumulation/Distribution
    ACCUMULATION_SIGNAL = "accumulation_signal"
    DISTRIBUTION_SIGNAL = "distribution_signal"
    # HTF Trend Alignment
    HTF_TREND_ALIGNED_BULLISH = "htf_trend_aligned_bullish"
    HTF_TREND_ALIGNED_BEARISH = "htf_trend_aligned_bearish"
    # Generic
    PRICE_LEVEL = "price_level"
    VOLATILITY = "volatility"
    EXTERNAL = "external"
    MOCK = "mock"


class BiasType(str, Enum):
    """Market bias direction."""
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class TickerSignal(BaseModel):
    """Signal information for a specific ticker."""
    ticker: str = Field(..., description="Stock symbol")
    signal: BiasType = Field(..., description="Signal direction (BULLISH/BEARISH/NEUTRAL)")
    confidence: float = Field(..., ge=0.0, le=100.0, description="Confidence level (0-100)")
    reasoning: Optional[str] = Field(None, description="Explanation for the signal")
    
    class Config:
        json_schema_extra = {
            "example": {
                "ticker": "AAPL",
                "signal": "BULLISH",
                "confidence": 85,
                "reasoning": "Golden cross detected on daily chart"
            }
        }


# Backwards compatibility alias
SignalBias = TickerSignal


class Signal(BaseModel):
    """
    Signal emitted by signal generators to trigger pipeline executions.
    
    Signals are published to Kafka and consumed by pipelines that match
    the tickers in their scanner configuration.
    """
    signal_id: UUID = Field(default_factory=uuid4, description="Unique signal identifier")
    signal_type: SignalType = Field(..., description="Type of signal")
    source: Optional[str] = Field(None, description="Signal generator source identifier")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Signal generation timestamp (UTC)"
    )
    tickers: List[TickerSignal] = Field(
        ..., 
        min_length=1, 
        description="List of ticker signals"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional signal-specific metadata"
    )
    
    @field_validator('tickers')
    @classmethod
    def validate_tickers(cls, v):
        """Ensure tickers have uppercase symbols."""
        if not v:
            raise ValueError("At least one ticker is required")
        # Normalize ticker symbols to uppercase
        for ticker_signal in v:
            ticker_signal.ticker = ticker_signal.ticker.upper().strip()
        return v
    
    def to_kafka_message(self) -> Dict[str, Any]:
        """
        Convert signal to Kafka message format (JSON-serializable).
        
        Returns:
            Dictionary ready for JSON serialization in flat structure
        """
        return {
            "signal_id": str(self.signal_id),
            "signal_type": self.signal_type.value,
            "source": self.source,
            "timestamp": int(self.timestamp.timestamp()),  # Unix timestamp
            "tickers": [
                {
                    "ticker": ts.ticker,
                    "signal": ts.signal.value,
                    "confidence": ts.confidence,
                    "reasoning": ts.reasoning
                }
                for ts in self.tickers
            ],
            "metadata": self.metadata
        }
    
    @classmethod
    def from_kafka_message(cls, data: Dict[str, Any]) -> 'Signal':
        """
        Create Signal from Kafka message.
        
        Args:
            data: Dictionary from Kafka JSON message
            
        Returns:
            Signal instance
        """
        return cls(
            signal_id=UUID(data['signal_id']) if isinstance(data.get('signal_id'), str) else data['signal_id'],
            signal_type=SignalType(data['signal_type']) if isinstance(data.get('signal_type'), str) else data['signal_type'],
            source=data.get('source'),
            timestamp=datetime.fromtimestamp(data['timestamp']) if isinstance(data.get('timestamp'), int) else data['timestamp'],
            tickers=[
                TickerSignal(
                    ticker=ts['ticker'],
                    signal=BiasType(ts['signal']) if isinstance(ts['signal'], str) else ts['signal'],
                    confidence=ts['confidence'],
                    reasoning=ts.get('reasoning')
                )
                for ts in data['tickers']
            ],
            metadata=data.get('metadata', {})
        )
    
    class Config:
        json_schema_extra = {
            "example": {
                "signal_id": "550e8400-e29b-41d4-a716-446655440000",
                "signal_type": "golden_cross",
                "source": "golden_cross_generator",
                "timestamp": 1733407800,
                "tickers": [
                    {
                        "ticker": "AAPL",
                        "signal": "BULLISH",
                        "confidence": 85,
                        "reasoning": "50-day SMA crossed above 200-day SMA"
                    },
                    {
                        "ticker": "MSFT",
                        "signal": "BULLISH",
                        "confidence": 78,
                        "reasoning": "50-day SMA crossed above 200-day SMA"
                    }
                ],
                "metadata": {
                    "sma_short": 50,
                    "sma_long": 200,
                    "timeframe": "1d"
                }
            }
        }

