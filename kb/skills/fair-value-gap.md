# Fair Value Gap (FVG)

## Definition

A Fair Value Gap (FVG) is a **3-candle formation** where the expansive middle candle creates a gap between the wicks of candles 1 and 3. This gap represents an imbalance in price delivery — an area where price moved so aggressively that it left behind an inefficiency. FVGs signal displacement and institutional intent.

## Formation Rules

### Bullish FVG
1. Candle 1: Any candle (the reference)
2. Candle 2: Large bullish candle with significant body
3. Candle 3: Any candle
4. **Gap**: The LOW of candle 3 is HIGHER than the HIGH of candle 1
5. The gap between candle 1's high and candle 3's low = the bullish FVG

### Bearish FVG
1. Candle 1: Any candle (the reference)
2. Candle 2: Large bearish candle with significant body
3. Candle 3: Any candle
4. **Gap**: The HIGH of candle 3 is LOWER than the LOW of candle 1
5. The gap between candle 1's low and candle 3's high = the bearish FVG

## Three Levels Inside an FVG

Every FVG has three critical levels:

| Level | Name | Fibonacci |
|-------|------|-----------|
| **FVG Open** | The nearest edge where price first enters the FVG | 0.0 |
| **Midpoint** | The 50% mark of the FVG range | 0.5 |
| **FVG Fill** | The far edge — complete fill of the gap | 1.0 |

## FVG Reaction Rules (Critical)

These three rules determine whether an FVG is valid, invalid, or inverted:

### Rule 1: Valid FVG — Continuation Expected
- Price taps into the FVG
- Price **fails to close beyond the midpoint (0.5)**
- → FVG is valid. Expect continuation in the original direction of the FVG.

### Rule 2: Invalid FVG — Wait
- Price enters the FVG
- Price **closes beyond the midpoint** but not through the entire FVG
- → FVG is invalid. Wait for the next FVG to form.

### Rule 3: Inversion — New Direction
- Price **closes completely through the FVG** from the opposite side
- → The FVG has been **inverted** (becomes an iFVG)
- → The old FVG now acts as support/resistance in the opposite direction
- See: [Inverse Fair Value Gap](inverse-fair-value-gap.md)

## Break Structure Gap (BSG)

A **BSG (Break Structure Gap)** is the FVG that forms when market structure is broken. BSGs are the **most important FVGs** as they are the lifeblood of a trend.

### BSG Rules
- Must follow the **consistency rule** (one-sided delivery — all candles in the same direction)
- If a BSG fails (opposing candle closes through it), look for the opposing swing point as a target
- A failed BSG can be used as an opposing level after inversion
- **BSG + Inflection Point = highest probability level**

## Inflection Points

Inflection points are found by extending the level of structure that was broken horizontally across the chart.

- When a swing high/low is broken, extend that level forward
- Where this level intersects with a BSG = **key confluence level**
- Expect displacement away from this level if the trend is genuine

## FVG Quality Filters

Not all FVGs are equal. Higher probability FVGs have:

| Quality Factor | High Probability | Low Probability |
|---------------|-----------------|----------------|
| **Count** | Single, clean FVG | Multiple FVGs in same leg |
| **Context** | Forms after liquidity sweep | Random formation |
| **Alignment** | In premium/discount zone | At equilibrium |
| **Displacement** | Large-body candle 2 | Small-body candle 2 |
| **One-sided delivery** | All candles same direction | Mixed candle directions |

### Clean vs Messy FVGs
- A **clean, singular FVG** is preferred — one FVG in an expansion leg
- **Multiple FVGs** in the same leg reduce accuracy and signal uncertainty
- If you see multiple FVGs, zoom out to a higher timeframe

## Uses of FVGs

1. **Higher Timeframe Levels**: HTF FVGs act as key support/resistance zones
2. **Directional Bias**: The direction of recent valid FVGs indicates bias
3. **Trade Entries**: Enter on retracement to FVG (limit order at FVG open or midpoint)
4. **Stop Losses**: Place stops beyond the FVG fill level
5. **Targets**: Unfilled FVGs ahead of price serve as targets (internal range liquidity)

## Agent Detection Logic

```
function detect_fvg(candles):
    fvgs = []
    for i in range(1, len(candles) - 1):
        candle_1 = candles[i - 1]
        candle_2 = candles[i]
        candle_3 = candles[i + 1]
        
        # Bullish FVG: candle 3 low > candle 1 high
        if candle_3.low > candle_1.high:
            fvg = BullishFVG(
                top=candle_3.low,
                bottom=candle_1.high,
                midpoint=(candle_3.low + candle_1.high) / 2,
                candle_index=i,
                timestamp=candle_2.timestamp
            )
            fvgs.append(fvg)
        
        # Bearish FVG: candle 3 high < candle 1 low
        if candle_3.high < candle_1.low:
            fvg = BearishFVG(
                top=candle_1.low,
                bottom=candle_3.high,
                midpoint=(candle_1.low + candle_3.high) / 2,
                candle_index=i,
                timestamp=candle_2.timestamp
            )
            fvgs.append(fvg)
    
    return fvgs

function evaluate_fvg_reaction(fvg, subsequent_candles):
    for candle in subsequent_candles:
        if fvg.type == BULLISH:
            if candle.close < fvg.midpoint:
                if candle.close < fvg.bottom:
                    return FVG_INVERTED  # Rule 3
                return FVG_INVALID       # Rule 2
            elif candle.low <= fvg.top:   # Price entered FVG
                return FVG_VALID          # Rule 1
        
        if fvg.type == BEARISH:
            if candle.close > fvg.midpoint:
                if candle.close > fvg.top:
                    return FVG_INVERTED  # Rule 3
                return FVG_INVALID       # Rule 2
            elif candle.high >= fvg.bottom:
                return FVG_VALID          # Rule 1
    
    return FVG_UNTESTED

function detect_bsg(candles, swing_points):
    """Detect Break Structure Gaps — FVGs that form at structure breaks."""
    fvgs = detect_fvg(candles)
    bsgs = []
    
    for fvg in fvgs:
        for swing in swing_points:
            # Check if FVG formed during a structure break
            if fvg.type == BULLISH and fvg.bottom >= swing.high:
                bsgs.append(BSG(fvg=fvg, broken_structure=swing))
            elif fvg.type == BEARISH and fvg.top <= swing.low:
                bsgs.append(BSG(fvg=fvg, broken_structure=swing))
    
    return bsgs
```
