# Test Output Example

## Running Tests with `-s` Flag (Verbose)

When you run tests with the `-s` flag, you'll see detailed output for each test:

```bash
docker-compose exec backend pytest tests/test_bias_agent.py::TestBiasAgentAccuracy::test_custom_rsi_thresholds_40_60 -v -s
```

## Example Output:

```
================================================================================
TEST: Custom RSI Thresholds (40/60)
================================================================================

📋 INPUT:
--------------------------------------------------------------------------------
Instructions: Using RSI on daily timeframe determine if the bias is bullish, bearish or neutral. Use RSI thresholds of 40 and 60 (oversold below 40, overbought above 60).
Model: lm-studio

🤖 LLM OUTPUT:
--------------------------------------------------------------------------------

[1d] Bias: NEUTRAL
[1d] Confidence: 75%
[1d] Reasoning:
Based on technical analysis using RSI indicator on daily timeframe:

**MARKET ANALYSIS:**
Current RSI reading: 42.8

The RSI value of 42.8 falls within the neutral zone (between 40 and 60 thresholds as specified). This indicates:
• No oversold condition (would need RSI < 40)
• No overbought condition (would need RSI > 60)
• Market is in equilibrium with balanced buying and selling pressure

**KEY FACTORS:**
• RSI at 42.8 shows neutral momentum
• Price action not at extreme levels
• Using custom thresholds: oversold=40, overbought=60

**BIAS DETERMINATION:**
Given the RSI reading between our specified thresholds, the current market bias is NEUTRAL.
[1d] Key Factors: RSI momentum, Volume confirmation, Trend strength

✅ EXPECTED vs ❓ ACTUAL:
--------------------------------------------------------------------------------
✅ reasoning_contains: Expected=40, Actual=Contains '40': True
✅ reasoning_not_contains: Expected=30, Actual=NOT Contains '30': True

================================================================================

PASSED                                                                   [100%]
```

## Benefits:

### 1. **Visual Verification**
You can SEE exactly what the LLM generated vs what you expected.

### 2. **Debug Failures Quickly**
When a test fails, you immediately see:
- What instructions were sent
- What the LLM actually returned
- Which part of the output doesn't match expectations

### 3. **Validate Reasoning Quality**
You can manually assess if the LLM's reasoning makes sense, even if the test passes.

### 4. **Compare Across Runs**
Run the same test multiple times and compare LLM outputs to check consistency.

## Example Failure Output:

```
================================================================================
TEST: Custom RSI Thresholds (40/60)
================================================================================

📋 INPUT:
--------------------------------------------------------------------------------
Instructions: Using RSI on daily timeframe determine if the bias is bullish, bearish or neutral. Use RSI thresholds of 40 and 60 (oversold below 40, overbought above 60).
Model: lm-studio

🤖 LLM OUTPUT:
--------------------------------------------------------------------------------

[1d] Bias: BULLISH
[1d] Confidence: 80%
[1d] Reasoning:
Based on RSI analysis using standard thresholds (30/70), the current RSI of 65 
indicates bullish momentum. The indicator shows the market is approaching 
overbought conditions at the traditional 70 threshold...

✅ EXPECTED vs ❓ ACTUAL:
--------------------------------------------------------------------------------
❓ reasoning_contains: Expected=40, Actual=Contains '40': False
❓ reasoning_not_contains: Expected=30, Actual=NOT Contains '30': False

================================================================================

FAILED - Agent used default thresholds (30/70) instead of custom (40/60)!
```

## Strategy Agent Example:

```
================================================================================
TEST: Bull Flag Pattern Detection
================================================================================

📋 INPUT:
--------------------------------------------------------------------------------
Instructions: Look for bull flag patterns on 5m timeframe. Enter on breakout with 2:1 R/R
Model: lm-studio
Timeframe: 5m

🤖 LLM OUTPUT:
--------------------------------------------------------------------------------

Action: BUY
Entry: $258.50
Stop Loss: $257.00
Take Profit: $261.50
Confidence: 75%
Pattern: Bull Flag

Reasoning:
**MARKET STRUCTURE:**
Clear uptrend with higher highs and higher lows. Price consolidated in a tight 
flag pattern between $257.50-$258.50 for the last 20 candles.

**PATTERNS IDENTIFIED:**
• Bull flag pattern identified with flagpole from $252 to $259
• Breakout above $258.50 resistance confirms continuation
• Volume decreased during consolidation (flag), increased on breakout

**ENTRY RATIONALE:**
Entry at $258.50 captures the breakout with confirmation. This aligns with the 
top of the flag pattern and shows bullish momentum continuation.

**EXIT STRATEGY:**
Stop loss at $257.00 (1.5 points) below the flag support protects against false 
breakout. Take profit at $261.50 (3 points) gives 2:1 risk/reward as requested.

**RISK FACTORS:**
• Potential false breakout if volume doesn't sustain
• Resistance at $260 could slow momentum

✅ EXPECTED vs ❓ ACTUAL:
--------------------------------------------------------------------------------
✅ action: Expected=BUY, Actual=BUY
✅ has_entry: Expected=True, Actual=Entry: $258.50

================================================================================

PASSED                                                                   [100%]
```

## Usage Tips:

### Always use `-s` when debugging:
```bash
# Debugging single test
pytest tests/test_bias_agent.py::test_custom_rsi_thresholds_40_60 -v -s

# Debugging all accuracy tests
pytest tests/ -m accuracy -v -s

# Debugging specific agent
pytest tests/test_strategy_agent.py -v -s
```

### Capture output to file:
```bash
pytest tests/test_bias_agent.py -v -s > test_output.txt 2>&1
```

### Compare two test runs:
```bash
# Run 1
pytest tests/test_bias_agent.py -v -s > run1.txt 2>&1

# Run 2
pytest tests/test_bias_agent.py -v -s > run2.txt 2>&1

# Compare
diff run1.txt run2.txt
```

## What Gets Printed:

### For Bias Agent Tests:
- ✅ Instructions sent to agent
- ✅ Model used (lm-studio, gpt-4, etc.)
- ✅ Bias determined (BULLISH/BEARISH/NEUTRAL)
- ✅ Confidence level
- ✅ Full reasoning text
- ✅ Key factors identified
- ✅ Expected values vs actual values

### For Strategy Agent Tests:
- ✅ Instructions + timeframe
- ✅ Action (BUY/SELL/HOLD)
- ✅ Entry, Stop Loss, Take Profit prices
- ✅ Pattern detected
- ✅ Full reasoning with market structure
- ✅ Chart annotations (if any)

### For Risk Manager Tests:
- ✅ Risk rules/instructions
- ✅ Approved/Rejected decision
- ✅ Position size calculated
- ✅ Risk amount
- ✅ R/R ratio
- ✅ Full risk assessment reasoning

---

**This makes testing feel more like a conversation with the AI!** 🎯

