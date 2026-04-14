# Bullish Candlestick Patterns

## Single Candle Patterns

### Hammer (Bullish Pin Bar)
- **Structure**: Small body at top, long lower shadow (2x+ body length), little or no upper shadow
- **Context**: Must appear at bottom of downtrend near support
- **Signal**: Sellers pushed price lower but buyers rejected and closed near high
- **Entry (Aggressive)**: Enter on next candle open; stop below hammer's low
- **Entry (Conservative)**: Enter at 50% retracement of hammer range; better R:R (5:1+)
- **Strength**: Longer tail = stronger signal

### Inverted Hammer
- **Structure**: Small body at bottom, long upper shadow, little or no lower shadow
- **Context**: At bottom of downtrend
- **Signal**: Potential reversal — buyers attempted to push higher

### Dragonfly Doji
- **Structure**: Open, high, and close at the same level; long lower shadow
- **Context**: At bottom of downtrend near support
- **Signal**: Bullish reversal — supply/demand nearing balance

### Bullish Marubozu
- **Structure**: Full bullish body, no shadows
- **Signal**: Strong bullish conviction — buyers controlled the entire session

## Two-Candle Patterns

### Bullish Engulfing
- **Structure**: Large bullish candle completely engulfs the prior bearish candle's body
- **Context**: At end of downtrend near support
- **Signal**: Buyers overwhelmed sellers — reversal signal
- **Strongest when**: At the very bottom of a downtrend = capitulation bottom (most powerful signal)
- **Also valid**: In an uptrend as continuation

### Bullish Harami (Inside Bar)
- **Structure**: Small bullish candle fully contained within the prior large bearish candle
- **Context**: At bottom of downtrend = reversal. In uptrend = continuation.
- **Reliability**: Bullish harami in bearish market = 52% continuation (use with confluence)
- **Entry**: Place order after breakout of mother candle; stop above/below mother candle

### Piercing Line
- **Structure**: Bearish candle followed by bullish candle that opens below prior low but closes above the midpoint of the bearish candle
- **Signal**: Buyers stepped in aggressively after a gap down

### Tweezer Bottom
- **Structure**: Bearish candle followed by bullish candle, both with matching lows
- **Context**: At bottom of downtrend
- **Signal**: Double rejection of the same low level

### Bullish Kicker
- **Structure**: Bearish candle followed by bullish candle that gaps up (opens above prior open)
- **Signal**: One of the strongest reversal signals

## Three-Candle Patterns

### Morning Star
- **Structure**:
  1. Large bearish candle (sellers in control)
  2. Small body candle (indecision — can be bullish, bearish, or doji)
  3. Large bullish candle that closes above the midpoint of candle 1
- **Context**: At bottom of downtrend near support
- **Signal**: Powerful bullish reversal

### Morning Doji Star
- Same as Morning Star but middle candle is specifically a Doji
- Slightly stronger signal due to the clearer indecision

### Bullish Abandoned Baby
- **Structure**: Gap down doji followed by gap up bullish candle
- **Signal**: Rare but very strong reversal

### Three White Soldiers
- **Structure**: Three consecutive bullish candles with progressively higher closes
- **Signal**: Strong bullish momentum / continuation

### Three Inside Up
- **Structure**: Bullish harami (candles 1-2) followed by a higher-closing bullish candle (candle 3)
- **Signal**: Confirms the harami reversal

### Three Outside Up
- **Structure**: Bullish engulfing (candles 1-2) followed by a higher-closing bullish candle (candle 3)
- **Signal**: Confirms the engulfing reversal

## ICT Integration

In ICT methodology, candlestick patterns gain additional significance when:
- They form at **FVG levels** (Fair Value Gaps)
- They appear at **Order Blocks** or **Breaker Blocks**
- They occur during **Killzone** windows
- They align with **HTF bias** direction
- A bullish pattern after a **sell-side liquidity sweep** = highest probability

## Agent Detection Logic

```
function detect_bullish_patterns(candles):
    patterns = []
    
    for i in range(2, len(candles)):
        c = candles[i]
        prev = candles[i-1]
        prev2 = candles[i-2]
        
        body = c.close - c.open
        range_ = c.high - c.low
        lower_shadow = min(c.open, c.close) - c.low
        upper_shadow = c.high - max(c.open, c.close)
        
        # Hammer
        if (body > 0 and lower_shadow >= 2 * abs(body) and 
            upper_shadow < abs(body) * 0.3):
            patterns.append(Hammer(candle=c, index=i))
        
        # Bullish Engulfing
        if (prev.close < prev.open and  # Prior is bearish
            c.close > c.open and         # Current is bullish
            c.open <= prev.close and      # Opens at or below prior close
            c.close >= prev.open):        # Closes at or above prior open
            patterns.append(BullishEngulfing(candle=c, index=i))
        
        # Morning Star
        if (prev2.close < prev2.open and           # First: bearish
            abs(prev.close - prev.open) < atr * 0.3 and  # Second: small body
            c.close > c.open and                     # Third: bullish
            c.close > (prev2.open + prev2.close) / 2):   # Closes above midpoint
            patterns.append(MorningStar(candles=[prev2, prev, c], index=i))
    
    return patterns
```
