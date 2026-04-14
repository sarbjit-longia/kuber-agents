# Unicorn Model

## Definition

The Unicorn Model is a precise entry model that combines three ICT concepts into one setup: a liquidity sweep (or SMT divergence), a breaker block, and a Fair Value Gap aligned with the breaker. It is considered one of the highest-probability setups when all three components align.

## 3-Step Process

### Step 1: Liquidity Sweep or SMT Divergence

Identify a liquidity purge:
- **Liquidity Sweep**: Price takes out an obvious swing high/low, equal highs/lows, or session liquidity
- **SMT Divergence**: A correlated instrument makes a new extreme while the trading instrument fails to (this also qualifies as the trigger)

After identifying, **wait** — do not enter immediately.

### Step 2: Identify the Breaker Block

A breaker block forms as part of the structure shift after the liquidity sweep:

**For Bearish Setup**:
- After buy-side liquidity is swept (highs taken), price reverses
- Identify the **lowest down-close candle** in the swing prior to the liquidity sweep
- This is the **bearish breaker block**
- Wait for price to retrace to this level

**For Bullish Setup**:
- After sell-side liquidity is swept (lows taken), price reverses
- Identify the **highest up-close candle** in the swing prior to the liquidity sweep
- This is the **bullish breaker block**
- Wait for price to retrace to this level

### Step 3: FVG in Alignment with Breaker

The entry trigger:
1. Identify a Fair Value Gap that **overlaps with or is within** the breaker block
2. The FVG must be in the direction of the expected move (aligned with the breaker)
3. Wait for price to retrace into this FVG for entry

**The sweet spot**: Where the breaker block and FVG overlap = the Unicorn entry zone.

## Entry Details

| Component | Detail |
|-----------|--------|
| **Entry** | Limit order at the FVG within the breaker block zone |
| **Stop Loss** | Beyond the breaker block extreme (high for bearish, low for bullish) + small buffer |
| **Take Profit** | Opposing liquidity pool or draw on liquidity |
| **Minimum R:R** | 2:1 or better |

## Why It's High Probability

The Unicorn Model stacks three independent confirmations:

1. **Liquidity Sweep / SMT**: Confirms institutional manipulation occurred
2. **Breaker Block**: Confirms structure has shifted (the old OB failed and flipped)
3. **FVG Alignment**: Confirms institutional displacement in the new direction

When all three align at the same price zone, the probability of a continuation move is very high.

## Bullish Unicorn Example

1. **Sell-side liquidity swept**: Price drops below equal lows at $100, reaching $99.50
2. **Price reverses**: Displacement upward, breaking above the recent swing high
3. **Bullish Breaker identified**: The highest up-close candle in the swing that preceded the sweep (around $100.50-$101.00)
4. **FVG forms**: A bullish FVG forms at $100.80-$101.20 as price displaces upward
5. **FVG overlaps breaker**: The FVG at $100.80-$101.20 sits within the breaker zone
6. **Entry**: Limit buy at $101.00. Stop at $99.40. Target: $104.00 (next buy-side liquidity)
7. **R:R**: $3.00 reward / $1.60 risk = 1.87:1

## Bearish Unicorn Example

1. **Buy-side liquidity swept**: Price rises above equal highs at $200, reaching $200.80
2. **Price reverses**: Displacement downward, breaking below the recent swing low
3. **Bearish Breaker identified**: The lowest down-close candle in the swing preceding the sweep (around $199.50-$199.00)
4. **FVG forms**: A bearish FVG at $199.20-$199.50
5. **FVG overlaps breaker**: Confluence zone at $199.20-$199.50
6. **Entry**: Limit sell at $199.40. Stop at $200.90. Target: $196.00
7. **R:R**: $3.40 / $1.50 = 2.27:1

## For Opposite Bias

The model is symmetrical — inverse all diagrams and conditions for the opposite direction.

## Agent Detection Logic

```
function detect_unicorn_model(candles, swing_points, liquidity_levels):
    signals = []
    
    # Step 1: Find liquidity sweeps
    sweeps = []
    for liq in liquidity_levels:
        sweep = detect_liquidity_sweep(candles, liq)
        if sweep:
            sweeps.append(sweep)
    
    for sweep in sweeps:
        # Step 2: Find breaker block after the sweep
        post_sweep_candles = get_candles_after(candles, sweep.timestamp)
        breakers = detect_breaker_blocks(post_sweep_candles, swing_points)
        
        for breaker in breakers:
            # Step 3: Find FVG overlapping with breaker
            fvgs = detect_fvg(post_sweep_candles)
            
            for fvg in fvgs:
                # Check if FVG overlaps with breaker block
                overlap = calculate_overlap(
                    (breaker.low, breaker.high),
                    (fvg.bottom, fvg.top)
                )
                
                if overlap > 0:
                    # Unicorn setup found!
                    entry_zone_low = max(breaker.low, fvg.bottom)
                    entry_zone_high = min(breaker.high, fvg.top)
                    
                    if breaker.type == BULLISH:
                        entry = entry_zone_low  # Buy at bottom of overlap
                        stop = breaker.low - buffer
                        direction = BULLISH
                    else:
                        entry = entry_zone_high  # Sell at top of overlap
                        stop = breaker.high + buffer
                        direction = BEARISH
                    
                    target = find_opposing_liquidity(liquidity_levels, entry, direction)
                    risk = abs(entry - stop)
                    reward = abs(target.price - entry)
                    
                    if reward / risk >= 2.0:
                        signals.append(UnicornSignal(
                            direction=direction,
                            entry=entry,
                            stop_loss=stop,
                            take_profit=target.price,
                            r_multiple=reward / risk,
                            sweep=sweep,
                            breaker=breaker,
                            fvg=fvg,
                            overlap_zone=(entry_zone_low, entry_zone_high)
                        ))
    
    return signals
```
