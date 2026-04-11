"""
Unit tests for agent framework and agents.
"""
import pytest
from datetime import datetime
from uuid import uuid4

from app.agents import MarketDataAgent, get_registry
from app.agents.base import TriggerNotMetException, InsufficientDataError
from app.schemas.pipeline_state import PipelineState


@pytest.fixture
def base_state():
    """Create a basic pipeline state for testing."""
    return PipelineState(
        pipeline_id=uuid4(),
        execution_id=uuid4(),
        user_id=uuid4(),
        symbol="AAPL",
        mode="paper"
    )


class TestAgentRegistry:
    """Tests for the agent registry."""

    def test_registry_has_agents(self):
        """Test that all current agents are registered."""
        registry = get_registry()
        metadata_list = registry.list_all_metadata()

        assert len(metadata_list) >= 5
        agent_types = [m.agent_type for m in metadata_list]
        assert "market_data_agent" in agent_types
        assert "bias_agent" in agent_types
        assert "strategy_agent" in agent_types
        assert "risk_manager_agent" in agent_types
        assert "trade_manager_agent" in agent_types

    def test_get_market_data_agent_metadata(self):
        """Test getting metadata for MarketDataAgent."""
        registry = get_registry()
        metadata = registry.get_metadata("market_data_agent")

        assert metadata.agent_type == "market_data_agent"
        assert metadata.category == "data"
        assert metadata.is_free is True

    def test_create_agent_instance(self):
        """Test creating an agent instance from the registry."""
        registry = get_registry()
        agent = registry.create_agent(
            "market_data_agent",
            "test-market-1",
            {"timeframes": ["5m"]}
        )

        assert agent.agent_id == "test-market-1"
        assert agent.config["timeframes"] == ["5m"]

    def test_list_agents_by_category(self):
        """Test filtering agents by category."""
        registry = get_registry()
        data_agents = registry.list_agents_by_category("data")
        analysis_agents = registry.list_agents_by_category("analysis")

        assert len(data_agents) >= 1
        assert len(analysis_agents) >= 1
        assert all(a.category == "data" for a in data_agents)
        assert all(a.category == "analysis" for a in analysis_agents)

    def test_no_time_trigger_agent_registered(self):
        """Confirm TimeTriggerAgent is not in registry (replaced by signal architecture)."""
        registry = get_registry()
        metadata = registry.get_metadata("time_trigger")
        assert metadata is None, "time_trigger should not be registered — use signal/scanner triggers"


class TestMarketDataAgent:
    """Tests for Market Data Agent."""

    def test_market_data_agent_with_mock_data(self, base_state):
        """Test market data agent with mock data."""
        agent = MarketDataAgent(
            "market-1",
            {
                "timeframes": ["5m", "1h"],
                "lookback_periods": 50,
                "use_mock_data": True
            }
        )

        result = agent.process(base_state)

        assert result.market_data is not None
        assert result.market_data.symbol == "AAPL"
        assert result.market_data.current_price > 0
        assert len(result.market_data.timeframes) == 2
        assert "5m" in result.market_data.timeframes
        assert "1h" in result.market_data.timeframes

    def test_market_data_agent_populates_candles(self, base_state):
        """Test that market data agent fetches candle data."""
        agent = MarketDataAgent(
            "market-2",
            {
                "timeframes": ["5m"],
                "lookback_periods": 20,
                "use_mock_data": True
            }
        )

        result = agent.process(base_state)

        candles = result.market_data.timeframes["5m"]
        assert len(candles) > 0
        assert len(candles) <= 20

        first_candle = candles[0]
        assert hasattr(first_candle, "open")
        assert hasattr(first_candle, "high")
        assert hasattr(first_candle, "low")
        assert hasattr(first_candle, "close")
        assert hasattr(first_candle, "volume")
        assert hasattr(first_candle, "timestamp")

    def test_market_data_agent_fails_without_symbol(self):
        """Test that agent raises error if no symbol provided."""
        state = PipelineState(
            pipeline_id=uuid4(),
            execution_id=uuid4(),
            user_id=uuid4(),
            symbol="",
            mode="paper"
        )

        agent = MarketDataAgent(
            "market-3",
            {
                "timeframes": ["5m"],
                "use_mock_data": True
            }
        )

        with pytest.raises(InsufficientDataError):
            agent.process(state)

    def test_market_data_agent_logs_execution(self, base_state):
        """Test that agent logs its execution."""
        agent = MarketDataAgent(
            "market-4",
            {
                "timeframes": ["5m"],
                "lookback_periods": 10,
                "use_mock_data": True
            }
        )

        result = agent.process(base_state)

        assert len(result.execution_log) > 0
        assert any("market data" in log["message"].lower() for log in result.execution_log)

    def test_market_data_agent_has_zero_cost(self, base_state):
        """Test that market data agent has zero cost (it's free)."""
        agent = MarketDataAgent(
            "market-5",
            {
                "timeframes": ["5m"],
                "use_mock_data": True
            }
        )

        result = agent.process(base_state)

        assert result.total_cost == 0.0


class TestPipelineState:
    """Tests for PipelineState helper methods."""

    def test_get_timeframe_data(self, base_state):
        """Test getting data for a specific timeframe."""
        agent = MarketDataAgent(
            "market-test",
            {
                "timeframes": ["5m", "1h"],
                "use_mock_data": True
            }
        )

        result = agent.process(base_state)

        data_5m = result.get_timeframe_data("5m")
        assert data_5m is not None
        assert len(data_5m) > 0

        data_none = result.get_timeframe_data("1d")
        assert data_none is None

    def test_get_latest_candle(self, base_state):
        """Test getting the latest candle."""
        agent = MarketDataAgent(
            "market-test",
            {
                "timeframes": ["5m"],
                "use_mock_data": True
            }
        )

        result = agent.process(base_state)

        latest = result.get_latest_candle("5m")
        assert latest is not None
        assert hasattr(latest, "close")

    def test_add_cost(self, base_state):
        """Test adding costs."""
        base_state.add_cost("agent-1", 0.05)
        base_state.add_cost("agent-2", 0.10)
        base_state.add_cost("agent-1", 0.03)

        assert base_state.total_cost == 0.18
        assert base_state.agent_costs["agent-1"] == 0.08
        assert base_state.agent_costs["agent-2"] == 0.10

    def test_add_log(self, base_state):
        """Test adding log entries."""
        base_state.add_log("agent-1", "Test message", "info")
        base_state.add_log("agent-2", "Warning message", "warning")

        assert len(base_state.execution_log) == 2
        assert base_state.execution_log[0]["agent_id"] == "agent-1"
        assert base_state.execution_log[0]["level"] == "info"
        assert base_state.execution_log[1]["level"] == "warning"
