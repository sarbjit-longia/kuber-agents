# Breaker Blocks

## Definition

A Breaker Block is a powerful price level that forms when a market structure shift causes a previous order block to fail. When price deviates from a range and breaks structure, the failed order block "flips" its role — a bearish order block becomes a bullish breaker, and vice versa. Breaker blocks represent levels where market makers return to stop out "dumb money" before continuing in the true direction.

## Types

### Bullish Breaker Block
- **Formation Pattern**: Low → High → Lower Low → Higher High
- **Definition**: An **up-close candle** in the most recent swing HIGH before an old LOW is violated
- **Context**: Price breaks below a previous low (runs sell-side liquidity), then reprices higher. The old bearish order block that failed now becomes a bullish breaker.
- **Role**: Acts as support when price retraces to it

### Bearish Breaker Block
- **Formation Pattern**: High → Low → Higher High → Lower Low
- **Definition**: A **down-close candle** in the most recent swing LOW before an old HIGH is violated
- **Context**: Price breaks above a previous high (runs buy-side liquidity), then reprices lower. The old bullish order block that failed now becomes a bearish breaker.
- **Role**: Acts as resistance when price retraces to it

## Formation Sequence

### Bullish Breaker Formation
1. Price creates a swing high (with bullish candles — potential bearish OB)
2. Price drops and makes a swing low
3. Price drops further, making a **lower low** (breaks the previous swing low — runs sell-side liquidity)
4. Price reverses and makes a **higher high** (breaks above the previous swing high)
5. The up-close candle at the original swing high is now a **Bullish Breaker Block**
6. → Price retraces to this breaker = buying opportunity

### Bearish Breaker Formation
1. Price creates a swing low (with bearish candles — potential bullish OB)
2. Price rallies and makes a swing high
3. Price rallies further, making a **higher high** (breaks the previous swing high — runs buy-side liquidity)
4. Price reverses and makes a **lower low** (breaks below the previous swing low)
5. The down-close candle at the original swing low is now a **Bearish Breaker Block**
6. → Price retraces to this breaker = selling opportunity

## Confirmation

A **Market Structure Break (MSB)** confirms the breaker block is active. Without the MSB (the price actually breaking through the previous structure in the new direction), the breaker is not confirmed.

## When Breakers Are Most Powerful

| Condition | Why |
|-----------|-----|
| At key times of day (killzones) | Liquidity sweeps are most common during killzones |
| Linked with Fair Value Gaps | Breaker + FVG = highest confluence level |
| After a clear liquidity raid | The breaker forms as part of the manipulation → distribution cycle |
| On HTF timeframes | HTF breakers are stronger reference levels |

## Trading with Breaker Blocks

### Entry
- Wait for price to retrace to the breaker block level
- Enter on the retest (limit order or LTF confirmation)

### Stop Loss
- **Bullish Breaker**: Below the low of the breaker block candle
- **Bearish Breaker**: Above the high of the breaker block candle

### Targets
- Opposing liquidity pool (the draw on liquidity identified on HTF)

## Breaker Block vs Order Block

| Feature | Order Block | Breaker Block |
|---------|-------------|---------------|
| **Formation** | Last opposing candle before displacement | Failed OB that flips role after MSB |
| **Context** | Trend continuation | Trend reversal / structure shift |
| **Reliability** | Good in trending markets | Excellent at reversal points |
| **Polarity** | Same as original move | Opposite (flipped) |

## Agent Detection Logic

```
function detect_breaker_blocks(candles, swing_points):
    breakers = []
    
    for i in range(2, len(swing_points)):
        p1 = swing_points[i-2]  # First swing
        p2 = swing_points[i-1]  # Second swing
        p3 = swing_points[i]    # Third swing (current)
        
        # Bullish Breaker: Low -> High -> Lower Low -> (expect Higher High)
        if (p1.type == LOW and p2.type == HIGH and p3.type == LOW 
            and p3.price < p1.price):  # Lower low made
            # Check if price subsequently makes higher high above p2
            subsequent = get_candles_after(candles, p3.timestamp)
            for candle in subsequent:
                if candle.high > p2.price:  # Higher high confirmed
                    # Find the up-close candle at p2 (the breaker)
                    breaker_candle = find_up_close_candle_at(candles, p2)
                    if breaker_candle:
                        breakers.append(BullishBreaker(
                            high=breaker_candle.high,
                            low=breaker_candle.low,
                            open=breaker_candle.open,
                            close=breaker_candle.close,
                            formation_swing=p2
                        ))
                    break
        
        # Bearish Breaker: High -> Low -> Higher High -> (expect Lower Low)
        if (p1.type == HIGH and p2.type == LOW and p3.type == HIGH 
            and p3.price > p1.price):  # Higher high made
            subsequent = get_candles_after(candles, p3.timestamp)
            for candle in subsequent:
                if candle.low < p2.price:  # Lower low confirmed
                    breaker_candle = find_down_close_candle_at(candles, p2)
                    if breaker_candle:
                        breakers.append(BearishBreaker(
                            high=breaker_candle.high,
                            low=breaker_candle.low,
                            open=breaker_candle.open,
                            close=breaker_candle.close,
                            formation_swing=p2
                        ))
                    break
    
    return breakers
```
