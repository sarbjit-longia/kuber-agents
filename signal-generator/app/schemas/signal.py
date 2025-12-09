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

