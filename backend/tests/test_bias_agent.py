"""
Tests for Bias Agent

Tests cover:
- Instruction accuracy (custom thresholds, timeframes)
- Tool execution and synthesis
- Report generation
- Edge cases and error handling
"""
import pytest
from app.agents import get_registry
from tests.conftest import assert_reasoning_format


class TestBiasAgentAccuracy:
    """Test that Bias Agent follows instructions accurately."""
    
    @pytest.mark.accuracy
    def test_custom_rsi_thresholds_40_60(self, state_with_market_data):
        """Test: Agent should use custom RSI thresholds (40/60) instead of defaults (30/70)."""
        from tests.conftest import print_test_details
        registry = get_registry()
        
        config = {
            "instructions": (
                "Using RSI on daily timeframe determine if the bias is bullish, bearish or neutral. "
                "Use RSI thresholds of 40 and 60 (oversold below 40, overbought above 60)."
            ),
            "model": "lm-studio"
        }
        
        agent = registry.create_agent(
            agent_type="bias_agent",
            agent_id="test-bias-custom-thresholds",
            config=config
        )
        
        result = agent.process(state_with_market_data)
        
        # Print detailed output (visible with pytest -s)
        expected = {
            "reasoning_contains": "40",
            "reasoning_not_contains": "30"
        }
        print_test_details(
            "Custom RSI Thresholds (40/60)",
            config,
            result,
            expected
        )
        
        # Assert bias was determined
        assert result.biases, "Bias should be determined"
        assert "1d" in result.biases, "Should have 1d bias"
        
        bias = result.biases["1d"]
        assert bias.bias in ["BULLISH", "BEARISH", "NEUTRAL"], f"Invalid bias: {bias.bias}"
        assert 0 <= bias.confidence <= 1, f"Invalid confidence: {bias.confidence}"
        
        # Check reasoning mentions custom thresholds
        reasoning_lower = bias.reasoning.lower()
        
        # Should mention 40 or 60, NOT 30 or 70
        has_custom = "40" in bias.reasoning or "60" in bias.reasoning
        has_default = "30" in bias.reasoning or "70" in bias.reasoning
        
        assert has_custom, "Reasoning should mention custom thresholds (40/60)"
        assert not has_default, "Reasoning should NOT use default thresholds (30/70)"
    
    @pytest.mark.accuracy
    def test_specific_timeframe_selection(self, state_with_market_data):
        """Test: Agent should analyze the specified timeframe (4h) not others."""
        registry = get_registry()
        
        # Add 4h timeframe
        from tests.conftest import mock_market_data
        state_with_market_data.market_data.timeframes["4h"] = mock_market_data(None)("4h", 100, 250.0)
        state_with_market_data.timeframes.append("4h")
        
        config = {
            "instructions": "Analyze 4-hour timeframe to determine market bias using RSI and MACD.",
            "model": "lm-studio"
        }
        
        agent = registry.create_agent(
            agent_type="bias_agent",
            agent_id="test-bias-4h",
            config=config
        )
        
        result = agent.process(state_with_market_data)
        
        # Should have 4h bias
        assert "4h" in result.biases or result.biases, "Should determine bias for 4h"
        
        # Check reasoning mentions 4h or 4-hour
        if result.biases:
            bias = list(result.biases.values())[0]
            reasoning_lower = bias.reasoning.lower()
            assert "4h" in reasoning_lower or "4 hour" in reasoning_lower or "4-hour" in reasoning_lower, \
                "Reasoning should mention 4-hour timeframe"
    
    @pytest.mark.accuracy  
    def test_multiple_indicator_usage(self, state_with_market_data):
        """Test: Agent should use multiple indicators as instructed."""
        registry = get_registry()
        
        config = {
            "instructions": (
                "Determine bias using RSI, MACD, and SMA on daily timeframe. "
                "All three indicators must confirm before declaring strong bias."
            ),
            "model": "lm-studio"
        }
        
        agent = registry.create_agent(
            agent_type="bias_agent",
            agent_id="test-bias-multi-indicator",
            config=config
        )
        
        result = agent.process(state_with_market_data)
        
        assert result.biases, "Should determine bias"
        bias = list(result.biases.values())[0]
        
        reasoning_lower = bias.reasoning.lower()
        
        # Should mention at least 2 of the 3 indicators
        indicators_mentioned = sum([
            "rsi" in reasoning_lower,
            "macd" in reasoning_lower,
            "sma" in reasoning_lower or "moving average" in reasoning_lower
        ])
        
        assert indicators_mentioned >= 2, f"Should mention multiple indicators, found {indicators_mentioned}"


