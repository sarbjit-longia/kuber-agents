# SMM Entry Model (Smart Money / Market Maker Entry Model)

## Definition

A high-frequency, high-quality entry model aligned with institutional order flow. The core principle: **before every large expansion in the market, there is an obvious liquidity raid.** By identifying where manipulation occurs, you can target the opposing pool of liquidity.

## Core Principle

> Before every large expansion, there is an obvious liquidity raid. The raid is manipulation. The expansion is distribution. Trade the transition.

## 4-Step Process

### Step 1: Build the HTF Narrative

On the higher timeframe (e.g., H1, H4, Daily):
1. Determine: Is the market bullish or bearish?
2. Is it currently in retracement or expansion?
3. Identify the next logical draw on liquidity
4. Look for liquidity sweeps occurring **against** the narrative (this is manipulation)

### Step 2: Confirm Manipulation (Lack of Displacement)

A move that sweeps liquidity **WITHOUT displacement** is manipulation.

**Two methods to confirm:**

#### HTF Method
Watch the candle that purges the liquidity:
- If the candle sweeps a **low** but closes **above** the low → Manipulation (not genuine selling)
- If the candle sweeps a **high** but closes **below** the high → Manipulation (not genuine buying)
- Key: The body close relative to the liquidity level tells you if the move was real or fake

#### LTF Method
After liquidity is purged, drop to a lower timeframe (e.g., M5):
- Watch for a shift in the **opposite direction** with displacement
- This displacement on LTF confirms the manipulation and shows the market's willingness to travel to the opposing liquidity pool
- An MSS + FVG on LTF = confirmation

### Step 3: Entry on LTF Confirmation

After HTF manipulation is identified, the LTF shows:
1. Price **stalls** after sweeping the liquidity
2. An **energetic displacement** creates a Market Structure Shift (MSS)
3. An **FVG forms** in the displacement leg
4. Enter at the FVG or at the MSS level

**Entry Options**:
- **Aggressive**: Enter on the MSS candle close
- **Conservative**: Wait for retrace to the FVG within the MSS move

### Step 4: Targeting

Target the **opposing pool of liquidity** identified on the HTF:
- If bullish (bought at sell-side liquidity sweep) → Target buy-side liquidity above
- If bearish (sold at buy-side liquidity sweep) → Target sell-side liquidity below

This creates **high probability AND high risk-to-reward** trades because:
- You're entering at one extreme (the manipulation)
- Targeting the other extreme (the opposing liquidity)

## Example Walkthrough

### Bullish Setup
1. **H1 chart**: Market is bullish, currently retracing downward
2. **Liquidity identified**: Equal lows at $150.50 (obvious sell-side liquidity)
3. **Price action**: A candle sweeps below $150.50 to $150.20 but **closes back above** $150.50 → Manipulation confirmed
4. **M5 chart**: After the sweep, price stalls. Then a large bullish candle breaks above the M5 swing high (MSS). FVG forms at $150.80-$151.00.
5. **Entry**: Long at $150.80 (FVG). Stop at $150.10 (below sweep low). Risk = $0.70.
6. **Target**: Next HTF buy-side liquidity at $153.00. Reward = $2.20. R:R = 3.14:1.

### Bearish Setup
1. **H1 chart**: Market is bearish, currently retracing upward
2. **Liquidity identified**: Equal highs at $200.00 (obvious buy-side liquidity)
3. **Price action**: A candle sweeps above $200.00 to $200.30 but closes back below $200.00 → Manipulation confirmed
4. **M5 chart**: Price stalls, then displaces downward with MSS + FVG at $199.50-$199.30
5. **Entry**: Short at $199.50. Stop at $200.40. Target: $196.00.

## What Makes This Model Powerful

1. **Identifies manipulation in real-time**: The HTF method (candle close analysis) gives you the signal before the LTF even confirms
2. **High R:R**: Entering at manipulation extreme and targeting opposing liquidity gives R:R of 3:1 to 10:1+
3. **Works on any timeframe**: The principle is fractal — works the same on weekly/daily as on M15/M5
4. **Clear invalidation**: If the manipulation candle's extreme is taken out, the setup is invalidated

## Agent Detection Logic

```
function smm_entry_model(htf_candles, ltf_candles):
    # Step 1: HTF Narrative
    htf_bias = determine_daily_bias(htf_candles)
    if htf_bias == NEUTRAL:
        return NO_TRADE, "No clear HTF narrative"
    
    # Step 2: Find manipulation (liquidity sweep without displacement)
    htf_liquidity = find_liquidity_levels(htf_candles)
    
    for liq in htf_liquidity:
        sweep_candle = find_candle_sweeping(htf_candles, liq)
        if not sweep_candle:
            continue
        
        # Check if sweep was manipulation (no displacement)
        if htf_bias == BULLISH and liq.type == SELLSIDE:
            # Bullish context, sell-side swept
            if sweep_candle.close > liq.price:  # Closed back above = manipulation
                manipulation = BullishManipulation(
                    sweep_level=liq,
                    sweep_candle=sweep_candle,
                    extreme=sweep_candle.low
                )
                break
        
        elif htf_bias == BEARISH and liq.type == BUYSIDE:
            if sweep_candle.close < liq.price:  # Closed back below = manipulation
                manipulation = BearishManipulation(
                    sweep_level=liq,
                    sweep_candle=sweep_candle,
                    extreme=sweep_candle.high
                )
                break
    else:
        return NO_TRADE, "No manipulation detected"
    
    # Step 3: LTF confirmation (MSS + FVG)
    ltf_after_sweep = filter_candles_after(ltf_candles, manipulation.sweep_candle.timestamp)
    mss = detect_mss(ltf_after_sweep, current_structure=opposite(htf_bias))
    
    if not mss or not mss.displacement:
        return NO_TRADE, "No LTF MSS after manipulation"
    
    fvg = detect_fvg_in_mss(ltf_after_sweep, mss)
    
    # Step 4: Entry and targeting
    entry = fvg.open_edge if fvg else mss.candle.close
    stop = manipulation.extreme
    risk = abs(entry - stop)
    
    opposing_liquidity = find_opposing_liquidity(htf_liquidity, entry, htf_bias)
    reward = abs(opposing_liquidity.price - entry)
    
    if reward / risk < 2.0:
        return NO_TRADE, f"R:R {reward/risk:.1f} below minimum"
    
    return TRADE_SIGNAL(
        direction=htf_bias,
        entry=entry,
        stop_loss=stop,
        take_profit=opposing_liquidity.price,
        r_multiple=reward / risk,
        model="SMM_Entry"
    )
```
