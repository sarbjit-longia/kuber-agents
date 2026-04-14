# Daily Bias

## Definition

Daily bias is the direction you anticipate the current daily candle to close. It answers the question: are buyers or sellers in control today? When bias is clear, all you need to do is wait for an entry model during the trading session.

## Standard Operating Procedure (SOP) — 4 Steps

### Step 1: IRL & ERL Analysis (HTF)

The market alternates in a never-ending cycle between Internal Range Liquidity (IRL) and External Range Liquidity (ERL):

- **IRL** = Fair Value Gaps (inefficiencies inside a range)
- **ERL** = Swing Highs/Lows (liquidity at range extremes)

**Ask**: Has price just tapped into a Fair Value Gap (IRL)? Or has price just taken out a high/low (ERL)?

**Your next draw on liquidity** is whichever has NOT been tapped yet:
- If price just filled an FVG (IRL) → Next target is a swing high/low (ERL)
- If price just swept a high/low (ERL) → Next target is an FVG (IRL)
- Pattern: Internal → External → Internal → External (rinse and repeat)

**Apply primarily to HTFs**: Monthly, Weekly, Daily

### Step 2: Time-Based Liquidity (Previous Candle Analysis)

Focus on previous weekly and daily candle highs and lows:
- Is price **displacing** past the previous candle (continuation)?
- Or merely **sweeping** the previous candle's liquidity (reversal)?

**Key distinction**:
- If the current candle fails to close past the previous candle's high/low → Expect reversal
- If the current candle closes through with displacement → Expect continuation

These levels are where high-probability Market Maker Models form.

### Step 3: LTF Structure Confirmation

Once HTF bias is determined, drop to a lower timeframe:
- Analyzing Weekly → Drop to 4H
- Analyzing Daily → Drop to 1H

Look for structure that **aligns** with your HTF bias:
- Market Maker Models in the bias direction
- Market Structure Shifts confirming the bias
- Retracements become opportunities to add positions, not threats

### Step 4 (Optional): Opening Prices / Power of 3

Use opening prices as time-based premium/discount:
- **Weekly Open**: Monday 18:00 EST
- **Daily Open**: 00:00 EST (Midnight)

If bullish → Enter longs BELOW the opening price
If bearish → Enter shorts ABOVE the opening price

## FVG-Based Daily Bias Strategy (3 Steps)

A simplified method using only FVGs on the daily chart:

### Step 1: Find the Most Recent FVG Tap
Go to the daily chart. Find the most recent tap of any Fair Value Gap.

### Step 2: Evaluate Using the 3 FVG Rules

| Rule | Condition | Meaning |
|------|-----------|---------|
| **Rule 1** | Price enters FVG, fails to close beyond midpoint | Valid FVG → Bias continues in FVG direction |
| **Rule 2** | Price closes beyond midpoint | Invalid FVG → Wait for next FVG |
| **Rule 3** | Price closes completely through FVG | Inversion → New FVG in opposite direction |

### Step 3: Target the Next Draw
Target the next fair value gap or liquidity level in the direction of your bias.

### Step 4 (Optional): Intraday Refinement
Drop to H1 and M5 during the killzone for more immediate intraday bias confirmation.

## Multi-Timeframe Bias Sequence

Follow this top-down sequence for the most complete bias determination:

| Step | Timeframe | Analysis |
|------|-----------|----------|
| 1 | Weekly | IRL/ERL → Determine weekly draw on liquidity |
| 2 | Weekly | Candle bias → What is the weekly candle telling you? |
| 3 | Daily | IRL/ERL → Determine daily draw on liquidity |
| 4 | Daily | Candle bias → What is the daily candle telling you? |
| 5 | H4/H1 | Market Maker Model → Identify MMXM on intermediate TF |
| 6 | M15 | IRL/ERL → Map intraday liquidity |
| 7 | M15/M5 | TBL reaction → Watch manipulation at session open/TBL |

## Determining Which Side Is Failing

Ask: **Which side of the market is failing?**

Evaluate via:
- **FVGs**: Are bullish or bearish FVGs failing (being closed through)?
- **Order Blocks**: Are OBs holding or being invalidated?
- **Structure**: Is price showing displacement or manipulation at key levels?

The side that is consistently failing = the side to trade against.

## OLHC / OHLC Framework

The daily candle structure reveals the bias:

| Pattern | Sequence | Bias |
|---------|----------|------|
| **OLHC** | Open → Low → High → Close | **Bullish** (low forms first, closes near high) |
| **OHLC** | Open → High → Low → Close | **Bearish** (high forms first, closes near low) |

- **Bullish OLHC**: Scan for this pattern. Low forms during London/early NY (manipulation), high forms during NY AM (distribution).
- **Bearish OHLC**: High forms during London/early NY, low forms during NY AM.

## Agent Detection Logic

```
function determine_daily_bias(daily_candles, h1_candles):
    # Step 1: IRL/ERL Analysis
    recent_fvgs = detect_fvg(daily_candles[-20:])
    recent_swings = identify_swing_points(daily_candles[-20:])
    
    last_event = determine_last_irl_erl_event(daily_candles, recent_fvgs, recent_swings)
    
    if last_event.type == IRL_TAP:  # Just tapped an FVG
        next_target = find_nearest_erl(recent_swings, daily_candles[-1].close)
        if next_target.price > daily_candles[-1].close:
            irl_erl_bias = BULLISH
        else:
            irl_erl_bias = BEARISH
    elif last_event.type == ERL_SWEEP:  # Just swept a high/low
        next_target = find_nearest_irl(recent_fvgs, daily_candles[-1].close)
        irl_erl_bias = BULLISH if next_target.price > daily_candles[-1].close else BEARISH
    
    # Step 2: FVG Reaction
    most_recent_fvg = find_most_recent_tapped_fvg(daily_candles, recent_fvgs)
    fvg_reaction = evaluate_fvg_reaction(most_recent_fvg, daily_candles)
    
    if fvg_reaction == FVG_VALID:
        fvg_bias = most_recent_fvg.direction  # Continue in FVG direction
    elif fvg_reaction == FVG_INVERTED:
        fvg_bias = opposite(most_recent_fvg.direction)  # Inverted = new direction
    else:
        fvg_bias = NEUTRAL
    
    # Step 3: Previous candle analysis
    prev_candle = daily_candles[-2]
    curr_candle = daily_candles[-1]
    
    if curr_candle.close > prev_candle.high:
        candle_bias = BULLISH  # Displacing past previous high
    elif curr_candle.close < prev_candle.low:
        candle_bias = BEARISH  # Displacing past previous low
    else:
        candle_bias = NEUTRAL  # Still inside previous range
    
    # Combine signals
    bias_votes = [irl_erl_bias, fvg_bias, candle_bias]
    bullish_count = sum(1 for b in bias_votes if b == BULLISH)
    bearish_count = sum(1 for b in bias_votes if b == BEARISH)
    
    if bullish_count >= 2:
        return BULLISH, confidence=bullish_count/3
    elif bearish_count >= 2:
        return BEARISH, confidence=bearish_count/3
    else:
        return NEUTRAL, confidence=0
```
