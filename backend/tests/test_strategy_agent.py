"""
Tests for Strategy Agent

Tests cover:
- Instruction accuracy (patterns, entry rules, R/R ratios)
- Chart data generation
- Report generation with charts
- Edge cases and error handling
"""
import pytest
from app.agents import get_registry
from tests.conftest import assert_reasoning_format


class TestStrategyAgentAccuracy:
    """Test that Strategy Agent follows instructions accurately."""
    
    @pytest.mark.accuracy
    def test_fvg_strategy_specific_instructions(self, state_with_bias):
        """Test: Agent should look for FVG and apply specific entry rules."""
        registry = get_registry()
        
        config = {
            "instructions": (
                "Buy when there is a bullish FVG formed on the 5-minute chart and price returns to this FVG. "
                "Set stop loss below the FVG and take profit at 1.5x risk."
            ),
            "model": "gpt-4"
        }
        
        agent = registry.create_agent(
            agent_type="strategy_agent",
            agent_id="test-strategy-fvg",
            config=config
        )
        
        result = agent.process(state_with_bias)
        
        # Should generate strategy
        assert result.strategy, "Should generate strategy"
        strategy = result.strategy
        
        assert strategy.action in ["BUY", "SELL", "HOLD"], f"Invalid action: {strategy.action}"
        
        # Check reasoning mentions FVG
        reasoning_lower = strategy.reasoning.lower()
        assert "fvg" in reasoning_lower or "fair value gap" in reasoning_lower, \
            "Strategy should mention FVG when instructed to look for it"
        
        # If strategy is BUY or SELL, check R/R ratio
        if strategy.action in ["BUY", "SELL"] and strategy.entry_price:
            if strategy.stop_loss and strategy.take_profit:
                risk = abs(strategy.entry_price - strategy.stop_loss)
                reward = abs(strategy.take_profit - strategy.entry_price)
                
                if risk > 0:
                    rr_ratio = reward / risk
                    # Should be around 1.5 (allow 1.2-1.8 range)
                    assert 1.2 <= rr_ratio <= 1.8, \
                        f"R/R ratio should be near 1.5x as instructed, got {rr_ratio:.2f}"
    
    @pytest.mark.accuracy
    def test_specific_pattern_detection(self, state_with_bias):
        """Test: Agent should look for specific pattern (Bull Flag)."""
        registry = get_registry()
        
        config = {
            "instructions": (
                "Look for bull flag pattern on 5-minute chart. "
                "Enter long when price breaks above the flag's resistance with increased volume."
            ),
            "model": "gpt-4"
        }
        
        agent = registry.create_agent(
            agent_type="strategy_agent",
            agent_id="test-strategy-bull-flag",
            config=config
        )
        
        result = agent.process(state_with_bias)
        
        assert result.strategy, "Should generate strategy"
        strategy = result.strategy
        
        reasoning_lower = strategy.reasoning.lower()
        
        # Should mention bull flag or flag pattern
        assert "flag" in reasoning_lower or "bull flag" in reasoning_lower, \
            "Should mention bull flag pattern when instructed"
    
    @pytest.mark.accuracy
    def test_custom_risk_reward_ratio(self, state_with_bias):
        """Test: Agent should use custom R/R ratio (2:1)."""
        registry = get_registry()
        
        config = {
            "instructions": (
                "Generate trading signals with strict 2:1 risk/reward ratio. "
                "Entry at support/resistance levels."
            ),
            "model": "gpt-4"
        }
        
        agent = registry.create_agent(
            agent_type="strategy_agent",
            agent_id="test-strategy-2to1",
            config=config
        )
        
        result = agent.process(state_with_bias)
        
        assert result.strategy, "Should generate strategy"
        strategy = result.strategy
        
        # If trade signal generated, check R/R
        if strategy.action in ["BUY", "SELL"] and all([
            strategy.entry_price, strategy.stop_loss, strategy.take_profit
        ]):
            risk = abs(strategy.entry_price - strategy.stop_loss)
            reward = abs(strategy.take_profit - strategy.entry_price)
            
            if risk > 0:
                rr_ratio = reward / risk
                # Should be around 2.0 (allow 1.8-2.2 range)
                assert 1.8 <= rr_ratio <= 2.2, \
                    f"R/R ratio should be near 2:1 as instructed, got {rr_ratio:.2f}"
    
    @pytest.mark.accuracy
    def test_timeframe_specific_analysis(self, state_with_bias):
        """Test: Agent should analyze specified timeframe (5m)."""
        registry = get_registry()
        
        config = {
            "instructions": "Generate scalping signals on 5-minute timeframe only.",
            "model": "gpt-4"
        }
        
        agent = registry.create_agent(
            agent_type="strategy_agent",
            agent_id="test-strategy-5m",
            config=config
        )
        
        result = agent.process(state_with_bias)
        
        assert result.strategy, "Should generate strategy"
        strategy = result.strategy
        
        reasoning_lower = strategy.reasoning.lower()
        
        # Should mention 5m or 5-minute
        assert "5m" in reasoning_lower or "5 minute" in reasoning_lower or "5-minute" in reasoning_lower, \
            "Should analyze 5-minute timeframe as instructed"


