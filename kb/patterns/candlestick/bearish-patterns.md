# Bearish Candlestick Patterns

## Single Candle Patterns

### Shooting Star (Bearish Pin Bar)
- **Structure**: Small body at bottom, long upper shadow (2x+ body length), little or no lower shadow
- **Context**: Must appear at top of uptrend near resistance
- **Signal**: Buyers pushed higher but sellers rejected and closed near low
- **Entry**: Sell on next candle; stop above shooting star's high
- **Strength**: Upper shadow should be at least 2x the real body

### Hanging Man
- **Structure**: Same shape as a hammer (small body at top, long lower shadow)
- **Context**: At top of uptrend (NOT at bottom — that's a hammer)
- **Signal**: Bearish reversal — selling pressure emerging

### Gravestone Doji
- **Structure**: Open and close at the low; long upper shadow
- **Context**: At top of uptrend near resistance
- **Signal**: Bearish reversal — market tested supply/resistance and was rejected

### Bearish Marubozu
- **Structure**: Full bearish body, no shadows
- **Signal**: Strong bearish conviction — sellers controlled the entire session

## Two-Candle Patterns

### Bearish Engulfing
- **Structure**: Large bearish candle completely engulfs the prior bullish candle's body
- **Context**: At end of uptrend near resistance
- **Signal**: Sellers overwhelmed buyers — strong reversal signal
- **Reliability**: One of the most reliable reversal patterns, especially on 4H/Daily

### Bearish Harami (Inside Bar)
- **Structure**: Small bearish candle fully contained within the prior large bullish candle
- **Context**: At top of uptrend = reversal. In downtrend = continuation.
- **Reliability**: Bearish harami in bullish market = 65% bearish reversal
- **Entry**: Sell after breakdown below mother candle; stop above mother candle

### Dark Cloud Cover
- **Structure**: Bullish candle followed by bearish candle that opens above prior high but closes below the midpoint of the bullish candle
- **Signal**: Sellers stepped in after a gap up — bearish pressure

### Tweezer Top
- **Structure**: Bullish candle followed by bearish candle, both with matching highs
- **Context**: At top of uptrend
- **Signal**: Double rejection of the same high level

### Bearish Kicker
- **Structure**: Bullish candle followed by bearish candle that gaps down (opens below prior open)
- **Signal**: One of the strongest reversal signals

## Three-Candle Patterns

### Evening Star
- **Structure**:
  1. Large bullish candle (buyers in control)
  2. Small body candle (indecision)
  3. Large bearish candle that closes below the midpoint of candle 1
- **Context**: At top of uptrend
- **Signal**: Powerful bearish reversal

### Evening Doji Star
- Same as Evening Star but middle candle is specifically a Doji
- Slightly stronger signal

### Bearish Abandoned Baby
- **Structure**: Gap up doji followed by gap down bearish candle
- **Signal**: Rare but very strong bearish reversal

### Three Black Crows
- **Structure**: Three consecutive bearish candles with progressively lower closes
- **Signal**: Strong bearish momentum / continuation

## Inside Bar False Breakout (Special Pattern)

### Structure
1. Mother candle (large)
2. Inside bar (small, within mother candle)
3. False breakout: price breaks above/below inside bar then reverses to close within mother candle range

### Signal
Identifies **stop-hunting by institutions**. Price breaks out to trigger stops, then reverses.

### Trading Rules
| Context | Signal | Action |
|---------|--------|--------|
| At top of uptrend near resistance | Bearish false breakout | Sell after close back inside |
| At bottom of downtrend near support | Bullish false breakout | Buy after close back inside |

### Best Locations for Inside Bar False Breakout
- Support/resistance levels
- 50% and 61% Fibonacci retracement levels
- 21 EMA (moving average)
- Trendlines
- Supply/demand zones

## ICT Integration

In ICT methodology, bearish candlestick patterns gain significance when:
- They form at **bearish FVG levels** or **bearish Order Blocks**
- They appear at **buy-side liquidity** levels (swing highs, equal highs)
- They occur during **Killzone** windows
- They align with **bearish HTF bias**
- A bearish pattern after a **buy-side liquidity sweep** = highest probability

## Agent Detection Logic

```
function detect_bearish_patterns(candles):
    patterns = []
    
    for i in range(2, len(candles)):
        c = candles[i]
        prev = candles[i-1]
        prev2 = candles[i-2]
        
        body = c.close - c.open
        range_ = c.high - c.low
        lower_shadow = min(c.open, c.close) - c.low
        upper_shadow = c.high - max(c.open, c.close)
        
        # Shooting Star
        if (body < 0 and upper_shadow >= 2 * abs(body) and
            lower_shadow < abs(body) * 0.3):
            patterns.append(ShootingStar(candle=c, index=i))
        
        # Bearish Engulfing
        if (prev.close > prev.open and  # Prior is bullish
            c.close < c.open and         # Current is bearish
            c.open >= prev.close and     # Opens at or above prior close
            c.close <= prev.open):       # Closes at or below prior open
            patterns.append(BearishEngulfing(candle=c, index=i))
        
        # Evening Star
        if (prev2.close > prev2.open and                # First: bullish
            abs(prev.close - prev.open) < atr * 0.3 and # Second: small body
            c.close < c.open and                         # Third: bearish
            c.close < (prev2.open + prev2.close) / 2):  # Closes below midpoint
            patterns.append(EveningStar(candles=[prev2, prev, c], index=i))
        
        # Inside Bar False Breakout
        if i >= 3:
            mother = candles[i-2]
            inside = candles[i-1]
            if (inside.high < mother.high and inside.low > mother.low):
                # Inside bar confirmed
                if (c.high > mother.high and c.close < mother.high):
                    patterns.append(BearishFalseBreakout(
                        mother=mother, inside=inside, breakout=c, index=i))
    
    return patterns
```
