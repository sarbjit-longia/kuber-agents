# Liquidity

## Definition

Liquidity is the ease at which an asset can be bought or sold. In ICT methodology, liquidity refers to clusters of resting orders (stop losses, pending orders) placed at obvious price levels — equal highs, equal lows, swing highs/lows, and session highs/lows. Price is drawn to these clusters to fill large institutional orders.

## Types of Liquidity

### External Range Liquidity (ERL)
- **Definition**: Highs and lows (swing points) at the boundaries of a price range
- **Examples**: Swing highs, swing lows, equal highs (EQH), equal lows (EQL)
- **Significance**: These are the primary targets price moves toward

### Internal Range Liquidity (IRL)
- **Definition**: Fair value gaps (FVGs) within a price range
- **Examples**: Unfilled FVGs, order blocks, breaker blocks
- **Significance**: These are levels price trades through on the way to ERL

### Key Rule: IRL → ERL Flow
**Price always moves from internal liquidity to external liquidity.** This is the fundamental principle of price delivery:
- Price fills/reacts to an FVG (IRL), then expands toward a swing high/low (ERL)
- After reaching ERL, price seeks new IRL to trade through

## Buy-Side vs Sell-Side Liquidity

| Type | Location | Contains | Who Gets Stopped |
|------|----------|----------|-----------------|
| **Buy-Side Liquidity (BSL)** | Above swing highs, equal highs | Buy stops, sell stop losses | Shorts get stopped out |
| **Sell-Side Liquidity (SSL)** | Below swing lows, equal lows | Sell stops, buy stop losses | Longs get stopped out |

### Institutional Logic
- **In a bullish market**: Institutions BUY from sellers under lows, at sell-side liquidity
- **In a bearish market**: Institutions SELL to buyers above highs, at buy-side liquidity
- This is counter-intuitive but reflects how large participants accumulate/distribute positions

## Time-Based Liquidity (TBL)

Time-based liquidity represents the highs and lows of specific time periods. These are high-value targets because many traders place stops relative to session extremes.

### Key TBL Levels to Annotate

| Time Period | EST Hours | What to Mark |
|------------|-----------|-------------|
| **Previous Week** | — | Weekly High and Low |
| **Previous Day** | — | PDH (Previous Day High) and PDL (Previous Day Low) |
| **Asia Session** | 18:00 - 00:00 | Session High and Low |
| **London Session** | 00:00 - 06:00 | Session High and Low |
| **Pre-Market Range** | 06:00 - 07:30 | Range High and Low |
| **NY Q1** | 06:00 - 07:30 | Quarter High and Low |
| **NY Q2** | 07:30 - 09:00 | Quarter High and Low |

### Chart Preparation Rule
At **09:30 EST** (market open), annotate all time-based liquidity pools:
1. Previous Asia Session high/low
2. Previous London Session high/low
3. 06:00-07:30 range high/low
4. Previous Day high/low

## Liquidity Sweeps

A **liquidity sweep** (also called a liquidity raid or purge) occurs when price briefly trades beyond a liquidity level to trigger resting orders, then reverses.

### Identifying a Liquidity Sweep
1. Price approaches an obvious liquidity level (swing high/low, equal highs/lows, session high/low)
2. Price trades through the level (wicks or briefly closes beyond)
3. Price fails to sustain/displace beyond the level
4. Price reverses direction

### Sweep + Displacement = Confirmation
- **Sweep WITHOUT displacement** = Manipulation (trade against the sweep direction)
- **Sweep WITH displacement** = Genuine breakout (trade with the sweep direction)

## Draw on Liquidity (DOL)

The **Draw on Liquidity** is the liquidity pool that price is expected to target next. Identifying the DOL is the first step in any trade setup.

### How to Identify DOL
1. Determine HTF bias (bullish or bearish)
2. If bullish: DOL = next buy-side liquidity (swing high, EQH, session high above)
3. If bearish: DOL = next sell-side liquidity (swing low, EQL, session low below)

## Algorithmic Bias Using Liquidity (2-Step System)

### Step 1: Daily Chart Analysis
- Find the most recent impulse
- Determine premium/discount of the impulse
- Identify areas of recent displacement for premium/discount zones

### Step 2: H1/M15 Liquidity Mapping
- Map out all liquidity levels on H1 or M15 only
- If bullish bias: look to buy under lows (at sell-side liquidity)
- If bearish bias: look to sell above highs (at buy-side liquidity)

## Agent Detection Logic

```
function find_liquidity_levels(candles, timeframe):
    levels = []
    
    # Find equal highs (2+ touches within tolerance)
    highs = [c.high for c in candles]
    for i, j in combinations(range(len(highs)), 2):
        if abs(highs[i] - highs[j]) / highs[i] < 0.001:  # 0.1% tolerance
            levels.append(BuySideLiquidity(price=max(highs[i], highs[j])))
    
    # Find equal lows
    lows = [c.low for c in candles]
    for i, j in combinations(range(len(lows)), 2):
        if abs(lows[i] - lows[j]) / lows[i] < 0.001:
            levels.append(SellSideLiquidity(price=min(lows[i], lows[j])))
    
    # Add session highs/lows as TBL
    for session in [ASIA, LONDON, NY_PRE, PREV_DAY, PREV_WEEK]:
        session_candles = filter_by_session(candles, session)
        levels.append(TBL(high=max(c.high for c in session_candles), 
                          low=min(c.low for c in session_candles),
                          session=session))
    
    return levels

function detect_liquidity_sweep(candles, liquidity_level):
    for candle in candles:
        if candle.high > liquidity_level.price:  # For BSL
            if candle.close < liquidity_level.price:  # Wick only
                return SWEEP_DETECTED
            elif not has_displacement(candle):  # Close through but no displacement
                return SWEEP_DETECTED
    return NO_SWEEP
```
