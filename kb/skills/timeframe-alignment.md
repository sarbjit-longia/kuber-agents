---
skill_id: kb_skill_timeframe_alignment
name: Timeframe Alignment
category: confluence
agent_types: [strategy_agent, bias_agent]
recommended_tools: [market_structure, premium_discount, rsi, macd]
tags: [ict, timeframe, alignment, bias]
---

# Timeframe Alignment

## Definition

Timeframe alignment is the practice of using specific timeframe pairs based on your trading style, where the higher timeframe provides the key level and narrative, and the lower timeframe provides structure and entries. Proper alignment prevents conflicting signals and ensures your entries are in sync with the dominant market direction.

## Alignment Matrix

| Trading Style | HTF (Key Levels & Narrative) | LTF (Structure & Entries) |
|--------------|------------------------------|---------------------------|
| **Position Trades** | Monthly | Weekly / Daily |
| **Swing Trades** | Daily | 4H / 1H |
| **Short-Term Trades** | 4H | 1H / M15 |
| **Intraday Trades** | 1H | M15 / M5 |

## Recommended Timeframe Combinations

Use **no more than 3 timeframes** at a time:

| Combination | Style |
|------------|-------|
| Weekly → H4 → H1 | Swing trading |
| Daily → H4 → M15 | Short-term swing |
| Daily → H1 → M5 | Intraday with daily context |
| Daily → H1 → M1 | Precision intraday |
| Daily → M15 → M1 | Scalping with daily context |

## Hierarchy (HTF → LTF Pairing)

Each timeframe has a natural "LTF" partner:

| HTF | Natural LTF |
|-----|-------------|
| Monthly | Daily |
| Weekly | H4 |
| Daily | H1 |
| H4 | M15 |
| H1 | M5 |
| M15 | M1 |

## 2-Step Application

### Step 1: Identify HTF Key Levels
On the higher timeframe, identify:
- Fair Value Gaps (FVGs)
- Draw on Liquidity (equal highs/lows, swing points)
- Order Blocks and Breaker Blocks
- The directional narrative (bullish or bearish bias)

### Step 2: Drop to LTF for Structure & Entries
Within the HTF key levels, look for LTF patterns:
- **Market Maker Models (MMXM)** — the most common LTF pattern within HTF levels
- **ICT 2022 Model** — liquidity sweep → MSS → FVG entry
- **Unicorn Model** — liquidity sweep → breaker block → FVG alignment
- **Silver Bullet** — time-based FVG entry
- **Market Structure Shifts (MSS)** — trend change confirmation on LTF

## Fractal Principle

Price is fractal. Any HTF → LTF breakdown can be further broken down:
- **HTF** → LTF → the LTF of the LTF

Example:
- Daily FVG identified (HTF key level)
- H1 shows a Market Maker Model forming within the daily FVG (LTF structure)
- M5 shows a Market Structure Shift within the H1 MMXM (entry timeframe)

This fractal nesting creates the highest-probability setups — an MMXM forming within an MMXM.

## Rules

### Rule 1: HTF Always Wins
Higher timeframe structure overrides lower timeframe structure. A bullish daily impulse means H1 bearish structure is just a retracement, not a new trend.

### Rule 2: Maximum 3 Timeframes
Using too many timeframes creates conflicting signals. Pick your HTF, LTF, and entry TF — that's it.

### Rule 3: Clean Charts
Remove indicators and clutter. The three timeframes should each serve a clear purpose:
1. **HTF**: Where is price going? (Narrative)
2. **LTF**: Where is the setup forming? (Structure)
3. **Entry TF**: Where do I enter? (Precision)

### Rule 4: Use Daily/Weekly as Foundation
Always use daily and weekly impulses as the foundational reference, regardless of your trading style. Even scalpers should know the daily and weekly bias.

## Agent Detection Logic

```
function get_timeframe_alignment(trading_style):
    alignments = {
        "position": {"htf": "monthly", "ltf": "weekly", "entry": "daily"},
        "swing": {"htf": "daily", "ltf": "4h", "entry": "1h"},
        "short_term": {"htf": "4h", "ltf": "1h", "entry": "15m"},
        "intraday": {"htf": "1h", "ltf": "15m", "entry": "5m"},
        "scalp": {"htf": "15m", "ltf": "5m", "entry": "1m"}
    }
    return alignments[trading_style]

function check_alignment(htf_bias, ltf_structure, entry_signal):
    """
    Verify all timeframes are aligned before taking a trade.
    """
    if htf_bias == NEUTRAL:
        return False, "No clear HTF bias"
    
    if ltf_structure.direction != htf_bias:
        return False, "LTF structure conflicts with HTF bias"
    
    if entry_signal.direction != htf_bias:
        return False, "Entry signal conflicts with HTF bias"
    
    return True, "All timeframes aligned"

function analyze_multi_timeframe(candles_by_tf, trading_style):
    alignment = get_timeframe_alignment(trading_style)
    
    # HTF Analysis
    htf_candles = candles_by_tf[alignment["htf"]]
    htf_bias = determine_daily_bias(htf_candles)
    htf_key_levels = find_key_levels(htf_candles)  # FVGs, OBs, liquidity
    
    # LTF Analysis (within HTF key levels)
    ltf_candles = candles_by_tf[alignment["ltf"]]
    ltf_structure = detect_market_maker_model(ltf_candles, htf_key_levels)
    
    # Entry TF Analysis (within LTF structure)
    entry_candles = candles_by_tf[alignment["entry"]]
    entry_signal = detect_mss(entry_candles, ltf_structure.current_phase)
    
    aligned, reason = check_alignment(htf_bias, ltf_structure, entry_signal)
    
    return {
        "htf_bias": htf_bias,
        "ltf_structure": ltf_structure,
        "entry_signal": entry_signal,
        "aligned": aligned,
        "reason": reason
    }
```
