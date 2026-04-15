---
skill_id: kb_skill_inverse_fair_value_gap
name: Inverse Fair Value Gap
category: ict
agent_types: [strategy_agent, bias_agent]
recommended_tools: [fvg_detector, market_structure, liquidity_analyzer]
tags: [ict, ifvg, inversion, continuation]
---

# Inverse Fair Value Gap (iFVG)

## Definition

An Inverse Fair Value Gap (iFVG) is a standard FVG that has been **inverted** — price has closed back through the FVG from the opposite direction. This transforms the original gap into a support/resistance zone with flipped polarity. iFVGs are powerful continuation signals.

## Formation Sequence

### Step 1: FVG Forms
A standard FVG forms during a directional move (e.g., a bearish FVG during a down move).

### Step 2: Price Reverses Through
Price reverses and **closes** back through the FVG from the opposite direction. The close must be on the same timeframe as the FVG.

### Step 3: Inversion Complete
The original FVG is now an iFVG with flipped role:
- A **bearish FVG** that price closes back up through → **Bullish iFVG** (now acts as support)
- A **bullish FVG** that price closes back down through → **Bearish iFVG** (now acts as resistance)

## Types

### Bullish iFVG
- **Origin**: A bearish FVG (gap created during a down move)
- **Trigger**: Price closes back UP through the bearish FVG
- **New Role**: Support — expect price to find buyers here on retests
- **Trade**: Look for longs on retrace to the iFVG level

### Bearish iFVG
- **Origin**: A bullish FVG (gap created during an up move)
- **Trigger**: Price closes back DOWN through the bullish FVG
- **New Role**: Resistance — expect price to find sellers here on retests
- **Trade**: Look for shorts on retrace to the iFVG level

## High Probability iFVG Conditions

Not all iFVGs are equal. The highest probability iFVGs occur:

| Condition | Why It Matters |
|-----------|---------------|
| At **two-sided gaps** | Shows genuine institutional activity from both directions |
| At **Break Structure Gaps (BSGs)** | BSGs are the strongest FVGs; their inversion is highly significant |
| **After a liquidity sweep** | Sweep + inversion = smart money reversal |
| With **SMT divergence** confirmation | Adds correlated-asset confirmation |
| **Clean, singular FVG** that inverts | Multiple FVGs reduce reliability |

## iFVG Trading Model (Complete Strategy)

**Instruments**: NQ, ES (index futures)
**Timeframe**: 1M, 2M, 3M, or 5M for entries; 4H/1H for bias
**Session**: NY Session

### Step 1 — Context (Bias Setup)
- Start with the 4H or 1H chart
- Determine overall direction (bullish or bearish)
- Identify the draw on liquidity: are we targeting highs or lows?
- Mark key swing highs/lows and session opens

### Step 2 — Liquidity Sweep
- Wait for a clear sweep of an obvious internal high or low
- Must be clean, obvious, market-structure-based liquidity
- SMT divergence after the sweep significantly increases probability

### Step 3 — FVG Formation
- Look for a clean FVG forming after the sweep
- Prefer a single, isolated FVG (multiple FVGs in the leg = avoid or zoom out)

### Step 4 — The Inversion (Confirmation)
- Wait for price to close back through the FVG from the opposite direction
- This transforms the FVG into an iFVG
- The candle close **must be on the same timeframe** as the inversion (e.g., a 3M iFVG needs a 3M close through it)

### Step 5 — Entry
- **Option A**: Limit order at the iFVG level (wait for retrace)
- **Option B**: Market entry on candle closure through the iFVG if there is clear displacement
- Use the same timeframe for entry as the inversion

### Step 6 — Targets
- **First target**: Internal liquidity (recent internal high or low)
- **Final target**: Major swing high/low or draw on liquidity

### Stop Loss
Below the FVG (for bullish iFVG) or above the FVG (for bearish iFVG), or at the low/high of the expansion leg.

### Breakeven Rule
If the first internal liquidity target is hit and no further displacement occurs, move stop to breakeven to protect capital.

## Trade Checklist

1. [ ] HTF bias confirmed (draw on liquidity identified)
2. [ ] Clear liquidity sweep occurred
3. [ ] SMT divergence for extra confirmation (optional but high confluence)
4. [ ] Clean, singular FVG formed after the sweep
5. [ ] Price closed back through the FVG (activating the inversion)
6. [ ] Entry on retrace to iFVG with proper structure
7. [ ] Stop loss below the FVG or low of the expansion leg
8. [ ] First target at internal liquidity
9. [ ] Move stop to breakeven after first target hit

## Agent Detection Logic

```
function detect_ifvg(candles, existing_fvgs):
    ifvgs = []
    
    for fvg in existing_fvgs:
        # Check if any subsequent candle closes through the FVG
        fvg_candles = get_candles_after(candles, fvg.timestamp)
        
        for candle in fvg_candles:
            if fvg.type == BEARISH:
                # Bearish FVG inverted = bullish iFVG
                if candle.close > fvg.top:  # Close above the FVG
                    ifvg = BullishIFVG(
                        level=fvg.top,       # Top of old bearish FVG = new support
                        range_top=fvg.top,
                        range_bottom=fvg.bottom,
                        inversion_candle=candle,
                        original_fvg=fvg
                    )
                    ifvgs.append(ifvg)
                    break
            
            elif fvg.type == BULLISH:
                # Bullish FVG inverted = bearish iFVG
                if candle.close < fvg.bottom:  # Close below the FVG
                    ifvg = BearishIFVG(
                        level=fvg.bottom,    # Bottom of old bullish FVG = new resistance
                        range_top=fvg.top,
                        range_bottom=fvg.bottom,
                        inversion_candle=candle,
                        original_fvg=fvg
                    )
                    ifvgs.append(ifvg)
                    break
    
    return ifvgs

function score_ifvg(ifvg, context):
    score = 0
    
    if context.after_liquidity_sweep:
        score += 3  # High value
    if context.at_bsg:
        score += 3  # BSG inversions are strongest
    if context.smt_divergence:
        score += 2  # Correlated confirmation
    if context.single_fvg_in_leg:
        score += 2  # Clean setup
    if context.in_premium_discount_zone:
        score += 1  # Aligned with institutional logic
    
    return score  # Max 11; trade if >= 5
```
