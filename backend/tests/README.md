# Agent Testing Suite

Comprehensive test suite for validating agent accuracy, report generation, and proper instruction following.

## Overview

This test suite ensures that:
- ✅ **Agents follow custom instructions accurately** (thresholds, patterns, ratios)
- ✅ **Tools are executed properly** (not just syntax returned)
- ✅ **Reports are generated with correct structure and formatting**
- ✅ **Edge cases are handled gracefully**
- ✅ **Calculations are accurate** (position sizing, R/R ratios)

## Structure

```
tests/
├── __init__.py
├── conftest.py                    # Shared fixtures and utilities
├── test_bias_agent.py             # Bias Agent tests (accuracy, reports, tools)
├── test_strategy_agent.py         # Strategy Agent tests (patterns, charts, prices)
└── test_risk_manager_agent.py     # Risk Manager tests (limits, calculations)
```

## Running Tests

### Run All Tests
```bash
# Inside Docker container
docker-compose exec backend pytest

# Or with more detail
docker-compose exec backend pytest -v
```

### Run Specific Test File
```bash
# Test only Bias Agent
docker-compose exec backend pytest tests/test_bias_agent.py -v

# Test only Strategy Agent
docker-compose exec backend pytest tests/test_strategy_agent.py -v

# Test only Risk Manager
docker-compose exec backend pytest tests/test_risk_manager_agent.py -v
```

### Run Tests by Marker

Tests are marked with categories:

```bash
# Run only accuracy tests (instruction following)
docker-compose exec backend pytest -m accuracy -v

# Run only report generation tests
docker-compose exec backend pytest -m report -v

# Run only unit tests (fast, no LLM calls or mocked)
docker-compose exec backend pytest -m unit -v

# Run only integration tests
docker-compose exec backend pytest -m integration -v

# Exclude slow tests
docker-compose exec backend pytest -m "not slow" -v
```

### Run Specific Test
```bash
# Run single test by name
docker-compose exec backend pytest tests/test_bias_agent.py::TestBiasAgentAccuracy::test_custom_rsi_thresholds_40_60 -v
```

### Run with Coverage
```bash
docker-compose exec backend pytest --cov=app.agents --cov-report=html

# View coverage report
open backend/htmlcov/index.html
```

## Test Categories

### 🎯 Accuracy Tests (`@pytest.mark.accuracy`)

Test that agents follow instructions accurately:

**Bias Agent:**
- Custom RSI thresholds (40/60 instead of 30/70)
- Specific timeframe selection (4h vs 1d)
- Multiple indicator usage (RSI + MACD + SMA)
- Tool execution (not just syntax)

**Strategy Agent:**
- Specific pattern detection (FVG, Bull Flag)
- Custom R/R ratios (1.5:1, 2:1)
- Timeframe-specific analysis (5m scalping)

**Risk Manager:**
- Risk per trade limits (1%, 2%)
- Position size limits (25% of account)
- Minimum R/R thresholds (2:1)

### 📊 Report Tests (`@pytest.mark.report`)

Test that reports are generated properly:

- Report structure (title, summary, data fields)
- Reasoning format (clean, no artifacts)
- Chart data generation (candles, annotations)
- Key factors/warnings populated

### 🔧 Unit Tests (`@pytest.mark.unit`)

Fast tests for edge cases and error handling:

- Missing data handling
- Empty/minimal instructions
- Conflicting instructions
- Boundary conditions (zero balance, incomplete prices)
- Calculation accuracy

### 🐌 Slow Tests (`@pytest.mark.slow`)

Tests that make multiple LLM calls or process large data:

- Mark tests that take >5 seconds
- Can be excluded during quick development cycles

## Fixtures

### Available Fixtures (from `conftest.py`)

```python
mock_state                 # Empty pipeline state
mock_market_data          # Function to generate candles
state_with_market_data    # State with 5m, 1h, 1d candles
state_with_bias           # State with bias determined
state_with_strategy       # State with strategy generated
```

### Utility Functions

```python
assert_reasoning_format(reasoning, required_sections)
# Validates reasoning is clean (no artifacts, proper sections)

assert_report_generated(state, agent_id)
# Validates report exists and has required fields
```

