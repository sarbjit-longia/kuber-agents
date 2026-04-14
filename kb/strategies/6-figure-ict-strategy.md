# 6-Figure ICT Strategy (Casper SMC A+ Trading Checklist)

## Definition

A 5-step systematic approach to high-probability ICT trading. Emphasizes time-based liquidity, the 07:30 EST session open, and strict risk rules including "no breakeven stops" and "stop after 1 win or 2 losses."

## Instruments
NQ, ES (index futures)

## 5-Step Process

### Step 1: Blueprint Bias System

Establish a clear directional bias before anything else.

**Process**:
1. Identify the most recent **displacement** on the higher timeframe
2. Determine if liquidity was taken **before** the displacement
3. If yes, mark out the FVG or Order Block in the premium or discount zone
4. Determine bias direction: the displacement direction IS the bias

**Rule**: A CLEAR bias is the absolute foundation. Without it, there is no trade.

**Key Elements**: Structure + Liquidity + Order Flow must all align.

### Step 2: Mark Time-Based Liquidity (TBL) + Session Open

Annotate ALL relevant time-based liquidity levels:

| Level | Time Range (EST) |
|-------|-----------------|
| Previous Week's High/Low | — |
| Previous Day's High/Low (PDH/PDL) | — |
| Previous Session High/Low | — |
| Previous Quarter High/Low | — |
| Asia Session Range | 18:00 - 00:00 |
| London Session Range | 00:00 - 06:00 |
| NY Q1 Range | 06:00 - 07:30 |
| NY Q2 Range | 07:30 - 09:00 |

**Key**: All of these are "high value liquidity" because they are time-based. Time-based liquidity levels are the most reliable targets and entry zones.

### Step 3: TBL Sweep (07:30 - 10:30 EST) + HTF Footprint

Wait for time-based liquidity to be swept between **7:30 AM and 10:30 AM EST**.

**Conditions** (all must be met):
1. Price must sweep a TBL level within the 07:30-10:30 window
2. Price must be trading within an **M15/H1 footprint** (PD array — FVG, OB, or breaker)
3. Price must be above or below the **7:30 AM opening price** (True Session Open)

**7:30 AM Open as Premium/Discount**:
- If **bearish** bias: sell above the 07:30 open
- If **bullish** bias: buy below the 07:30 open

The 07:30 open acts as the session's equilibrium line.

### Step 4: M1 Market Structure Shift with Displacement

Drop to the **1-minute chart** and watch for:
1. Price often forms a small range near the TBL level
2. Price may sweep its own minor liquidity within this range
3. Wait for a **Market Structure Shift (MSS) WITH displacement**
4. The MSS must show:
   - A candle closing through a recent swing point
   - Large body, small wicks
   - FVG forming in the break

**Critical Rule**: Enter as soon as the MSS is confirmed. Do NOT wait for an FVG retracement — enter immediately.

**Patience is key**: The MSS might take time to form. Do not force an entry.

### Step 5: Target First Liquidity at Minimum 3R

**Target**: The first obvious liquidity pool (does NOT need to be time-based):
- Equal highs/lows
- Swing highs/lows
- Session highs/lows
- Any visible liquidity cluster

**Minimum R:R**: **3R** (3:1 reward-to-risk)

**Position Management**:
- **NO breakeven stops** — let the trade play out
- **NO moving stops** — the stop stays where it was placed
- The trade either hits TP or SL. Period.

## Daily Rules

| Rule | Detail |
|------|--------|
| **Stop after 2 losses** | If you lose 2 trades → Done for the day |
| **Stop after 1 win** | If you win 1 trade → Done for the day |
| **No breakeven** | Do not move stops to breakeven |
| **Minimum 3R** | Do not take trades with less than 3:1 R:R |

## What Makes This Strategy Unique

1. **No breakeven stops**: Forces you to trust the setup and accept the risk. Prevents death by a thousand breakeven-to-loss swings.
2. **1 win = done**: Removes the temptation to "make more" and prevents giving back profits.
3. **3R minimum**: Ensures that even at a 40% win rate, the strategy is profitable.
4. **Immediate MSS entry**: Captures the initial displacement move without waiting for retrace (which may not come).

## Agent Detection Logic

```
function six_figure_strategy(daily_candles, h1_candles, m1_candles, timestamp_est):
    # Step 1: Blueprint Bias
    recent_displacement = find_most_recent_displacement(daily_candles)
    if not recent_displacement:
        return NO_TRADE, "No clear displacement for bias"
    
    bias = recent_displacement.direction
    
    # Check if liquidity was taken before the displacement
    pre_displacement_sweep = check_liquidity_before(daily_candles, recent_displacement)
    if not pre_displacement_sweep:
        return NO_TRADE, "No liquidity sweep before displacement"
    
    # Step 2: Mark TBL
    tbl = get_all_time_based_liquidity(h1_candles, timestamp_est.date())
    session_open_730 = get_price_at(h1_candles, timestamp_est.date(), time(7, 30))
    
    # Step 3: TBL Sweep in 07:30-10:30 window
    t = timestamp_est.hour + timestamp_est.minute / 60.0
    if not (7.5 <= t <= 10.5):
        return NO_TRADE, "Outside 07:30-10:30 window"
    
    tbl_sweep = check_tbl_swept_in_window(m1_candles, tbl, 
                                           start=time(7, 30), end=time(10, 30))
    if not tbl_sweep:
        return NO_TRADE, "No TBL sweep in NY window"
    
    # Check price vs 07:30 open
    current_price = m1_candles[-1].close
    if bias == BEARISH and current_price < session_open_730:
        return NO_TRADE, "Price below 07:30 open but bias is bearish (need to sell above)"
    if bias == BULLISH and current_price > session_open_730:
        return NO_TRADE, "Price above 07:30 open but bias is bullish (need to buy below)"
    
    # Check H1/M15 PD array confluence
    htf_pd_array = find_pd_array_at(h1_candles, current_price)
    if not htf_pd_array:
        return NO_TRADE, "Not within HTF PD array"
    
    # Step 4: M1 MSS with displacement
    mss = detect_mss(m1_candles[-60:], current_structure=opposite(bias))
    if not mss or not mss.displacement:
        return NO_TRADE, "No M1 MSS with displacement"
    
    # Step 5: Target first liquidity at 3R minimum
    entry = mss.candle.close  # Enter immediately on MSS
    stop = mss.swing_extreme
    risk = abs(entry - stop)
    
    target = find_first_liquidity(m1_candles, entry, bias)
    reward = abs(target.price - entry)
    
    if reward / risk < 3.0:
        return NO_TRADE, f"R:R only {reward/risk:.1f}, need minimum 3R"
    
    return TRADE_SIGNAL(
        direction=bias,
        entry=entry,
        stop_loss=stop,
        take_profit=target.price,
        r_multiple=reward / risk,
        rules=["NO breakeven", "NO trailing stop", "Close after 1W or 2L"]
    )
```