class TestBiasAgentReports:
    """Test that Bias Agent generates proper reports."""
    
    @pytest.mark.report
    def test_report_structure(self, state_with_market_data):
        """Test: Report should have all required fields."""
        registry = get_registry()
        
        config = {
            "instructions": "Determine market bias using RSI on daily timeframe.",
            "model": "lm-studio"
        }
        
        agent = registry.create_agent(
            agent_type="bias_agent",
            agent_id="test-bias-report",
            config=config
        )
        
        result = agent.process(state_with_market_data)
        
        # Check reports were created
        assert hasattr(result, 'reports'), "State should have reports"
        assert "test-bias-report" in result.reports, "Should have report for this agent"
        
        report = result.reports["test-bias-report"]
        
        # Verify report structure
        assert report.title == "Market Bias Analysis", f"Wrong title: {report.title}"
        assert report.summary, "Report should have summary"
        assert report.data, "Report should have data"
        
        # Check data fields
        assert "Market Bias" in report.data, "Should include bias in data"
        assert "Confidence Level" in report.data, "Should include confidence"
        assert "Analyzed Timeframe" in report.data, "Should include timeframe"
        assert "Detailed Analysis" in report.data, "Should include detailed analysis"
    
    @pytest.mark.report
    def test_reasoning_format(self, state_with_market_data):
        """Test: Reasoning should be clean and professional."""
        registry = get_registry()
        
        config = {
            "instructions": "Use RSI to determine bias on daily timeframe.",
            "model": "lm-studio"
        }
        
        agent = registry.create_agent(
            agent_type="bias_agent",
            agent_id="test-bias-format",
            config=config
        )
        
        result = agent.process(state_with_market_data)
        
        bias = list(result.biases.values())[0]
        
        # Use utility to check formatting
        assert_reasoning_format(bias.reasoning)
    
    @pytest.mark.report
    def test_key_factors_populated(self, state_with_market_data):
        """Test: Key factors should be identified and listed."""
        registry = get_registry()
        
        config = {
            "instructions": "Determine bias using multiple factors: RSI, MACD, volume, and trend.",
            "model": "lm-studio"
        }
        
        agent = registry.create_agent(
            agent_type="bias_agent",
            agent_id="test-bias-factors",
            config=config
        )
        
        result = agent.process(state_with_market_data)
        
        bias = list(result.biases.values())[0]
        
        # Should have key factors
        assert bias.key_factors, "Should identify key factors"
        assert isinstance(bias.key_factors, list), "Key factors should be a list"
        assert len(bias.key_factors) > 0, "Should have at least one key factor"


class TestBiasAgentEdgeCases:
    """Test edge cases and error handling."""
    
    @pytest.mark.unit
    def test_missing_timeframe_data(self, mock_state):
        """Test: Agent should handle missing timeframe gracefully."""
        registry = get_registry()
        
        # State with NO market data for requested timeframe
        from app.schemas.pipeline_state import MarketData
        mock_state.market_data = MarketData(
            symbol="AAPL",
            current_price=250.0,
            timeframes={},  # Empty!
            fetched_at=None
        )
        
        config = {
            "instructions": "Determine bias on 1d timeframe using RSI.",
            "model": "lm-studio"
        }
        
        agent = registry.create_agent(
            agent_type="bias_agent",
            agent_id="test-bias-no-data",
            config=config
        )
        
        # Should raise InsufficientDataError
        from app.agents.base import InsufficientDataError
        with pytest.raises(InsufficientDataError):
            agent.process(mock_state)
    
    @pytest.mark.unit
    def test_very_short_instructions(self, state_with_market_data):
        """Test: Agent should work with minimal instructions."""
        registry = get_registry()
        
        config = {
            "instructions": "Determine bias.",
            "model": "lm-studio"
        }
        
        agent = registry.create_agent(
            agent_type="bias_agent",
            agent_id="test-bias-short",
            config=config
        )
        
        result = agent.process(state_with_market_data)
        
        # Should still work (use defaults)
        assert result.biases, "Should determine bias even with short instructions"
    
    @pytest.mark.unit
    def test_conflicting_instructions(self, state_with_market_data):
        """Test: Agent should handle conflicting instructions reasonably."""
        registry = get_registry()
        
        config = {
            "instructions": (
                "Determine BULLISH bias only. Never return BEARISH or NEUTRAL. "
                "But also be objective and honest in your analysis."
            ),
            "model": "lm-studio"
        }
        
        agent = registry.create_agent(
            agent_type="bias_agent",
            agent_id="test-bias-conflict",
            config=config
        )
        
        result = agent.process(state_with_market_data)
        
        # Should complete without error (LLM should resolve conflict)
        assert result.biases, "Should handle conflicting instructions"
        bias = list(result.biases.values())[0]
        assert bias.bias in ["BULLISH", "BEARISH", "NEUTRAL"], "Should return valid bias"


class TestBiasAgentToolExecution:
    """Test that tools are properly executed (not just syntax returned)."""
    
    @pytest.mark.accuracy
    @pytest.mark.slow
    def test_tool_execution_not_just_syntax(self, state_with_market_data):
        """Test: Agent should EXECUTE tools, not return tool call syntax."""
        registry = get_registry()
        
        config = {
            "instructions": "Use RSI calculator with period 14 on daily timeframe. Report the actual RSI value.",
            "model": "lm-studio"
        }
        
        agent = registry.create_agent(
            agent_type="bias_agent",
            agent_id="test-bias-tool-exec",
            config=config
        )
        
        result = agent.process(state_with_market_data)
        
        bias = list(result.biases.values())[0]
        
        # Reasoning should NOT contain tool syntax
        assert "to=" not in bias.reasoning, "Should not contain tool call syntax"
        assert "json" not in bias.reasoning.lower() or "json format" in bias.reasoning.lower(), \
            "Should not contain raw JSON (unless referring to format)"
        assert "<|" not in bias.reasoning, "Should not contain CrewAI markers"
        
        # Reasoning SHOULD contain actual analysis
        assert "rsi" in bias.reasoning.lower(), "Should mention RSI in analysis"
        
        # If tool executed properly, should have numeric values
        import re
        has_numbers = bool(re.search(r'\d+\.?\d*', bias.reasoning))
        assert has_numbers, "Should contain numeric values from tool execution"

