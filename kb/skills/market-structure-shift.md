---
skill_id: kb_skill_market_structure_shift
name: Market Structure Shift
category: ict
agent_types: [strategy_agent, bias_agent]
recommended_tools: [market_structure, fvg_detector, liquidity_analyzer]
tags: [ict, mss, cisd, structure]
---

# Market Structure Shift (MSS)

## Definition

A Market Structure Shift (MSS) is a break and close through a recent swing high (bullish MSS) or swing low (bearish MSS) that signals a change in the short-term trend direction. MSS is the primary confirmation signal for entries on lower timeframes. Also referred to as Market Structure Break (MSB) or Change in State of Delivery (CISD).

## Types

### Bullish MSS
- Price breaks and closes **above** a recent swing high in a previously bearish structure
- Signals shift from bearish to bullish
- Look for this after a sell-side liquidity sweep in a bullish HTF context

### Bearish MSS
- Price breaks and closes **below** a recent swing low in a previously bullish structure
- Signals shift from bullish to bearish
- Look for this after a buy-side liquidity sweep in a bearish HTF context

## Validation Rules

### Must Have Displacement
An MSS is **only valid when accompanied by displacement**:
- The candle(s) breaking the swing point must be large-bodied, close strongly through the level
- FVGs should form in the break
- Without displacement, the break is likely manipulation (a stop hunt) rather than a genuine MSS

### MSS Without Displacement = Manipulation
If price breaks a swing point but:
- The candle only wicks through (doesn't close through)
- No FVGs form
- Price immediately reverses

→ This is manipulation, NOT a valid MSS. Expect price to reverse.

## Change in State of Delivery (CISD)

CISD is the broader concept that encompasses MSS. It occurs when:
- An **M15** candle closes above/below a breaker block → Start of intraday order flow shift
- An **M30-H1** candle confirms → High-quality confirmation
- An **H1-H4** candle confirms → Start of HTF order flow change

### CISD Hierarchy
| Timeframe | Significance |
|-----------|-------------|
| M15 | Intraday order flow shift |
| M30-H1 | High-quality intraday confirmation |
| H1-H4 | HTF order flow change |
| Daily | Major trend shift |

## Where MSS Is Most Significant

| Context | Probability |
|---------|------------|
| After a liquidity sweep at a HTF key level | Highest |
| At an HTF FVG or order block | High |
| During a killzone (01:30-04:30 or 07:30-10:30 EST) | High |
| With SMT divergence confirmation | Very high |
| Random MSS without HTF context | Low — avoid |

## MSS as Entry Confirmation

MSS on the lower timeframe (LTF) is the **required** entry confirmation in the ICT methodology:

### Step 1: HTF Bias
Determine direction from HTF (Daily, H4, H1)

### Step 2: Wait for Manipulation
Wait for price to sweep liquidity against the bias (manipulation phase)

### Step 3: Drop to LTF
Switch to M5 or M1

### Step 4: Wait for MSS
Look for an MSS in the direction of your HTF bias:
- For bullish: MSS above a recent M5/M1 swing high
- For bearish: MSS below a recent M5/M1 swing low

### Step 5: Enter
- **Option A**: Enter immediately on the MSS candle close
- **Option B**: Wait for the FVG that forms in the MSS, enter on retrace to FVG
- **Stop loss**: Beyond the swing point that was just created by the manipulation

## Entry Checklist Integration

MSS is always required (item #5) in the ICT entry checklist:

1. HTF bias = LTF bias (optional but preferred)
2. HTF IRL/ERL = LTF MMXM (optional but preferred)
3. Manipulation beyond session open / TBL swept (optional but preferred)
4. HTF key level (optional but preferred)
5. **LTF MSS with displacement (REQUIRED)**

You need **2+ of items 1-4** plus the **required MSS** to have a valid entry.

## Agent Detection Logic

```
function detect_mss(candles, current_structure, lookback=20):
    """
    Detect Market Structure Shift on the given candle series.
    current_structure: BULLISH or BEARISH (the prevailing trend)
    """
    swings = identify_swing_points(candles[-lookback:])
    mss_signals = []
    
    for i, candle in enumerate(candles):
        if current_structure == BEARISH:
            # Look for bullish MSS: close above recent swing high
            recent_swing_high = get_most_recent_swing_high(swings, before=candle.timestamp)
            if recent_swing_high and candle.close > recent_swing_high.price:
                if has_displacement(candle):
                    fvg = detect_fvg_at(candles, i)  # Check for FVG forming
                    mss_signals.append(BullishMSS(
                        candle=candle,
                        broken_level=recent_swing_high.price,
                        displacement=True,
                        fvg=fvg,
                        candle_index=i
                    ))
        
        elif current_structure == BULLISH:
            # Look for bearish MSS: close below recent swing low
            recent_swing_low = get_most_recent_swing_low(swings, before=candle.timestamp)
            if recent_swing_low and candle.close < recent_swing_low.price:
                if has_displacement(candle):
                    fvg = detect_fvg_at(candles, i)
                    mss_signals.append(BearishMSS(
                        candle=candle,
                        broken_level=recent_swing_low.price,
                        displacement=True,
                        fvg=fvg,
                        candle_index=i
                    ))
    
    return mss_signals

function validate_mss(mss, htf_bias, context):
    """Score an MSS signal for trade quality."""
    score = 0
    
    if mss.displacement:
        score += 3  # Required — without this, MSS is invalid
    if mss.fvg:
        score += 2  # FVG in the break = strong confirmation
    if mss.direction == htf_bias:
        score += 2  # Aligned with HTF
    if context.after_liquidity_sweep:
        score += 3  # Post-sweep MSS = highest probability
    if context.in_killzone:
        score += 1  # During active session
    if context.at_htf_key_level:
        score += 2  # At FVG, OB, or breaker on HTF
    
    return score  # Trade if >= 7 (out of 13)
```
