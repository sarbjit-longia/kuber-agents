"""
Test Fixtures and Utilities

Shared fixtures and utilities for agent testing.
"""
import pytest
from uuid import uuid4
from datetime import datetime, timedelta
from typing import List

from app.schemas.pipeline_state import (
    PipelineState,
    MarketData,
    TimeframeData,
    BiasResult,
    StrategyResult,
)


@pytest.fixture
def mock_state():
    """Create a basic mock pipeline state."""
    state = PipelineState(
        execution_id=uuid4(),
        pipeline_id=uuid4(),
        user_id=uuid4(),
        symbol="AAPL",
        mode="paper",
        timeframes=["5m", "1d"]
    )
    return state


@pytest.fixture
def mock_market_data():
    """Create mock market data with multiple timeframes."""
    def _create_candles(timeframe: str, num_candles: int = 100, base_price: float = 250.0):
        """Generate realistic mock candles."""
        candles = []
        for i in range(num_candles):
            # Create realistic price movement with trend
            price_change = (i % 10 - 5) * 0.5  # Oscillating
            close = base_price + price_change + (i * 0.1)  # Uptrend
            
            candle = TimeframeData(
                timeframe=timeframe,
                timestamp=datetime.utcnow() - timedelta(minutes=(num_candles - i) * 5),
                open=close - 0.3,
                high=close + 0.5,
                low=close - 0.6,
                close=close,
                volume=1000000 + (i * 10000)
            )
            candles.append(candle)
        return candles
    
    return _create_candles


@pytest.fixture
def state_with_market_data(mock_state, mock_market_data):
    """Create a state with populated market data."""
    timeframes = {
        "5m": mock_market_data("5m", 100, 250.0),
        "1h": mock_market_data("1h", 100, 250.0),
        "1d": mock_market_data("1d", 100, 250.0),
    }
    
    latest_candle = timeframes["5m"][-1]
    mock_state.market_data = MarketData(
        symbol="AAPL",
        current_price=latest_candle.close,
        timeframes=timeframes,
        fetched_at=datetime.utcnow()
    )
    mock_state.timeframes = ["5m", "1h", "1d"]
    
    return mock_state


@pytest.fixture
def state_with_bias(state_with_market_data):
    """Create a state with bias already determined."""
    bias = BiasResult(
        bias="BULLISH",
        confidence=0.75,
        timeframe="1d",
        reasoning="Market showing strong upward momentum with RSI at 65.",
        key_factors=["RSI momentum", "Volume confirmation", "Trend strength"]
    )
    state_with_market_data.biases["1d"] = bias
    return state_with_market_data


@pytest.fixture
def state_with_strategy(state_with_bias):
    """Create a state with strategy already generated."""
    strategy = StrategyResult(
        action="BUY",
        entry_price=260.0,
        stop_loss=258.0,
        take_profit=264.0,
        confidence=0.80,
        pattern_detected="Bull Flag",
        reasoning="**MARKET STRUCTURE:** Clear uptrend with higher highs. **ENTRY RATIONALE:** Pullback to support."
    )
    state_with_bias.strategy = strategy
    return state_with_bias


def assert_reasoning_format(reasoning: str, required_sections: List[str] = None):
    """Assert that reasoning is properly formatted with expected sections."""
    if required_sections is None:
        required_sections = []
    
    # Check it's not empty
    assert reasoning, "Reasoning should not be empty"
    assert len(reasoning) > 50, f"Reasoning too short: {len(reasoning)} chars"
    
    # Check for proper formatting (no artifacts)
    assert "to=" not in reasoning, "Reasoning contains tool call artifacts"
    assert "json {" not in reasoning.lower(), "Reasoning contains JSON artifacts"
    assert "```" not in reasoning, "Reasoning contains code blocks"
    assert "commentary" not in reasoning.lower(), "Reasoning contains commentary artifacts"
    
    # Check for required sections if specified
    for section in required_sections:
        assert section.lower() in reasoning.lower(), f"Missing required section: {section}"


def assert_report_generated(state: PipelineState, agent_id: str):
    """Assert that a report was generated for the given agent."""
    assert hasattr(state, 'reports'), "State should have reports"
    assert agent_id in state.reports, f"No report found for agent {agent_id}"
    
    report = state.reports[agent_id]
    assert report.title, "Report should have a title"
    assert report.summary, "Report should have a summary"
    assert report.data, "Report should have data"
