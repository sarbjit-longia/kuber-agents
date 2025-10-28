"""
Unit tests for agent framework and agents.
"""
import pytest
from datetime import datetime
from uuid import uuid4

from app.agents import TimeTriggerAgent, MarketDataAgent, get_registry
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
        """Test that agents are registered."""
        registry = get_registry()
        metadata_list = registry.list_all_metadata()
        
        assert len(metadata_list) >= 2
        agent_types = [m.agent_type for m in metadata_list]
        assert "time_trigger" in agent_types
        assert "market_data_agent" in agent_types
    
    def test_get_agent_metadata(self):
        """Test getting agent metadata."""
        registry = get_registry()
        metadata = registry.get_metadata("time_trigger")
        
        assert metadata.agent_type == "time_trigger"
        assert metadata.name == "Time-Based Trigger"
        assert metadata.is_free is True
        assert metadata.category == "trigger"
    
    def test_create_agent_instance(self):
        """Test creating an agent instance."""
        registry = get_registry()
        agent = registry.create_agent(
            "time_trigger",
            "test-trigger-1",
            {"interval": "5m"}
        )
        
        assert agent.agent_id == "test-trigger-1"
        assert agent.config["interval"] == "5m"
    
    def test_list_agents_by_category(self):
        """Test filtering agents by category."""
        registry = get_registry()
        trigger_agents = registry.list_agents_by_category("trigger")
        data_agents = registry.list_agents_by_category("data")
        
        assert len(trigger_agents) >= 1
        assert len(data_agents) >= 1
        assert all(a.category == "trigger" for a in trigger_agents)
        assert all(a.category == "data" for a in data_agents)


class TestTimeTriggerAgent:
    """Tests for Time-Based Trigger Agent."""
    
    def test_trigger_met_basic(self, base_state):
        """Test that trigger is met with basic config."""
        agent = TimeTriggerAgent("trigger-1", {"interval": "5m"})
        
        result = agent.process(base_state)
        
        assert result.trigger_met is True
        assert result.trigger_reason is not None
        assert "Time trigger" in result.trigger_reason
    
    def test_trigger_with_time_constraints_outside_hours(self, base_state):
        """Test that trigger is not met outside configured hours."""
        # Configure for hours that don't include current time
        agent = TimeTriggerAgent(
            "trigger-2",
            {
                "interval": "5m",
                "start_time": "00:00",
                "end_time": "00:01"
            }
        )
        
        # Should raise TriggerNotMetException
        with pytest.raises(TriggerNotMetException):
            agent.process(base_state)
    
    def test_trigger_with_day_constraint(self, base_state):
        """Test that trigger respects day of week constraints."""
        from datetime import datetime
        
        # Get current day
        current_day = datetime.utcnow().weekday()
        
        # Configure to run on different days
        other_days = [d for d in range(7) if d != current_day]
        agent = TimeTriggerAgent(
            "trigger-3",
            {
                "interval": "5m",
                "days_of_week": other_days
            }
        )
        
        # Should raise TriggerNotMetException
        with pytest.raises(TriggerNotMetException):
            agent.process(base_state)
    
    def test_agent_logs_execution(self, base_state):
        """Test that agent logs its execution."""
        agent = TimeTriggerAgent("trigger-4", {"interval": "5m"})
        
        result = agent.process(base_state)
        
        assert len(result.execution_log) > 0
        assert any("trigger" in log["message"].lower() for log in result.execution_log)
    
    def test_agent_tracks_zero_cost(self, base_state):
        """Test that trigger agent has zero cost (it's free)."""
        agent = TimeTriggerAgent("trigger-5", {"interval": "5m"})
        
        result = agent.process(base_state)
        
        # Trigger agents should have zero cost
        assert result.total_cost == 0.0


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
        
        # Check candle structure
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
            symbol="",  # Empty symbol
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
        
        # Market data agent should have zero cost
        assert result.total_cost == 0.0


class TestPipelineState:
    """Tests for PipelineState helper methods."""
    
    def test_get_timeframe_data(self, base_state):
        """Test getting data for a specific timeframe."""
        # First populate with market data
        agent = MarketDataAgent(
            "market-test",
            {
                "timeframes": ["5m", "1h"],
                "use_mock_data": True
            }
        )
        
        result = agent.process(base_state)
        
        # Test get_timeframe_data
        data_5m = result.get_timeframe_data("5m")
        assert data_5m is not None
        assert len(data_5m) > 0
        
        # Test with non-existent timeframe
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
        base_state.add_cost("agent-1", 0.03)  # Add more to agent-1
        
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


class TestAgentConfigValidation:
    """Tests for agent configuration validation."""
    
    def test_missing_required_config_raises_error(self):
        """Test that missing required config raises error."""
        with pytest.raises(ValueError, match="Missing required configuration"):
            TimeTriggerAgent("trigger-bad", {})  # Missing required 'interval'
    
    def test_valid_config_works(self):
        """Test that valid config works."""
        agent = TimeTriggerAgent("trigger-good", {"interval": "5m"})
        assert agent.config["interval"] == "5m"

