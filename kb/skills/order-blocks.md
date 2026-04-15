---
skill_id: kb_skill_order_blocks
name: Order Blocks
category: ict
agent_types: [strategy_agent, bias_agent]
recommended_tools: [liquidity_analyzer, market_structure, premium_discount]
tags: [ict, order-block, displacement, liquidity]
---

# Order Blocks

## Definition

An Order Block (OB) is the last opposing candle before an expansive displacement move. It represents the price level where institutional orders were placed. When price returns to this level, it often reacts as the resting orders provide support or resistance.

## Types

### Bullish Order Block
- The **lowest candle with a DOWN close** (bearish candle) before a strong bullish displacement
- Must have the **most range between open and close** compared to nearby down-close candles
- Located near a support level
- When price returns to this level, expect it to act as support (buyers)

### Bearish Order Block
- The **highest candle with an UP close** (bullish candle) before a strong bearish displacement
- Must have the **most range between open and close** compared to nearby up-close candles
- Located near a resistance level
- When price returns to this level, expect it to act as resistance (sellers)

## Identification Rules

### Step 1: Find Displacement
Look for an aggressive, impulsive move that creates FVGs:
- Bullish displacement: Large bullish candles, closes through highs
- Bearish displacement: Large bearish candles, closes through lows

### Step 2: Identify the Order Block Candle
Go back to just before the displacement and find:
- **Bullish OB**: The last bearish (down-close) candle before the bullish move
- **Bearish OB**: The last bullish (up-close) candle before the bearish move

### Step 3: Mark the Zone
Two approaches:
- **Conservative**: Mark from the candle's open to its close (body only)
- **Aggressive**: Mark from the candle's high to its low (full range including wicks)

**Recommendation**: Use candle bodies (open to close) as wicks vary between brokers.

## Validation / Activation

An order block is **validated (activated)** when its extreme is traded through by a subsequent candle:
- **Bullish OB**: Validated when a candle trades below the OB's low (sweeps it) then reverses up
- **Bearish OB**: Validated when a candle trades above the OB's high (sweeps it) then reverses down

## Mean Threshold Rule

Use a Fibonacci tool to measure the OB candle's open and close. The **mean threshold is the 50% level**.

| Order Block | Rule |
|------------|------|
| **Bullish OB** | Price should NOT close below the mean threshold (50%). If it does, the OB is likely invalidated. |
| **Bearish OB** | Price should NOT close above the mean threshold (50%). If it does, the OB is likely invalidated. |

## Order Block Variants

### Mitigation Block
When price breaks structure and shifts direction, the trapped side's last candle before the shift becomes a mitigation block. Traders who were wrong will look to exit (mitigate losses) when price returns to this level.

- **Bearish Mitigation Block**: Last down-close candle inside a failed bullish move. When price returns, trapped longs exit → selling pressure.
- **Bullish Mitigation Block**: Last up-close candle inside a failed bearish move. When price returns, trapped shorts exit → buying pressure.

### Rejection Block
Formed when two consecutive candles create long wicks beyond a level, showing rejection.

- **Bearish Rejection Block**: Two long upper wicks at a high → price cleared buy-side liquidity and rejected. Sell trigger: price trades back to the low of the rejection block range. Stop: above highest wick.
- **Bullish Rejection Block**: Two long lower wicks at a low → price cleared sell-side liquidity and rejected. Buy trigger: price trades back to the high of the rejection block range. Stop: below lowest wick.

### Reclaimed Order Block
Within Market Maker Models, OBs from the sell-side of the curve get "reclaimed" on the buy-side, and vice versa.

- **Bullish Reclaimed OB**: A candle from the sell-side of curve that caused minor upward displacement. Now on the buy-side of curve, it becomes a reclaimed long.
- **Bearish Reclaimed OB**: A candle from the buy-side of curve that caused minor downward displacement. Now on the sell-side of curve, it becomes a reclaimed short.

### Propulsion Block
A candle that previously traded into an OB and now takes over the support/resistance role.

- **Bullish Propulsion Block**: Candle that bounced off a bullish OB and now acts as support for higher prices. Price should NOT fall below its 50% level.
- **Bearish Propulsion Block**: Candle that rejected from a bearish OB and now acts as resistance. Sell trigger at the low of the propulsion block.

### Vacuum Block
A gap created by a volatility event (e.g., NFP, session open gap). Treat as a range with potential OBs inside.

- Look for OBs within the gap
- If the gap fills 100%, the bottom/top of the gap becomes a key level
- **More probable**: Corrective move (gap partially fills then continues)
- **Less probable**: Exhaustion gap (fully reverses)

## Trading with Order Blocks

### Entry
- Enter when price retraces to the OB after displacement
- Limit order at the OB candle's open (conservative) or body midpoint (aggressive)

### Stop Loss
- **Bullish OB**: Below the low of the OB candle
- **Bearish OB**: Above the high of the OB candle

### Take Profit
- **Bullish OB**: Next buy-side liquidity (swing highs, equal highs)
- **Bearish OB**: Next sell-side liquidity (swing lows, equal lows)

### Liquidity-Based Bias with OBs
- **Bullish**: On intraday charts (4H and below), wait for retracement into discount. Look for price to run into a discount array, respect the bullish OB, then impulsively move up.
- **Bearish**: Wait for correction into premium. Look for price to enter a premium array, respect the bearish OB, then react strongly downward.

## Agent Detection Logic

```
function detect_order_blocks(candles, min_displacement_atr=1.5):
    obs = []
    
    for i in range(len(candles) - 3):
        # Check for bullish displacement (candles i+1, i+2, i+3 move up strongly)
        displacement_range = candles[i+3].close - candles[i].close
        atr = calculate_atr(candles, period=14, at=i)
        
        if displacement_range > atr * min_displacement_atr:
            # Bullish displacement detected — find the last down-close candle
            for j in range(i, max(i-5, 0), -1):
                if candles[j].close < candles[j].open:  # Down-close candle
                    ob = BullishOB(
                        high=candles[j].high,
                        low=candles[j].low,
                        open=candles[j].open,
                        close=candles[j].close,
                        midpoint=(candles[j].open + candles[j].close) / 2,
                        candle_index=j
                    )
                    obs.append(ob)
                    break
        
        if displacement_range < -atr * min_displacement_atr:
            # Bearish displacement detected — find the last up-close candle
            for j in range(i, max(i-5, 0), -1):
                if candles[j].close > candles[j].open:  # Up-close candle
                    ob = BearishOB(
                        high=candles[j].high,
                        low=candles[j].low,
                        open=candles[j].open,
                        close=candles[j].close,
                        midpoint=(candles[j].open + candles[j].close) / 2,
                        candle_index=j
                    )
                    obs.append(ob)
                    break
    
    return obs

function validate_ob(ob, subsequent_candles):
    """Check if OB's mean threshold (50%) holds."""
    for candle in subsequent_candles:
        if ob.type == BULLISH:
            if candle.close < ob.midpoint:
                return OB_INVALIDATED
            if candle.low <= ob.open and candle.close > ob.midpoint:
                return OB_VALIDATED  # Tested and held
        elif ob.type == BEARISH:
            if candle.close > ob.midpoint:
                return OB_INVALIDATED
            if candle.high >= ob.open and candle.close < ob.midpoint:
                return OB_VALIDATED
    return OB_UNTESTED
```