class TestStrategyAgentReports:
    """Test that Strategy Agent generates proper reports with charts."""
    
    @pytest.mark.report
    def test_report_structure(self, state_with_bias):
        """Test: Report should have all required fields."""
        registry = get_registry()
        
        config = {
            "instructions": "Generate trading signals with clear entry/exit points.",
            "model": "gpt-4"
        }
        
        agent = registry.create_agent(
            agent_type="strategy_agent",
            agent_id="test-strategy-report",
            config=config
        )
        
        result = agent.process(state_with_bias)
        
        # Check reports
        assert hasattr(result, 'reports'), "Should have reports"
        assert "test-strategy-report" in result.reports, "Should have report for this agent"
        
        report = result.reports["test-strategy-report"]
        
        # Verify structure
        assert report.title == "Strategy Analysis", f"Wrong title: {report.title}"
        assert report.summary, "Should have summary"
        assert report.data, "Should have data"
        
        # Check data fields
        assert "Action" in report.data, "Should include action"
        assert "Confidence" in report.data, "Should include confidence"
        assert "Strategy Reasoning" in report.data, "Should include reasoning"
    
    @pytest.mark.report
    def test_chart_data_generation(self, state_with_bias):
        """Test: Chart data should be generated with entry/exit levels."""
        registry = get_registry()
        
        config = {
            "instructions": "Generate buy signals with clear entry, stop loss, and take profit levels.",
            "model": "gpt-4"
        }
        
        agent = registry.create_agent(
            agent_type="strategy_agent",
            agent_id="test-strategy-chart",
            config=config
        )
        
        result = agent.process(state_with_bias)
        
        # Check if chart data exists
        report = result.reports.get("test-strategy-chart")
        if report and "chart_data" in report.data:
            chart_data = report.data["chart_data"]
            
            # Should have candles
            assert "candles" in chart_data, "Chart should include candle data"
            assert len(chart_data["candles"]) > 0, "Should have candle data"
            
            # If strategy has levels, should have annotations
            if result.strategy.action in ["BUY", "SELL"]:
                if result.strategy.entry_price:
                    assert "annotations" in chart_data, "Should have chart annotations"
    
    @pytest.mark.report
    def test_reasoning_format_with_sections(self, state_with_bias):
        """Test: Reasoning should be formatted with clear sections."""
        registry = get_registry()
        
        config = {
            "instructions": "Provide detailed strategy analysis with market structure, entry rationale, and risk factors.",
            "model": "gpt-4"
        }
        
        agent = registry.create_agent(
            agent_type="strategy_agent",
            agent_id="test-strategy-format",
            config=config
        )
        
        result = agent.process(state_with_bias)
        
        strategy = result.strategy
        
        # Check formatting
        assert_reasoning_format(
            strategy.reasoning,
            required_sections=["MARKET STRUCTURE", "ENTRY RATIONALE"]
        )


