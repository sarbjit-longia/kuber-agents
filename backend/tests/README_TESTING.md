# Agent Testing Guide

## 🎯 Overview

This directory contains test suites for all agents. Tests are designed to be **fast, predictable, and independent** by mocking external dependencies.

## 📋 Test Structure

```
tests/
├── conftest.py              # Shared fixtures and mocks
├── test_bias_agent.py       # Bias Agent tests
├── test_strategy_agent.py   # Strategy Agent tests
├── test_risk_manager_agent.py  # Risk Manager tests
└── README_TESTING.md        # This file
```

## 🔧 Mocking Strategy

### **Problem: Unpredictable External Dependencies**

Without mocking, tests:
- ❌ Call real APIs (Finnhub, Data Plane)
- ❌ Depend on market conditions (tests fail randomly)
- ❌ Are SLOW (3+ minutes per test)
- ❌ Require all services running
- ❌ Cost money (API calls)

### **Solution: Mock All External Calls**

The `conftest.py` file provides automatic mocking:

```python
@pytest.fixture(autouse=True)
def auto_mock_tools(mock_all_tools):
    """Automatically mock tools for ALL tests."""
    # This runs for every test automatically
    pass
```

### **What Gets Mocked:**

1. **IndicatorTools** - Returns fake RSI, MACD, SMA values
2. **RSITool** - Returns predictable RSI analysis
3. **MACDTool** - Returns predictable MACD analysis
4. **Market Data** - Uses fixture data (no real API calls)

## 📊 Predictable Test Data

### **RSI Values (Mocked)**
```python
Timeframe → RSI Value
"5m"  → 52.3 (neutral, slightly bullish)
"15m" → 48.7 (neutral, slightly bearish)
"1h"  → 45.2 (neutral)
"4h"  → 58.6 (neutral, approaching overbought)
"1d"  → 42.8 (neutral)
```

### **MACD Values (Mocked)**
```python
Timeframe → MACD / Signal / Histogram
"5m"  → 0.8 / 0.6 / +0.2 (bullish)
"1h"  → -0.3 / -0.1 / -0.2 (bearish)
"1d"  → 1.2 / 0.9 / +0.3 (bullish)
```

### **Market Data (Fixture)**
```python
# 100 candles per timeframe
- Uptrend: $250 → $260
- Realistic OHLC spread
- Volume: 1M+ per candle
- Timestamps: Sequential
```

## 🚀 Running Tests

### **Run All Bias Agent Tests**
```bash
cd backend
docker-compose exec backend pytest tests/test_bias_agent.py -v
```

### **Run with Detailed Output (Verbose)**
```bash
# Show test details: instructions, LLM output, expected vs actual
docker-compose exec backend pytest tests/test_bias_agent.py -v -s

# This will print for each test:
# - Input: Instructions, model, config
# - LLM Output: Full reasoning, bias, confidence
# - Expected vs Actual: Visual comparison
```

### **Run Single Test with Details**
```bash
docker-compose exec backend pytest tests/test_bias_agent.py::TestBiasAgentAccuracy::test_custom_rsi_thresholds_40_60 -v -s
```

### **Run Only Fast Tests (Exclude Slow)**
```bash
docker-compose exec backend pytest tests/test_bias_agent.py -m "not slow" -v
```

### **Run with Print Statements**
```bash
docker-compose exec backend pytest tests/test_bias_agent.py -v -s
```

### **Run Specific Category**
```bash
# Accuracy tests only
docker-compose exec backend pytest tests/ -m accuracy -v -s

# Unit tests only
docker-compose exec backend pytest tests/ -m unit -v

# Report tests only
docker-compose exec backend pytest tests/ -m report -v
```

## 🏷️ Test Markers

Tests are categorized with markers:

- `@pytest.mark.accuracy` - Tests agent behavior accuracy
- `@pytest.mark.report` - Tests report generation
- `@pytest.mark.unit` - Fast unit tests
- `@pytest.mark.slow` - Long-running tests
- `@pytest.mark.integration` - Real API calls (not mocked)

