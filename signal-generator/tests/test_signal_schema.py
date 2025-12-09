"""
Tests for Signal Schema
"""
from datetime import datetime
from uuid import UUID
import pytest

from app.schemas.signal import (
    Signal,
    SignalBias,
    SignalType,
    BiasType
)


def test_signal_bias_creation():
    """Test creating a SignalBias."""
    bias = SignalBias(
        ticker="AAPL",
        bias=BiasType.BULLISH,
        confidence=0.85,
        reasoning="Test reasoning"
    )
    
    assert bias.ticker == "AAPL"
    assert bias.bias == BiasType.BULLISH
    assert bias.confidence == 0.85
    assert bias.reasoning == "Test reasoning"


def test_signal_bias_confidence_validation():
    """Test that confidence must be between 0 and 1."""
    with pytest.raises(ValueError):
        SignalBias(
            ticker="AAPL",
            bias=BiasType.BULLISH,
            confidence=1.5  # Invalid
        )


def test_signal_creation():
    """Test creating a Signal."""
    bias = SignalBias(
        ticker="AAPL",
        bias=BiasType.BULLISH,
        confidence=0.85
    )
    
    signal = Signal(
        signal_type=SignalType.GOLDEN_CROSS,
        tickers=["AAPL"],
        bias={"AAPL": bias},
        metadata={"test": "data"},
        source="test_generator"
    )
    
    assert signal.signal_type == SignalType.GOLDEN_CROSS
    assert signal.tickers == ["AAPL"]
    assert "AAPL" in signal.bias
    assert signal.bias["AAPL"].bias == BiasType.BULLISH
    assert signal.metadata["test"] == "data"
    assert signal.source == "test_generator"
    assert isinstance(signal.signal_id, UUID)
    assert isinstance(signal.timestamp, datetime)


def test_signal_ticker_validation():
    """Test that tickers are required and normalized."""
    with pytest.raises(ValueError):
        Signal(
            signal_type=SignalType.MOCK,
            tickers=[],  # Empty list
            bias={}
        )
    
    # Test normalization (lowercase to uppercase)
    signal = Signal(
        signal_type=SignalType.MOCK,
        tickers=["aapl", "msft"],
        bias={}
    )
    assert signal.tickers == ["AAPL", "MSFT"]


def test_signal_to_kafka_message():
    """Test converting Signal to Kafka message format."""
    bias = SignalBias(
        ticker="AAPL",
        bias=BiasType.BULLISH,
        confidence=0.85,
        reasoning="Test"
    )
    
    signal = Signal(
        signal_type=SignalType.GOLDEN_CROSS,
        tickers=["AAPL"],
        bias={"AAPL": bias},
        metadata={"key": "value"}
    )
    
    message = signal.to_kafka_message()
    
    # Check that UUID is converted to string
    assert isinstance(message["signal_id"], str)
    
    # Check that timestamp is ISO format string
    assert isinstance(message["timestamp"], str)
    assert "T" in message["timestamp"]
    
    # Check that bias enum is converted to string
    assert message["bias"]["AAPL"]["bias"] == "BULLISH"
    
    # Check metadata is preserved
    assert message["metadata"]["key"] == "value"


def test_signal_from_kafka_message():
    """Test reconstructing Signal from Kafka message."""
    bias = SignalBias(
        ticker="AAPL",
        bias=BiasType.BULLISH,
        confidence=0.85
    )
    
    original_signal = Signal(
        signal_type=SignalType.GOLDEN_CROSS,
        tickers=["AAPL"],
        bias={"AAPL": bias}
    )
    
    # Convert to Kafka message
    message = original_signal.to_kafka_message()
    
    # Reconstruct from message
    reconstructed_signal = Signal.from_kafka_message(message)
    
    assert reconstructed_signal.signal_id == original_signal.signal_id
    assert reconstructed_signal.signal_type == original_signal.signal_type
    assert reconstructed_signal.tickers == original_signal.tickers
    assert reconstructed_signal.bias["AAPL"].bias == BiasType.BULLISH
    assert reconstructed_signal.bias["AAPL"].confidence == 0.85
    
    # Timestamps should be equal (within microseconds)
    assert abs((reconstructed_signal.timestamp - original_signal.timestamp).total_seconds()) < 0.001


def test_signal_roundtrip():
    """Test that Signal -> Kafka -> Signal roundtrip preserves data."""
    bias_aapl = SignalBias(
        ticker="AAPL",
        bias=BiasType.BULLISH,
        confidence=0.85,
        reasoning="Golden cross"
    )
    
    bias_msft = SignalBias(
        ticker="MSFT",
        bias=BiasType.BEARISH,
        confidence=0.72,
        reasoning="Death cross"
    )
    
    original = Signal(
        signal_type=SignalType.GOLDEN_CROSS,
        tickers=["AAPL", "MSFT"],
        bias={"AAPL": bias_aapl, "MSFT": bias_msft},
        metadata={"sma_short": 50, "sma_long": 200},
        source="test_generator"
    )
    
    # Roundtrip
    message = original.to_kafka_message()
    reconstructed = Signal.from_kafka_message(message)
    
    # Verify all fields
    assert reconstructed.signal_id == original.signal_id
    assert reconstructed.signal_type == original.signal_type
    assert reconstructed.tickers == original.tickers
    assert reconstructed.source == original.source
    assert reconstructed.metadata == original.metadata
    
    # Verify bias data
    assert reconstructed.bias["AAPL"].ticker == "AAPL"
    assert reconstructed.bias["AAPL"].bias == BiasType.BULLISH
    assert reconstructed.bias["AAPL"].confidence == 0.85
    assert reconstructed.bias["AAPL"].reasoning == "Golden cross"
    
    assert reconstructed.bias["MSFT"].ticker == "MSFT"
    assert reconstructed.bias["MSFT"].bias == BiasType.BEARISH
    assert reconstructed.bias["MSFT"].confidence == 0.72