class TestStrategyAgentEdgeCases:
    """Test edge cases and error handling."""
    
    @pytest.mark.unit
    def test_no_trading_opportunity(self, state_with_bias):
        """Test: Agent should return HOLD when no clear opportunity."""
        registry = get_registry()
        
        # Modify bias to NEUTRAL (no clear direction)
        state_with_bias.biases["1d"].bias = "NEUTRAL"
        state_with_bias.biases["1d"].confidence = 0.3
        
        config = {
            "instructions": "Only trade when there is very high confidence setup (>80%). Otherwise hold.",
            "model": "gpt-4"
        }
        
        agent = registry.create_agent(
            agent_type="strategy_agent",
            agent_id="test-strategy-hold",
            config=config
        )
        
        result = agent.process(state_with_bias)
        
        # Should generate strategy (might be HOLD)
        assert result.strategy, "Should generate strategy result"
        
        # If HOLD, should explain why
        if result.strategy.action == "HOLD":
            assert result.strategy.reasoning, "HOLD decision should have reasoning"
    
    @pytest.mark.unit
    def test_missing_bias(self, state_with_market_data):
        """Test: Agent should handle missing bias gracefully."""
        registry = get_registry()
        
        # State has market data but NO bias
        config = {
            "instructions": "Generate trading signals based on market bias.",
            "model": "gpt-4"
        }
        
        agent = registry.create_agent(
            agent_type="strategy_agent",
            agent_id="test-strategy-no-bias",
            config=config
        )
        
        # Should still work (bias is helpful but not required)
        result = agent.process(state_with_market_data)
        assert result.strategy, "Should generate strategy even without bias"
    
    @pytest.mark.unit
    def test_unrealistic_instructions(self, state_with_bias):
        """Test: Agent should handle unrealistic instructions gracefully."""
        registry = get_registry()
        
        config = {
            "instructions": (
                "Generate signals with 100:1 risk/reward ratio and 99% win rate. "
                "Never take losses."
            ),
            "model": "gpt-4"
        }
        
        agent = registry.create_agent(
            agent_type="strategy_agent",
            agent_id="test-strategy-unrealistic",
            config=config
        )
        
        # Should complete without error (LLM should handle gracefully)
        result = agent.process(state_with_bias)
        assert result.strategy, "Should handle unrealistic instructions"


class TestStrategyAgentPriceValidity:
    """Test that generated prices are valid and reasonable."""
    
    @pytest.mark.unit
    def test_price_levels_logical_for_long(self, state_with_bias):
        """Test: For BUY signals, stop < entry < target."""
        registry = get_registry()
        
        config = {
            "instructions": "Generate long (BUY) signals only.",
            "model": "gpt-4"
        }
        
        agent = registry.create_agent(
            agent_type="strategy_agent",
            agent_id="test-strategy-long-prices",
            config=config
        )
        
        result = agent.process(state_with_bias)
        
        strategy = result.strategy
        
        if strategy.action == "BUY" and all([
            strategy.entry_price, strategy.stop_loss, strategy.take_profit
        ]):
            # For long: stop_loss < entry_price < take_profit
            assert strategy.stop_loss < strategy.entry_price, \
                f"Stop loss ({strategy.stop_loss}) should be below entry ({strategy.entry_price}) for long"
            assert strategy.entry_price < strategy.take_profit, \
                f"Entry ({strategy.entry_price}) should be below target ({strategy.take_profit}) for long"
    
    @pytest.mark.unit
    def test_price_levels_near_current_price(self, state_with_bias):
        """Test: Entry price should be reasonably close to current price."""
        registry = get_registry()
        
        config = {
            "instructions": "Generate immediate entry signals (not limit orders far away).",
            "model": "gpt-4"
        }
        
        agent = registry.create_agent(
            agent_type="strategy_agent",
            agent_id="test-strategy-price-range",
            config=config
        )
        
        result = agent.process(state_with_bias)
        
        strategy = result.strategy
        current_price = state_with_bias.market_data.current_price
        
        if strategy.action in ["BUY", "SELL"] and strategy.entry_price:
            # Entry should be within 5% of current price
            price_diff_pct = abs(strategy.entry_price - current_price) / current_price * 100
            assert price_diff_pct <= 5.0, \
                f"Entry price ({strategy.entry_price}) too far from current ({current_price}): {price_diff_pct:.1f}%"

