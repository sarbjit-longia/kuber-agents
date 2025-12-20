"""
Test Fixtures and Utilities

Shared fixtures and utilities for agent testing.
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
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


def print_test_details(test_name: str, config: dict, result, expected: dict = None):
    """
    Print detailed test information for debugging.
    
    Use pytest -s flag to see this output.
    
    Args:
        test_name: Name of the test
        config: Agent configuration (instructions, model, etc.)
        result: Agent result (bias, strategy, etc.)
        expected: Expected values to check against
    """
    print("\n" + "="*80)
    print(f"TEST: {test_name}")
    print("="*80)
    
    # Print Input
    print("\n📋 INPUT:")
    print("-"*80)
    print(f"Instructions: {config.get('instructions', 'N/A')}")
    print(f"Model: {config.get('model', 'N/A')}")
    if 'strategy_timeframe' in config:
        print(f"Timeframe: {config.get('strategy_timeframe')}")
    
    # Print LLM Output
    print("\n🤖 LLM OUTPUT:")
    print("-"*80)
    if hasattr(result, 'biases') and result.biases:
        for tf, bias in result.biases.items():
            print(f"\n[{tf}] Bias: {bias.bias}")
            print(f"[{tf}] Confidence: {bias.confidence:.0%}")
            print(f"[{tf}] Reasoning:\n{bias.reasoning[:500]}..." if len(bias.reasoning) > 500 else f"[{tf}] Reasoning:\n{bias.reasoning}")
            if bias.key_factors:
                print(f"[{tf}] Key Factors: {', '.join(bias.key_factors)}")
    
    if hasattr(result, 'strategy') and result.strategy:
        strategy = result.strategy
        print(f"\nAction: {strategy.action}")
        print(f"Entry: ${strategy.entry_price:.2f}")
        print(f"Stop Loss: ${strategy.stop_loss:.2f}")
        print(f"Take Profit: ${strategy.take_profit:.2f}")
        print(f"Confidence: {strategy.confidence:.0%}")
        if strategy.pattern_detected:
            print(f"Pattern: {strategy.pattern_detected}")
        print(f"\nReasoning:\n{strategy.reasoning[:500]}..." if len(strategy.reasoning) > 500 else f"\nReasoning:\n{strategy.reasoning}")
    
    if hasattr(result, 'risk_assessment') and result.risk_assessment:
        risk = result.risk_assessment
        print(f"\nApproved: {risk.approved}")
        print(f"Position Size: {risk.position_size}")
        print(f"Risk Amount: ${risk.risk_amount:.2f}")
        print(f"\nReasoning:\n{risk.reasoning[:500]}..." if len(risk.reasoning) > 500 else f"\nReasoning:\n{risk.reasoning}")
    
    # Print Expected vs Actual
    if expected:
        print("\n✅ EXPECTED vs ❓ ACTUAL:")
        print("-"*80)
        for key, expected_value in expected.items():
            actual_value = "N/A"
            
            if hasattr(result, 'biases') and result.biases:
                bias = list(result.biases.values())[0]
                if key == 'bias':
                    actual_value = bias.bias
                elif key == 'confidence_min':
                    actual_value = f"{bias.confidence:.0%}"
                elif key == 'reasoning_contains':
                    actual_value = f"Contains '{expected_value}': {expected_value in bias.reasoning}"
                elif key == 'reasoning_not_contains':
                    actual_value = f"NOT Contains '{expected_value}': {expected_value not in bias.reasoning}"
            
            if hasattr(result, 'strategy') and result.strategy:
                strategy = result.strategy
                if key == 'action':
                    actual_value = strategy.action
                elif key == 'has_entry':
                    actual_value = f"Entry: ${strategy.entry_price:.2f}"
            
            # Determine if it matches
            match_symbol = "✅" if str(actual_value) == str(expected_value) or "True" in str(actual_value) else "❓"
            print(f"{match_symbol} {key}: Expected={expected_value}, Actual={actual_value}")
    
    print("\n" + "="*80 + "\n")


# Add pytest option to enable verbose test output
def pytest_addoption(parser):
    """Add custom pytest options."""
    parser.addoption(
        "--test-verbose",
        action="store_true",
        default=False,
        help="Show detailed test output (instructions, LLM output, expected vs actual)"
    )


# ============================================================================
# MOCKING FIXTURES - Make tests predictable and fast
# ============================================================================

@pytest.fixture
def mock_indicator_tools(monkeypatch):
    """
    Mock IndicatorTools to return predictable fake data.
    
    This prevents tests from making real API calls to Data Plane/Finnhub.
    Returns realistic but consistent indicator values.
    """
    class MockIndicatorTools:
        def __init__(self, ticker: str):
            self.ticker = ticker
        
        async def get_rsi(self, timeframe: str = "1h", period: int = 14):
            """Return fake but realistic RSI values."""
            # Simulate different RSI values based on timeframe for variety
            rsi_values = {
                "5m": 52.3,
                "15m": 48.7,
                "1h": 45.2,
                "4h": 58.6,
                "1d": 42.8
            }
            current_rsi = rsi_values.get(timeframe, 50.0)
            
            return {
                "ticker": self.ticker,
                "timeframe": timeframe,
                "period": period,
                "current_rsi": current_rsi,
                "previous_rsi": current_rsi - 2.5,  # Slight decrease
                "trend": "neutral"
            }
        
        async def get_macd(self, timeframe: str = "1h"):
            """Return fake but realistic MACD values."""
            macd_values = {
                "5m": {"macd": 0.8, "signal": 0.6, "histogram": 0.2},
                "1h": {"macd": -0.3, "signal": -0.1, "histogram": -0.2},
                "1d": {"macd": 1.2, "signal": 0.9, "histogram": 0.3}
            }
            values = macd_values.get(timeframe, {"macd": 0.0, "signal": 0.0, "histogram": 0.0})
            
            return {
                "ticker": self.ticker,
                "timeframe": timeframe,
                "macd": values["macd"],
                "signal": values["signal"],
                "histogram": values["histogram"],
                "crossover": "bullish" if values["histogram"] > 0 else "bearish"
            }
        
        async def get_sma(self, timeframe: str = "1h", period: int = 20):
            """Return fake SMA values."""
            return {
                "ticker": self.ticker,
                "timeframe": timeframe,
                "period": period,
                "sma": 255.0,
                "current_price": 258.0,
                "position": "above"
            }
    
    # Patch IndicatorTools class
    monkeypatch.setattr(
        "app.tools.strategy_tools.indicator_tools.IndicatorTools",
        MockIndicatorTools
    )
    
    return MockIndicatorTools


@pytest.fixture
def mock_rsi_tool(monkeypatch, mock_indicator_tools):
    """
    Mock RSI tool to return predictable output without calling Data Plane.
    
    This makes RSI tool tests fast and deterministic.
    """
    def mock_run(self, timeframe="1h", period=14, threshold_oversold=30, threshold_overbought=70):
        """Mocked RSI calculation."""
        # Use predictable RSI values based on timeframe
        rsi_values = {
            "5m": 52.3,
            "15m": 48.7,
            "1h": 45.2,
            "4h": 58.6,
            "1d": 42.8
        }
        current_rsi = rsi_values.get(timeframe, 50.0)
        previous_rsi = current_rsi - 2.5
        
        # Determine status based on thresholds
        if current_rsi < threshold_oversold:
            status = f"OVERSOLD (RSI < {threshold_oversold})"
            interpretation = "Potential BUY signal (oversold)"
        elif current_rsi > threshold_overbought:
            status = f"OVERBOUGHT (RSI > {threshold_overbought})"
            interpretation = "Potential SELL signal (overbought)"
        else:
            status = "neutral"
            interpretation = "Neutral momentum"
        
        return (
            f"RSI Analysis for {self.ticker} on {timeframe}:\n"
            f"  Current RSI: {current_rsi:.2f}\n"
            f"  Previous RSI: {previous_rsi:.2f}\n"
            f"  Status: {status}\n"
            f"  Thresholds: Oversold={threshold_oversold}, Overbought={threshold_overbought}\n"
            f"\nInterpretation: {interpretation}"
        )
    
    # Patch the _run method
    monkeypatch.setattr(
        "app.tools.crewai_tools.RSITool._run",
        mock_run
    )


@pytest.fixture
def mock_macd_tool(monkeypatch, mock_indicator_tools):
    """Mock MACD tool to return predictable output."""
    def mock_run(self, timeframe="1h", fast_period=12, slow_period=26, signal_period=9):
        """Mocked MACD calculation."""
        macd_values = {
            "5m": {"macd": 0.8, "signal": 0.6, "histogram": 0.2},
            "1h": {"macd": -0.3, "signal": -0.1, "histogram": -0.2},
            "1d": {"macd": 1.2, "signal": 0.9, "histogram": 0.3}
        }
        values = macd_values.get(timeframe, {"macd": 0.0, "signal": 0.0, "histogram": 0.0})
        
        crossover = "bullish" if values["histogram"] > 0 else "bearish"
        
        return (
            f"MACD Analysis for {self.ticker} on {timeframe}:\n"
            f"  MACD Line: {values['macd']:.2f}\n"
            f"  Signal Line: {values['signal']:.2f}\n"
            f"  Histogram: {values['histogram']:.2f}\n"
            f"  Crossover: {crossover}\n"
            f"\nInterpretation: {'Bullish momentum (MACD above signal)' if crossover == 'bullish' else 'Bearish momentum (MACD below signal)'}"
        )
    
    monkeypatch.setattr(
        "app.tools.crewai_tools.MACDTool._run",
        mock_run
    )


@pytest.fixture
def mock_all_tools(mock_indicator_tools, mock_rsi_tool, mock_macd_tool):
    """
    Convenience fixture to mock all indicator tools at once.
    
    Use this in tests to ensure no real API calls are made.
    
    Example:
        def test_bias_agent(state_with_market_data, mock_all_tools):
            # All tools are mocked, test is fast and predictable
            agent.process(state)
    """
    pass  # All mocking is done by dependent fixtures


@pytest.fixture(autouse=True)
def auto_mock_tools(mock_all_tools):
    """
    Automatically mock tools for ALL tests.
    
    This ensures tests never make real API calls unless explicitly disabled.
    To disable for a specific test, use:
        @pytest.mark.integration
        def test_with_real_apis():
            pass
    """
    pass
