# 3-Step Liquidity System

## Definition

A complete trading system built on three pillars: bias determination through displacement vs manipulation analysis, precise timing using killzone windows, and entry models calibrated to the timeframe. This system integrates the core ICT concepts into a repeatable, step-by-step process.

## Step 1: Manipulation vs Displacement (Determine Bias)

### Process
1. Open the **Daily chart**
2. Find the most recent impulse (move with displacement and FVGs)
3. Determine premium/discount of the impulse using Fibonacci (0.5 = equilibrium)
4. Distinguish:
   - **Displacement through structure** → Continuation expected → Bias aligns with displacement direction
   - **Manipulation through structure** → Reversal expected → Bias is opposite to the manipulation direction

### Algorithmic Bias (2-Step Sub-Process)

**Sub-Step A**: Daily chart — identify the most recent displacement. Draw premium/discount on that impulse. Determine where price currently sits (premium or discount).

**Sub-Step B**: H1/M15 chart — map out all liquidity levels.
- If **bullish** bias: look to buy under lows (at sell-side liquidity)
- If **bearish** bias: look to sell above highs (at buy-side liquidity)

### Key Question
When the market trades through a level:
- Did it **displace** (large candle, closed through, FVGs formed)? → Trade WITH the move
- Did it **manipulate** (wick only, no close through, no FVGs)? → Trade AGAINST the move

## Step 2: Timing

**Only look for entries during killzones:**

| Killzone | Time (EST) | What to Watch |
|----------|-----------|---------------|
| **London** | 01:30 - 04:30 | Manipulation of Asia session range |
| **NY** | 07:30 - 10:30 | Manipulation of London/pre-market range |

### Rules
- These are the **only** windows where manipulation-based entries are valid
- Outside these windows, do not look for entries
- The manipulation during these windows provides the setup; the subsequent displacement provides the entry

## Step 3: Entry Models

### Model A — Immediate Candle Entry (H1/M15)

**For**: Traders who want a quick, simple entry on the H1 or M15 timeframe.

**Process**:
1. Wait for pro-bias manipulation (liquidity sweep in the direction opposing your bias)
2. If the candle that takes the liquidity **immediately engulfs** the previous candle (sweep + engulfing) → **Enter trade**
3. Stop loss at the extreme of the sweep candle
4. Target: Draw on liquidity from H1/M15

**Risk Check**: Must achieve minimum 2R. If 2R is not achievable on H1/M15, use Model B instead.

### Model B — Market Structure Shift Entry (M5/M1)

**For**: Traders who want precision entries and better R:R.

**Process**:
1. Wait for the same liquidity sweep as Model A
2. Drop to M5 or M1
3. Wait for a **Market Structure Shift (MSS)** to confirm the reversal
4. Look for the FVG that forms in the MSS displacement
5. Enter on retrace to the FVG
6. Stop loss at the swing low/high created by the manipulation
7. Target: Draw on liquidity identified on H1/M15

**Re-entry Rule**: Re-entry throughout the move is allowed as long as minimum 2R is maintained.

## Risk Management Rules

| Rule | Detail |
|------|--------|
| **Minimum R:R** | 2R on every trade. If 2R isn't achievable, go to LTF for better entry. |
| **Position Sizing** | 1R risk from breakeven; 2R risk when 2R in profit; 0.5R risk in drawdown |
| **Daily Stop Rule** | 2 losses OR 1 win = stop trading for the day |
| **Trimming vs Breakeven** | Trimming (partial profits) is preferred over breakeven stops |

## Complete Framework Workflow

Putting it all together — the full top-down analysis:

| Step | Timeframe | Action |
|------|-----------|--------|
| 1 | Weekly | Identify IRL/ERL, weekly candle bias, weekly FVGs |
| 2 | Daily | Identify IRL/ERL, daily candle bias, most recent FVG tap and reaction |
| 3 | H4/H1 | Identify Market Maker Model, map liquidity levels |
| 4 | M15 | Map IRL/ERL, time-based liquidity (Asia, London, 06:00-07:30), session opens |
| 5 | During Killzone | Wait for manipulation (TBL sweep or session open sweep) |
| 6 | Entry Check | Confirm 2+ checklist items + LTF MSS with displacement |
| 7 | M5/M1 | Wait for MSS, enter on FVG retrace |
| 8 | Manage | Min 2R, trim at internal liquidity, stop after 2L or 1W |

## Entry Checklist (2 of 4 + Required LTF Confirmation)

| # | Condition | Required? |
|---|-----------|-----------|
| 1 | HTF bias = LTF bias | Optional (need 2 of 4) |
| 2 | HTF IRL/ERL = LTF MMXM | Optional (need 2 of 4) |
| 3 | Manipulation beyond session open / TBL swept | Optional (need 2 of 4) |
| 4 | Price at HTF key level (FVG, OB, breaker) | Optional (need 2 of 4) |
| 5 | **LTF MSS with displacement** | **REQUIRED** |

## Agent Detection Logic

```
function three_step_liquidity_system(daily_candles, h1_candles, m5_candles, timestamp_est):
    # STEP 1: Bias
    bias = determine_bias_from_displacement(daily_candles)
    if bias == NEUTRAL:
        return NO_TRADE, "No clear bias"
    
    # Map liquidity on H1
    h1_liquidity = find_liquidity_levels(h1_candles, timeframe="1h")
    if bias == BULLISH:
        entry_zones = [l for l in h1_liquidity if l.type == SELLSIDE]  # Buy under lows
    else:
        entry_zones = [l for l in h1_liquidity if l.type == BUYSIDE]  # Sell above highs
    
    # STEP 2: Timing
    if not is_in_killzone(timestamp_est):
        return NO_TRADE, "Outside killzone"
    
    # Check for TBL sweep
    tbl = get_time_based_liquidity(h1_candles, timestamp_est.date())
    tbl_sweep = check_tbl_swept(m5_candles, tbl, since=killzone_start(timestamp_est))
    if not tbl_sweep:
        return NO_TRADE, "No TBL sweep during killzone"
    
    # STEP 3: Entry
    # Model B (preferred): MSS on M5
    mss = detect_mss(m5_candles, current_structure=opposite(bias))
    if mss and mss.displacement:
        fvg = detect_fvg_after_mss(m5_candles, mss)
        if fvg:
            entry = fvg.open_edge
            stop = mss.swing_extreme  # Low of manipulation for longs
            risk = abs(entry - stop)
            
            # Check minimum 2R
            target_liquidity = find_nearest_liquidity(h1_liquidity, entry, bias)
            potential_reward = abs(target_liquidity.price - entry)
            
            if potential_reward / risk >= 2.0:
                return TRADE_SIGNAL(
                    direction=bias,
                    entry=entry,
                    stop_loss=stop,
                    take_profit=target_liquidity.price,
                    r_multiple=potential_reward / risk,
                    model="B_MSS_FVG"
                )
    
    return NO_TRADE, "No valid entry model triggered"
```
