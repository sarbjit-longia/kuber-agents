# Time and Price

## Definition

Time and Price is the ICT framework that integrates session timing, killzones, and key time references into trading decisions. The premise is that institutional algorithms operate on predictable time-based schedules, and aligning trades with these windows dramatically increases probability.

## Session Times (All EST)

| Session | Hours (EST) | Purpose |
|---------|-------------|---------|
| **Asia** | 18:00 - 00:00 | Accumulation phase; sets the day's initial range |
| **London** | 00:00 - 06:00 | First major expansion; often sets the high or low of the day |
| **NY Pre-Market** | 06:00 - 07:30 | Transition; creates time-based liquidity |
| **NY AM** | 07:30 - 12:00 | Primary US session; highest volume and volatility |
| **NY PM** | 12:00 - 16:00 | Continuation or reversal of AM move |
| **NY Close** | 16:00 - 18:00 | End of day; accumulation for next cycle |

## Killzones

Killzones are the specific time windows where the highest-probability setups occur. **Only look for entries during killzones.**

| Killzone | Hours (EST) | Focus |
|----------|-------------|-------|
| **London Killzone** | 01:30 - 04:30 | Manipulation of Asia range; look for sweeps of Asia highs/lows |
| **NY Killzone** | 07:30 - 10:30 | Manipulation of London/pre-market range; primary trading window |
| **NY AM Focus** | 09:00 - 10:30 | Most precise window for NY entries |

### Rule
**Only watch for manipulation-based entries during killzones.** Outside these windows, do not look for manipulation setups.

## Key Time References

### True Session Open: 07:30 EST
- The 07:30 EST opening price is the **True Session Open** for NY
- Acts as a dividing line for premium/discount within the session:
  - If bearish bias: sell above the 07:30 open
  - If bullish bias: buy below the 07:30 open

### Midnight Open: 00:00 EST
- The midnight open is a key reference level for the entire trading day
- Price often returns to or reacts at the midnight open during the NY session
- Mark this level daily

### Session Quarter Times
Each session can be divided into quarters for more granular analysis:

| NY AM Quarters | Hours (EST) |
|---------------|-------------|
| Q1 | 06:00 - 07:30 |
| Q2 | 07:30 - 09:00 |
| Q3 | 09:00 - 10:30 |
| Q4 | 10:30 - 12:00 |

## Weekly Cycle

| Day | Typical Role | Notes |
|-----|-------------|-------|
| **Monday** | Accumulation | Sets the week's range; can also be expansion if Friday accumulated |
| **Tuesday** | Manipulation | Often the day of the week's manipulation move |
| **Wednesday** | Manipulation / Distribution | Key reversal day; often sets the week's high or low |
| **Thursday** | Distribution / Continuation | Follow-through from Wednesday's move |
| **Friday** | Continuation / Reversal | Can reverse Thursday's move; low probability for new setups |

### True Week Open
- **18:00 EST Sunday** is the True Week Open
- Mark this level and use it as a weekly premium/discount reference

## Daily Chart Preparation Checklist

At **09:30 EST** each day, annotate these levels on your chart:

1. Previous Day High (PDH) and Previous Day Low (PDL)
2. Previous Week High (PWH) and Previous Week Low (PWL)
3. Asia Session High and Low (18:00-00:00 EST)
4. London Session High and Low (00:00-06:00 EST)
5. Pre-Market Range High and Low (06:00-07:30 EST)
6. Midnight Open (00:00 EST price)
7. True Session Open (07:30 EST price)
8. Any relevant HTF FVGs and order blocks

## Agent Detection Logic

```
function get_current_session(timestamp_est):
    hour = timestamp_est.hour
    minute = timestamp_est.minute
    time_decimal = hour + minute / 60
    
    if 18.0 <= time_decimal or time_decimal < 0.0:
        return ASIA
    elif 0.0 <= time_decimal < 6.0:
        return LONDON
    elif 6.0 <= time_decimal < 7.5:
        return NY_PRE_MARKET
    elif 7.5 <= time_decimal < 12.0:
        return NY_AM
    elif 12.0 <= time_decimal < 16.0:
        return NY_PM
    else:
        return NY_CLOSE

function is_killzone(timestamp_est):
    hour = timestamp_est.hour
    minute = timestamp_est.minute
    time_decimal = hour + minute / 60
    
    london_kz = 1.5 <= time_decimal < 4.5   # 01:30 - 04:30
    ny_kz = 7.5 <= time_decimal < 10.5      # 07:30 - 10:30
    
    return london_kz or ny_kz

function get_time_based_liquidity(candles, date):
    tbl = {}
    
    # Asia session (previous day 18:00 to current day 00:00)
    asia = filter_candles(candles, start=date-1d 18:00, end=date 00:00)
    tbl['asia_high'] = max(c.high for c in asia)
    tbl['asia_low'] = min(c.low for c in asia)
    
    # London session
    london = filter_candles(candles, start=date 00:00, end=date 06:00)
    tbl['london_high'] = max(c.high for c in london)
    tbl['london_low'] = min(c.low for c in london)
    
    # Pre-market range
    pre = filter_candles(candles, start=date 06:00, end=date 07:30)
    tbl['pre_high'] = max(c.high for c in pre)
    tbl['pre_low'] = min(c.low for c in pre)
    
    # Previous day
    prev_day = filter_candles(candles, date=date-1)
    tbl['pdh'] = max(c.high for c in prev_day)
    tbl['pdl'] = min(c.low for c in prev_day)
    
    # Key opens
    tbl['midnight_open'] = get_price_at(candles, date, 00:00)
    tbl['session_open'] = get_price_at(candles, date, 07:30)
    
    return tbl
```
