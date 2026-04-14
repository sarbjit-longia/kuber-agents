# Silver Bullet Strategy

## Definition

The Silver Bullet is a **purely mechanical, time-based** intraday trading strategy. It requires NO daily bias determination. It uses one timeframe (5-minute), specific time windows, and strict rules. Backtested on 300+ trades with a ~65.73% win rate and 1.292 profit factor.

## Instruments
NQ, ES (index futures), or any liquid instrument

## Timeframe
5-minute chart only

## Key Characteristics
- No bias needed — the liquidity sweep tells you the direction
- Fixed 2R (2:1 reward-to-risk) target
- Maximum 2 trades per day
- All trades closed by end of day
- 100% mechanical — no discretion

## 5-Step Setup Process

### Step 1: Time Gate
**Is it 9:30 AM EST?**
- If NO → No trade. Wait.
- If YES → Proceed to Step 2.

### Step 2: Mark Time-Based Liquidity
At 9:30 AM EST, mark these levels on your chart:

| Liquidity Level | Time Range (EST) |
|----------------|-----------------|
| Asia Session High/Low | 18:00 - 00:00 |
| London Session High/Low | 00:00 - 06:00 |
| Pre-Market Range High/Low | 06:00 - 07:30 |

### Step 3: Liquidity Sweep Check
**Has at least one time-based liquidity level been swept since Midnight EST?**
- If NO → No trade. Wait and monitor.
- If YES → Proceed to Step 4.

A "sweep" means price has traded through the high or low of one of the marked sessions.

### Step 4: Determine Bias from the Sweep

| Liquidity Swept | Price Action After | Bias |
|----------------|-------------------|------|
| **Highs** swept | Price fails to continue higher, displaces lower | **BEARISH** |
| **Lows** swept | Price fails to continue lower, displaces higher | **BULLISH** |

The sweep direction tells you the bias without any HTF analysis.

### Step 5: FVG Entry in Time Windows

Wait for the **FIRST 5-minute Fair Value Gap** to form within the designated time window:

| Window | Time (EST) | Notes |
|--------|-----------|-------|
| **Window 1** | 10:00 AM - 11:00 AM | Primary window |
| **Window 2** | 2:00 PM - 3:00 PM | Secondary window |

**Rules**:
- Only the **FIRST** FVG in each window counts
- If the first FVG does **NOT** match the bias from Step 4 → No trade
- If the first FVG **matches** the bias → Valid setup

## Execution Rules

### Entry
- **Limit order** at the FVG (at the gap's open edge)
- Wait for price to retrace into the FVG

### Stop Loss
- Above/below the **first candle** in the FVG formation (candle 1 of the 3-candle pattern)

### Take Profit
- **Fixed 2R** (2:1 reward-to-risk ratio)
- Measure from entry to stop loss, then project 2x that distance as take profit

### Exit Rules
- All trades **MUST** be closed at end of day
- Maximum **2 trades per day** (one from each window)
- If the first window trade hits TP or SL, you may still take the second window trade

## Critical Rules

1. You **MUST** follow EVERY rule exactly — no exceptions
2. Do NOT enter outside the time windows
3. Do NOT take the second or third FVG if the first doesn't match
4. Do NOT hold overnight
5. Do NOT adjust the 2R target based on "feel"

## Backtesting Results

| Metric | Value |
|--------|-------|
| Win Rate | ~65.73% |
| Profit Factor | 1.292 |
| Trades Tested | 300+ |
| R:R per Trade | Fixed 2R |

## Agent Detection Logic

```
function silver_bullet_scan(candles_5m, date):
    # Step 1: Time gate
    if current_time(EST) < time(9, 30):
        return NO_TRADE, "Before 9:30 AM EST"
    
    # Step 2: Mark TBL
    tbl = get_time_based_liquidity(candles_5m, date)
    
    # Step 3: Check for sweep since midnight
    midnight_candles = filter_candles(candles_5m, start=date 00:00)
    sweeps = []
    
    for level_name, level_price in tbl.items():
        if "high" in level_name:
            if any(c.high > level_price for c in midnight_candles):
                sweeps.append(("HIGH_SWEPT", level_name, level_price))
        elif "low" in level_name:
            if any(c.low < level_price for c in midnight_candles):
                sweeps.append(("LOW_SWEPT", level_name, level_price))
    
    if not sweeps:
        return NO_TRADE, "No TBL sweep since midnight"
    
    # Step 4: Determine bias
    high_sweeps = [s for s in sweeps if s[0] == "HIGH_SWEPT"]
    low_sweeps = [s for s in sweeps if s[0] == "LOW_SWEPT"]
    
    if high_sweeps and not low_sweeps:
        bias = BEARISH
    elif low_sweeps and not high_sweeps:
        bias = BULLISH
    else:
        # Both swept — use the most recent sweep
        bias = BEARISH if high_sweeps[-1] > low_sweeps[-1] else BULLISH
    
    # Step 5: Look for first FVG in time windows
    windows = [
        (time(10, 0), time(11, 0)),  # Window 1
        (time(14, 0), time(15, 0)),  # Window 2
    ]
    
    for window_start, window_end in windows:
        window_candles = filter_candles(candles_5m, start=window_start, end=window_end)
        fvgs = detect_fvg(window_candles)
        
        if fvgs:
            first_fvg = fvgs[0]
            if first_fvg.direction == bias:
                entry = first_fvg.open_edge
                stop = first_fvg.candle_1_extreme
                risk = abs(entry - stop)
                tp = entry + (2 * risk * (1 if bias == BULLISH else -1))
                
                return TRADE_SIGNAL(
                    direction=bias,
                    entry=entry,
                    stop_loss=stop,
                    take_profit=tp,
                    r_multiple=2.0,
                    window=f"{window_start}-{window_end}"
                )
            else:
                continue  # First FVG doesn't match — skip this window
    
    return NO_TRADE, "No matching FVG in any window"
```