## ✅ Test Checklist

When writing new tests:

1. ✅ Use `state_with_market_data` fixture for market data
2. ✅ Mocking is automatic (don't manually call APIs)
3. ✅ Use `model: "lm-studio"` for local testing
4. ✅ Add appropriate markers (`@pytest.mark.accuracy`, etc.)
5. ✅ Assert both success and failure cases
6. ✅ Check reasoning format (no artifacts)
7. ✅ Verify report generation
8. ✅ Test should complete in < 30 seconds

## 📝 Example Test

```python
@pytest.mark.accuracy
def test_custom_rsi_thresholds_40_60(self, state_with_market_data):
    """Test: Agent should use custom RSI thresholds (40/60)."""
    registry = get_registry()
    
    # Configure agent with custom thresholds
    config = {
        "instructions": "Use RSI with 40/60 thresholds",
        "model": "lm-studio"  # Use local model
    }
    
    agent = registry.create_agent(
        agent_type="bias_agent",
        agent_id="test-bias",
        config=config
    )
    
    # Process with mocked data (fast!)
    result = agent.process(state_with_market_data)
    
    # Assert results
    assert result.biases["1d"].bias in ["BULLISH", "BEARISH", "NEUTRAL"]
    assert "40" in result.biases["1d"].reasoning  # Custom threshold used
```

## 🔍 Debugging Failed Tests

### **Test Takes Too Long (>3 minutes)**
- ✅ Check if mocking is working
- ✅ Verify `auto_mock_tools` fixture is active
- ✅ Look for real API calls in logs

### **Test Results Vary**
- ✅ Ensure using `mock_all_tools` fixture
- ✅ Check if hardcoded test data is used
- ✅ Verify no environment-dependent logic

### **"Tool not found" Errors**
- ✅ Check tool registry is populated
- ✅ Verify tool names match exactly
- ✅ Ensure imports are correct

## 🎯 Best Practices

### **DO:**
✅ Mock external APIs  
✅ Use fixtures for test data  
✅ Test one thing per test  
✅ Use descriptive test names  
✅ Add docstrings explaining what's tested  
✅ Assert specific values, not just "truthy"  

### **DON'T:**
❌ Make real API calls in unit tests  
❌ Test multiple behaviors in one test  
❌ Use hardcoded IDs (use uuid4())  
❌ Depend on test execution order  
❌ Skip assertions ("it doesn't crash" isn't enough)  

## 🚦 Test Coverage Goals

- **Bias Agent**: 80%+ coverage
- **Strategy Agent**: 80%+ coverage
- **Risk Manager**: 80%+ coverage
- **Trade Manager**: 70%+ coverage

## 📚 Resources

- Pytest docs: https://docs.pytest.org/
- Monkeypatch: https://docs.pytest.org/en/stable/how-to/monkeypatch.html
- Fixtures: https://docs.pytest.org/en/stable/how-to/fixtures.html

## 🐛 Troubleshooting

### Mocking Not Working?

1. Check `conftest.py` is in `tests/` directory
2. Verify `autouse=True` on `auto_mock_tools`
3. Restart pytest if fixtures were recently changed
4. Check import paths match exactly

### Tests Still Calling Real APIs?

1. Add print statement in mock to verify it's called
2. Check tool is instantiated AFTER mock is applied
3. Verify monkeypatch path is correct

## 📊 Current Status

- ✅ Mock fixtures created
- ✅ Auto-mocking enabled
- ✅ Predictable test data defined
- ✅ All tests use local model
- ⏳ Tests still slow (CrewAI overhead)
- ⏳ Some tests may still call Data Plane

**Next Steps:**
1. Verify mocking is fully working
2. Optimize test fixtures
3. Add more edge case tests
4. Improve test documentation

---

**Last Updated:** 2025-12-20  
**Maintained By:** Trading Platform Team

