"""
Tests for Golden Cross Signal Generator
"""
import pytest
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.generators.golden_cross import GoldenCrossSignalGenerator
from app.schemas.signal import SignalType, BiasType


def create_mock_price_data(num_days: int = 300, golden_cross: bool = False):
    """
    Create mock price data for testing.
    
    Args:
        num_days: Number of days of data
        golden_cross: If True, create data with a golden cross pattern
        
    Returns:
        DataFrame with OHLCV data
    """
    dates = pd.date_range(
        end=datetime.utcnow(),
        periods=num_days,
        freq="D"
    )
    
    if golden_cross:
        # Create a clear golden cross: price rises steadily
        # Short SMA (50) will cross above long SMA (200)
        base_price = 100
        prices = [base_price + (i * 0.5) for i in range(num_days)]
    else:
        # Flat prices - no golden cross
        prices = [100] * num_days
    
    df = pd.DataFrame({
        "timestamp": dates,
        "open": prices,
        "high": [p * 1.01 for p in prices],
        "low": [p * 0.99 for p in prices],
        "close": prices,
        "volume": [1000000] * num_days
    })
    
    return df


@pytest.mark.asyncio
async def test_golden_cross_generator_creation():
    """Test creating a golden cross generator."""
    config = {
        "tickers": ["AAPL"],
        "sma_short": 50,
        "sma_long": 200,
        "timeframe": "D",
        "confidence": 0.85
    }
    
    generator = GoldenCrossSignalGenerator(config)
    
    assert generator.sma_short == 50
    assert generator.sma_long == 200
    assert generator.timeframe == "D"
    assert generator.confidence == 0.85


@pytest.mark.asyncio
async def test_golden_cross_config_validation():
    """Test that invalid config raises error."""
    # Short SMA >= Long SMA is invalid
    with pytest.raises(ValueError):
        GoldenCrossSignalGenerator({
            "sma_short": 200,
            "sma_long": 50
        })
    
    # Invalid confidence
    with pytest.raises(ValueError):
        GoldenCrossSignalGenerator({
            "sma_short": 50,
            "sma_long": 200,
            "confidence": 1.5
        })


@pytest.mark.asyncio
async def test_golden_cross_no_data():
    """Test that generator handles missing market data gracefully."""
    config = {
        "tickers": ["AAPL"],
        "sma_short": 50,
        "sma_long": 200
    }
    
    generator = GoldenCrossSignalGenerator(config)
    
    # Mock market data fetcher to return None
    with patch.object(
        generator.market_data,
        'fetch_candles',
        new_callable=AsyncMock,
        return_value=None
    ):
        signals = await generator.generate()
        
        # Should return empty list when no data available
        assert signals == []


@pytest.mark.asyncio
async def test_golden_cross_insufficient_data():
    """Test that generator handles insufficient data."""
    config = {
        "tickers": ["AAPL"],
        "sma_short": 50,
        "sma_long": 200
    }
    
    generator = GoldenCrossSignalGenerator(config)
    
    # Create data with only 100 days (need 200 for long SMA)
    insufficient_data = create_mock_price_data(num_days=100)
    
    with patch.object(
        generator.market_data,
        'fetch_candles',
        new_callable=AsyncMock,
        return_value=insufficient_data
    ):
        signals = await generator.generate()
        
        # Should return empty list
        assert signals == []


@pytest.mark.asyncio
async def test_golden_cross_detection():
    """Test that generator detects golden cross pattern."""
    config = {
        "tickers": ["AAPL"],
        "sma_short": 50,
        "sma_long": 200,
        "lookback_days": 5,
        "confidence": 0.85
    }
    
    generator = GoldenCrossSignalGenerator(config)
    
    # Create data with golden cross
    golden_cross_data = create_mock_price_data(num_days=300, golden_cross=True)
    
    with patch.object(
        generator.market_data,
        'fetch_candles',
        new_callable=AsyncMock,
        return_value=golden_cross_data
    ):
        signals = await generator.generate()
        
        # Should detect golden cross
        assert len(signals) > 0
        
        signal = signals[0]
        
        # Verify signal structure
        assert signal.signal_type == SignalType.GOLDEN_CROSS
        assert signal.source == "golden_cross_generator"
        assert signal.tickers == ["AAPL"]
        
        # Verify bias
        assert "AAPL" in signal.bias
        bias = signal.bias["AAPL"]
        assert bias.ticker == "AAPL"
        assert bias.bias == BiasType.BULLISH
        assert bias.confidence == 0.85
        assert "Golden cross" in bias.reasoning
        assert "50-day SMA" in bias.reasoning
        assert "200-day SMA" in bias.reasoning
        
        # Verify metadata
        assert signal.metadata["sma_short"] == 50
        assert signal.metadata["sma_long"] == 200
        assert signal.metadata["timeframe"] == "D"
        assert "current_sma_short" in signal.metadata
        assert "current_sma_long" in signal.metadata
        assert "current_price" in signal.metadata


@pytest.mark.asyncio
async def test_golden_cross_no_detection():
    """Test that generator does not emit signal without golden cross."""
    config = {
        "tickers": ["AAPL"],
        "sma_short": 50,
        "sma_long": 200
    }
    
    generator = GoldenCrossSignalGenerator(config)
    
    # Create flat data with no golden cross
    flat_data = create_mock_price_data(num_days=300, golden_cross=False)
    
    with patch.object(
        generator.market_data,
        'fetch_candles',
        new_callable=AsyncMock,
        return_value=flat_data
    ):
        signals = await generator.generate()
        
        # Should not detect golden cross
        assert signals == []


@pytest.mark.asyncio
async def test_golden_cross_multiple_tickers():
    """Test that generator can check multiple tickers."""
    config = {
        "tickers": ["AAPL", "MSFT", "GOOGL"],
        "sma_short": 50,
        "sma_long": 200
    }
    
    generator = GoldenCrossSignalGenerator(config)
    
    # Mock: AAPL has golden cross, MSFT and GOOGL don't
    golden_cross_data = create_mock_price_data(num_days=300, golden_cross=True)
    flat_data = create_mock_price_data(num_days=300, golden_cross=False)
    
    async def mock_fetch_candles(symbol, resolution, lookback_days):
        if symbol == "AAPL":
            return golden_cross_data
        else:
            return flat_data
    
    with patch.object(
        generator.market_data,
        'fetch_candles',
        side_effect=mock_fetch_candles
    ):
        signals = await generator.generate()
        
        # Should only generate signal for AAPL
        assert len(signals) == 1
        assert signals[0].tickers == ["AAPL"]


@pytest.mark.asyncio
async def test_golden_cross_error_handling():
    """Test that generator handles errors gracefully."""
    config = {
        "tickers": ["AAPL", "MSFT"],
        "sma_short": 50,
        "sma_long": 200
    }
    
    generator = GoldenCrossSignalGenerator(config)
    
    # Mock market data fetcher to raise exception for AAPL, return data for MSFT
    golden_cross_data = create_mock_price_data(num_days=300, golden_cross=True)
    
    async def mock_fetch_with_error(symbol, resolution, lookback_days):
        if symbol == "AAPL":
            raise Exception("API error")
        else:
            return golden_cross_data
    
    with patch.object(
        generator.market_data,
        'fetch_candles',
        side_effect=mock_fetch_with_error
    ):
        signals = await generator.generate()
        
        # Should still generate signal for MSFT, skip AAPL
        assert len(signals) == 1
        assert signals[0].tickers == ["MSFT"]

