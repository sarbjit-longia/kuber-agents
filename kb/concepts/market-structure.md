# Market Structure

## Definition

Market structure is the pattern of swing highs and swing lows that price creates over time. It is the foundation of all price action analysis. The key skill is knowing which highs and lows are significant, and having a practical method of identifying them.

## Swing Highs and Swing Lows

A **swing high** or **swing low** is a **3-candle formation**:
- **Swing High**: The middle candle has the highest high of the 3 candles
- **Swing Low**: The middle candle has the lowest low of the 3 candles

Every swing high and swing low should be noted on the chart.

## Bullish vs Bearish Structure

| Structure | Definition | Pattern |
|-----------|-----------|---------|
| **Bullish** | Higher highs (HH) and higher lows (HL) | Price making successively higher swing points |
| **Bearish** | Lower highs (LH) and lower lows (LL) | Price making successively lower swing points |

## Impulse Structure

Not all market structure is equal. **Impulse structure** is structure that forms with **displacement** and **fair value gaps (FVGs)**.

### Rules
- An impulse is a move that pushes **through** structure with displacement, not merely **to** structure
- One HTF impulse contains many LTF impulses
- Impulses can be used to confirm HTF zones
- **Only pay attention to structure that is impulse structure** — filter out non-impulsive moves using displacement vs manipulation analysis

### Displacement vs Manipulation
- **Displacement = Continuation**: Price pushes through structure and keeps going. Confirmed by FVGs forming in the move.
- **Manipulation = Reversal**: Price pushes through structure but reverses back. The move fails to displace beyond the level.

## One-Sided vs Two-Sided Price Delivery

| Type | Characteristics | Action |
|------|----------------|--------|
| **One-Sided** | Consistent candles, all same direction, displacement present | High probability to continue — trade with it |
| **Two-Sided** | Indecisive candles, mixed directions, no displacement | Low probability — look for nearest swing point as target |

## Multi-Timeframe Hierarchy (High Card Rules)

An impulse on a lower timeframe could be just a retracement of a higher timeframe impulse. **Higher timeframe structure always overrides lower timeframe structure.**

- Daily structure can be invalidated by weekly structure
- H1 structure can be invalidated by daily structure
- Always be aware of the HTF impulse context before trading LTF structure

## Break of Structure (BOS) vs Market Structure Shift (MSS)

| Event | Definition | Significance |
|-------|-----------|--------------|
| **BOS** | Price breaks a swing high/low in the direction of the current trend | Trend continuation confirmation |
| **MSS** | Price breaks a swing high/low **against** the current trend with displacement | Potential trend reversal signal |

An MSS must occur **with displacement** to be valid. An MSS without displacement is likely manipulation.

## Agent Detection Logic

```
function identify_swing_points(candles):
    swings = []
    for i in range(1, len(candles) - 1):
        if candles[i].high > candles[i-1].high and candles[i].high > candles[i+1].high:
            swings.append(SwingHigh(candles[i]))
        if candles[i].low < candles[i-1].low and candles[i].low < candles[i+1].low:
            swings.append(SwingLow(candles[i]))
    return swings

function determine_structure(swings):
    if last_high > prev_high and last_low > prev_low:
        return BULLISH
    if last_high < prev_high and last_low < prev_low:
        return BEARISH
    return RANGING

function detect_mss(candles, current_structure):
    if current_structure == BULLISH:
        # Look for candle closing below recent swing low with displacement
        if candle.close < recent_swing_low and has_displacement(candle):
            return MSS_BEARISH
    if current_structure == BEARISH:
        # Look for candle closing above recent swing high with displacement
        if candle.close > recent_swing_high and has_displacement(candle):
            return MSS_BULLISH
```
