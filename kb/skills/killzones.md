---
skill_id: kb_skill_killzones
name: Killzones
category: ict
agent_types: [strategy_agent, bias_agent]
recommended_tools: [liquidity_analyzer, market_structure]
tags: [ict, time, session, killzone]
---

# Killzones

## Definition

Killzones are specific time windows during the trading day when the highest-probability setups occur. These windows coincide with the transition between Power of Three phases (Manipulation → Distribution) and are when institutional algorithms are most active. **Only look for manipulation-based entries during killzones.**

## Primary Killzones (All Times EST)

| Killzone | Hours | Primary Action |
|----------|-------|---------------|
| **London Killzone** | 01:30 - 04:30 | Manipulation of Asia session range |
| **NY Killzone** | 07:30 - 10:30 | Manipulation of London/pre-market range |
| **NY AM Focus** | 09:00 - 10:30 | Most precise window for NY entries |

## Secondary Windows

| Window | Hours (EST) | Purpose |
|--------|-------------|---------|
| **Silver Bullet Window 1** | 10:00 - 11:00 | First FVG entry window (Silver Bullet strategy) |
| **Silver Bullet Window 2** | 14:00 - 15:00 | Second FVG entry window |
| **NY PM Session** | 13:30 - 16:00 | Continuation trades or reversals |

## Session Context for Each Killzone

### London Killzone (01:30 - 04:30 EST)
- **What to expect**: Manipulation of Asia session highs/lows
- **Typical pattern**: Price sweeps Asia high or low, then reverses
- **Entry**: After sweep of Asia liquidity + MSS on LTF
- **Target**: Opposing liquidity (if Asia low swept → target above Asia high, vice versa)
- **Daily profile**: London Reversal or NY Reversal (Judas swing in London)

### NY Killzone (07:30 - 10:30 EST)
- **What to expect**: Manipulation of London range and/or pre-market (06:00-07:30) range
- **Key reference**: 07:30 EST opening price (True Session Open)
- **Typical pattern**: Price sweeps London/pre-market liquidity, then reverses or expands
- **Entry**: After TBL sweep + MSS on M1/M5

### NY AM Focus (09:00 - 10:30 EST)
- **Most precise entry window** for NY session
- **09:30**: Market open — prepare charts with all TBL annotations
- **09:30 - 10:00**: Opening range forms (key highs/lows the algorithm references all day)
- **10:00 - 11:00**: Silver Bullet window — first FVG entry opportunity

## Pre-Killzone Preparation

### At 09:30 EST (NY Open), Annotate:
1. Asia Session High/Low (18:00-00:00 EST)
2. London Session High/Low (00:00-06:00 EST)
3. Pre-Market Range High/Low (06:00-07:30 EST)
4. Previous Day High (PDH) and Low (PDL)
5. Previous Week High (PWH) and Low (PWL)
6. Midnight Open (00:00 EST price)
7. True Session Open (07:30 EST price)
8. NDOG (New Day Opening Gap): 16:59 close to 18:00 open range
9. HTF FVGs and Order Blocks

## Rules

### Rule 1: Only Trade During Killzones
Outside killzone windows, do not look for manipulation-based entries. The probability of valid setups drops significantly.

### Rule 2: News Amplifies Killzones
High-impact economic releases (CPI, NFP, FOMC, PCE, GDP, PPI) during killzones amplify the manipulation and create the strongest setups.

- **8:30 AM EST news**: Wait for data release, then look for manipulation → distribution during the 09:00-10:30 focus window
- **No 8:30 news**: Can still trade but with reduced conviction; look to PM session (13:30+)

### Rule 3: Opening Range (09:30-10:00) Is Sacred
- 70% of the time, the Opening Range Gap Consequent Encroachment (CE) is hit before 10:00 AM
- The first FVG formed between 09:30-10:00 is significant and can be used as a reference for the entire trading day
- The opening range high/low are key levels the algorithm references throughout the day

## Weekly Killzone Map

| Day | Rating | Best Killzone | Notes |
|-----|--------|---------------|-------|
| **Monday** | 2/5 | Avoid | Accumulation day; study the range for Tuesday |
| **Tuesday** | 4/5 | London & NY | Expansion candidate; high/low of week often forms |
| **Wednesday** | 5/5 | London & NY | Ideal day; bulk of weekly expansion |
| **Thursday** | 4.5/5 | NY | Continuation toward weekly draw on liquidity |
| **Friday** | 3/5 | NY AM only | TGIF counter-trend possible; reduced conviction |

## Agent Detection Logic

```
function is_in_killzone(timestamp_est):
    hour = timestamp_est.hour
    minute = timestamp_est.minute
    t = hour + minute / 60.0
    
    killzones = {
        "london": (1.5, 4.5),        # 01:30 - 04:30
        "ny": (7.5, 10.5),           # 07:30 - 10:30
        "ny_focus": (9.0, 10.5),     # 09:00 - 10:30
        "silver_bullet_1": (10.0, 11.0),  # 10:00 - 11:00
        "silver_bullet_2": (14.0, 15.0),  # 14:00 - 15:00
    }
    
    active = []
    for name, (start, end) in killzones.items():
        if start <= t < end:
            active.append(name)
    
    return active if active else None

function get_day_quality(day_of_week):
    """Returns trading quality rating for the day."""
    ratings = {
        "Monday": 2,
        "Tuesday": 4,
        "Wednesday": 5,
        "Thursday": 4.5,
        "Friday": 3
    }
    return ratings.get(day_of_week, 0)

function should_trade(timestamp_est, has_news_at_830=False):
    killzone = is_in_killzone(timestamp_est)
    day_quality = get_day_quality(timestamp_est.strftime("%A"))
    
    if not killzone:
        return False, "Outside killzone"
    if day_quality <= 2:
        return False, "Low-quality day (Monday)"
    if has_news_at_830 and "ny_focus" in killzone:
        return True, "High-probability: News day + NY focus killzone"
    if killzone:
        return True, f"In killzone: {killzone}"
```
