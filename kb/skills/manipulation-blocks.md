---
skill_id: kb_skill_manipulation_blocks
name: Manipulation Blocks
category: ict
agent_types: [strategy_agent, bias_agent]
recommended_tools: [liquidity_analyzer, market_structure, fvg_detector, premium_discount]
tags: [ict, manipulation, liquidity, reversal]
---

# Manipulation Blocks

## Definition

A Manipulation Block (MB) is the candle that **closes beyond a liquidity level** during a manipulative move. It is NOT the candle that wicks through liquidity — it is specifically the candle whose **body closes past** the liquidity level. This candle represents institutional manipulation: large players pushing price through obvious levels to trigger stop losses before reversing.

## Types

### Bearish Manipulation Block
- An **up-close (bullish) candle** that closes above a previous high during a manipulation event
- After this candle, price reverses and moves lower
- The MB candle becomes a key level for targeting

### Bullish Manipulation Block
- A **down-close (bearish) candle** that closes below a previous low during a manipulation event
- After this candle, price reverses and moves higher
- The MB candle becomes a key level for targeting

## Identification Rules

### Step 1: Identify the Liquidity Level
Find obvious liquidity (swing high/low, equal highs/lows, session high/low, previous day high/low).

### Step 2: Watch for the Close Beyond
Wait for a candle to **close** beyond the liquidity level:
- For bearish MB: A candle closes above the previous high
- For bullish MB: A candle closes below the previous low

**Important**: The candle that just wicks through is NOT the manipulation block. The MB is the candle with the body closure beyond the level.

### Step 3: Confirm Lack of Displacement
The move beyond the liquidity should show characteristics of manipulation, not displacement:
- No continuation follow-through
- No FVGs forming in the extension direction
- Price stalls or immediately reverses

## Activation

A Manipulation Block is **activated** when the market **engulfs and displaces past the opening price** of the Manipulation Block:
- For bearish MB: Price must close below the MB candle's open with displacement
- For bullish MB: Price must close above the MB candle's open with displacement

Only after activation is the MB a valid trading reference.

## Fibonacci Targets from Manipulation Blocks

Anchor a Fibonacci extension from the High and Low of the Manipulation Block:

| Fib Level | Usage |
|-----------|-------|
| -0.5 | Intermediate reference point |
| -0.75 | Intermediate reference point |
| -1.0 | First extension (equal to MB range) |
| **-2.0 to -2.5** | **Target 1**: Look for liquidity or PD array here |
| **-4.0** | **Target 2**: Extended target for full moves |

### Target Selection
- **Target 1**: Liquidity or PD array between -2 to -2.5 standard deviations of the MB
- **Target 2**: Liquidity or PD array at -4 standard deviations of the MB
- Always look for confluence — the fib level that aligns with an actual liquidity pool or PD array

## 4-Step Manipulation Block Strategy

### Step 1: Identify HTF Key Level
Find a higher timeframe key level — FVG, order block, or significant support/resistance on 1H/4H/Daily.

### Step 2: Wait for Liquidity Sweep + Body Close
Wait for:
- A liquidity sweep at the key level
- A candle body closing BEYOND the liquidity into the HTF key level
- This candle = the Manipulation Block

### Step 3: Enter on Activation
Enter the trade once the MB is activated (price engulfs and displaces past the MB's opening price in the opposite direction).

### Step 4: Stop Loss and Targets
- **Stop Loss**: At the low (for longs) or high (for shorts) of the Manipulation Block
- **Take Profit**: Use the Fibonacci projection method above
  - Target 1: -2 to -2.5 SD
  - Target 2: -4 SD

## Agent Detection Logic

```
function detect_manipulation_block(candles, liquidity_levels):
    mbs = []
    
    for liq in liquidity_levels:
        for i, candle in enumerate(candles):
            if liq.type == BUYSIDE:  # Liquidity above (highs)
                # Bearish MB: candle closes above the liquidity
                if candle.close > liq.price and candle.close > candle.open:
                    # Check if subsequent candles reverse
                    if has_reversal_after(candles, i, direction=BEARISH):
                        mb = BearishMB(
                            high=candle.high,
                            low=candle.low,
                            open=candle.open,
                            close=candle.close,
                            liquidity_level=liq,
                            candle_index=i
                        )
                        mbs.append(mb)
            
            elif liq.type == SELLSIDE:  # Liquidity below (lows)
                # Bullish MB: candle closes below the liquidity
                if candle.close < liq.price and candle.close < candle.open:
                    if has_reversal_after(candles, i, direction=BULLISH):
                        mb = BullishMB(
                            high=candle.high,
                            low=candle.low,
                            open=candle.open,
                            close=candle.close,
                            liquidity_level=liq,
                            candle_index=i
                        )
                        mbs.append(mb)
    
    return mbs

function check_mb_activation(mb, subsequent_candles):
    for candle in subsequent_candles:
        if mb.type == BEARISH:
            # Price must close below MB's open with displacement
            if candle.close < mb.open and has_displacement(candle):
                return ACTIVATED
        elif mb.type == BULLISH:
            if candle.close > mb.open and has_displacement(candle):
                return ACTIVATED
    return NOT_ACTIVATED

function calculate_mb_targets(mb):
    mb_range = mb.high - mb.low
    
    if mb.type == BEARISH:
        target_1 = mb.low - (mb_range * 2.0)   # -2 SD
        target_1b = mb.low - (mb_range * 2.5)   # -2.5 SD
        target_2 = mb.low - (mb_range * 4.0)    # -4 SD
    elif mb.type == BULLISH:
        target_1 = mb.high + (mb_range * 2.0)
        target_1b = mb.high + (mb_range * 2.5)
        target_2 = mb.high + (mb_range * 4.0)
    
    return {"target_1": (target_1, target_1b), "target_2": target_2}
```
