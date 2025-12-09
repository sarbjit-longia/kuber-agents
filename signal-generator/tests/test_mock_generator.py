"""
Tests for Mock Signal Generator
"""
import pytest

from app.generators.mock import MockSignalGenerator
from app.schemas.signal import SignalType, BiasType


@pytest.mark.asyncio
async def test_mock_generator_creation():
    """Test creating a mock generator."""
    config = {
        "tickers": ["AAPL", "MSFT"],
        "emission_probability": 0.5,
        "bias_options": [BiasType.BULLISH]
    }
    
    generator = MockSignalGenerator(config)
    
    assert generator.config == config
    assert generator.generator_type == "mocksignal"


@pytest.mark.asyncio
async def test_mock_generator_config_validation():
    """Test that invalid config raises error."""
    with pytest.raises(ValueError):
        MockSignalGenerator({
            "emission_probability": 1.5  # Invalid, must be 0-1
        })


@pytest.mark.asyncio
async def test_mock_generator_no_emission():
    """Test that generator may not emit signals based on probability."""
    config = {
        "tickers": ["AAPL"],
        "emission_probability": 0.0  # Never emit
    }
    
    generator = MockSignalGenerator(config)
    
    # Run multiple times, should never emit
    for _ in range(10):
        signals = await generator.generate()
        assert signals == []


@pytest.mark.asyncio
async def test_mock_generator_always_emit():
    """Test that generator emits signals with high probability."""
    config = {
        "tickers": ["AAPL", "MSFT", "GOOGL"],
        "emission_probability": 1.0,  # Always emit
        "bias_options": [BiasType.BULLISH, BiasType.BEARISH]
    }
    
    generator = MockSignalGenerator(config)
    
    signals = await generator.generate()
    
    # Should emit at least one signal
    assert len(signals) > 0
    
    signal = signals[0]
    
    # Verify signal structure
    assert signal.signal_type == SignalType.MOCK
    assert signal.source == "mock_generator"
    assert len(signal.tickers) >= 1
    assert len(signal.tickers) <= 3  # Max 3 tickers per signal
    
    # Verify all tickers have bias
    for ticker in signal.tickers:
        assert ticker in signal.bias
        assert signal.bias[ticker].ticker == ticker
        assert signal.bias[ticker].bias in [BiasType.BULLISH, BiasType.BEARISH]
        assert 0.6 <= signal.bias[ticker].confidence <= 0.95
        assert "Mock signal" in signal.bias[ticker].reasoning
    
    # Verify metadata
    assert signal.metadata["generator"] == "mock"
    assert signal.metadata["emission_probability"] == 1.0


@pytest.mark.asyncio
async def test_mock_generator_bias_options():
    """Test that generator respects bias_options config."""
    config = {
        "tickers": ["AAPL"],
        "emission_probability": 1.0,
        "bias_options": [BiasType.BULLISH]  # Only BULLISH
    }
    
    generator = MockSignalGenerator(config)
    
    # Generate multiple signals to test randomness
    for _ in range(5):
        signals = await generator.generate()
        if signals:
            signal = signals[0]
            # All biases should be BULLISH
            for bias in signal.bias.values():
                assert bias.bias == BiasType.BULLISH


@pytest.mark.asyncio
async def test_mock_generator_default_config():
    """Test generator with default configuration."""
    generator = MockSignalGenerator({})
    
    # Should not raise errors
    signals = await generator.generate()
    
    # May or may not emit based on default probability
    assert isinstance(signals, list)