## Writing New Tests

### Template for Accuracy Test

```python
@pytest.mark.accuracy
def test_agent_follows_custom_instruction(self, state_with_market_data):
    """Test: Agent should follow specific custom instruction."""
    registry = get_registry()
    
    config = {
        "instructions": "Your custom instruction here...",
        "model": "gpt-3.5-turbo"
    }
    
    agent = registry.create_agent(
        agent_type="bias_agent",
        agent_id="test-id",
        config=config
    )
    
    result = agent.process(state_with_market_data)
    
    # Assert expected behavior
    assert result.biases, "Should generate result"
    # ... more specific assertions
```

### Template for Report Test

```python
@pytest.mark.report
def test_report_structure(self, state_with_market_data):
    """Test: Report should have correct structure."""
    registry = get_registry()
    
    config = {
        "instructions": "Generate detailed report.",
        "model": "gpt-3.5-turbo"
    }
    
    agent = registry.create_agent(
        agent_type="bias_agent",
        agent_id="test-report",
        config=config
    )
    
    result = agent.process(state_with_market_data)
    
    # Check report
    assert "test-report" in result.reports
    report = result.reports["test-report"]
    
    assert report.title == "Expected Title"
    assert report.summary
    assert_reasoning_format(result.biases["1d"].reasoning)
```

## Common Issues

### Issue: Tests Fail with "Tool syntax in reasoning"

**Cause:** Agent is returning tool call syntax instead of executing tools.

**Fix:** This indicates CrewAI tool execution is broken. Check:
1. Tools are properly registered in agent's `_create_crew()`
2. LLM is properly configured for tool use
3. CrewAI version is compatible

### Issue: Tests Fail with "Custom thresholds not found"

**Cause:** Agent is not parsing instructions correctly.

**Fix:** Check:
1. Instructions are being passed to agent prompt
2. LLM prompt includes instruction emphasis
3. Tool parameters are extracted from instructions

### Issue: Tests Are Very Slow

**Solution:** Use test markers:
```bash
# Skip slow tests during development
pytest -m "not slow" -v

# Or only run unit tests (no LLM calls)
pytest -m unit -v
```

## CI/CD Integration

### GitHub Actions Example

```yaml
# .github/workflows/test.yml
name: Test Agents

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Start services
      run: docker-compose up -d
    
    - name: Run tests
      run: |
        docker-compose exec -T backend pytest -v \
          --cov=app.agents \
          --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v2
```

## Test Coverage Goals

| Component | Target | Current |
|-----------|--------|---------|
| Bias Agent | >80% | TBD |
| Strategy Agent | >80% | TBD |
| Risk Manager | >80% | TBD |
| Overall Agents | >75% | TBD |

## Best Practices

1. **Test with realistic data** - Use fixtures that simulate real market conditions
2. **Test both happy and sad paths** - Include edge cases and error conditions
3. **Use descriptive test names** - Name should explain what's being tested
4. **Keep tests isolated** - Each test should be independent
5. **Mock external dependencies** - Mock OpenAI API, database, etc. for unit tests
6. **Mark tests appropriately** - Use markers for organization and filtering
7. **Assert specific behavior** - Don't just check "not None", check actual values

## Future Enhancements

- [ ] Add performance benchmarks
- [ ] Add load/stress tests
- [ ] Mock OpenAI API for faster unit tests
- [ ] Add visual regression tests for charts
- [ ] Add integration tests with real pipeline execution
- [ ] Add mutation testing for robustness

## Troubleshooting

### Run a single test with full output
```bash
docker-compose exec backend pytest tests/test_bias_agent.py::TestBiasAgentAccuracy::test_custom_rsi_thresholds_40_60 -v -s
```

### Debug test failures
```bash
# Show full traceback
docker-compose exec backend pytest --tb=long

# Drop into debugger on failure
docker-compose exec backend pytest --pdb

# Show print statements
docker-compose exec backend pytest -s
```

### Check test collection
```bash
# List all tests without running
docker-compose exec backend pytest --collect-only
```

## Questions?

See:
- `conftest.py` for fixture details
- Individual test files for examples
- `/docs/context.md` for agent architecture

