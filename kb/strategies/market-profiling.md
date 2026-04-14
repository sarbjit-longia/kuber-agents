# Market Profiling

## Definition

Market Profiling is a framework for anticipating the formation of weekly and daily candles using ICT concepts. It identifies three weekly profiles and three daily profiles that repeat in the market. High-probability daily profiles align with defined weekly profiles — **you cannot have one without the other**.

## Three Weekly Profiles

### 1. Classic Expansion

The most common weekly profile. Monday-Tuesday sets up, Wednesday-Thursday expands, Friday may retrace.

**Bullish Classic Expansion**:
- Monday-Tuesday forms the **low of the week** by engaging a discount PD array on H4+
- Tuesday-Thursday: expansion toward the weekly draw on liquidity
- Thursday-Friday: reaches the objective

**Bearish Classic Expansion**:
- Monday-Tuesday forms the **high of the week** at a premium PD array
- Expansion downward Tuesday-Thursday

**Ideal Sequence**:
1. Monday = Accumulation (range-bound)
2. Tuesday = Manipulation (Judas swing into H4 PD array → forms high/low of week)
3. Wednesday-Thursday = Expansion toward weekly draw on liquidity
4. Friday = Return into range (TGIF setup)

**High-Probability Days**:
| Day | Rating | Role |
|-----|--------|------|
| Monday | Avoid | Accumulation / Judas swing |
| Tuesday | 4/5 | Expansion candidate |
| Wednesday | 5/5 | Ideal day — bulk of expansion |
| Thursday | 4.5/5 | Continuation to weekly draw |
| Friday | 3/5 | TGIF counter-trend (0.20-0.30 retracement) |

**Negative Conditions** (low probability):
- Monday accumulation → Tuesday expansion with no manipulation
- Monday opening expansion directly toward weekly draw (no manipulation phase)

### 2. Consolidation Reversal

Market consolidates Monday-Wednesday, then reverses Thursday-Friday.

**Condition**: Requires daily consolidation (smaller range candles without displacement, trading within equilibrium).

**Bullish Consolidation Reversal**:
- Monday-Wednesday: Consolidation within a defined range
- Thursday: Manipulation to the external consolidation range **low** (sweeps sell-side liquidity)
- Friday: Expansion higher

**Bearish Consolidation Reversal**:
- Thursday: Manipulation to the external consolidation range **high** (sweeps buy-side)
- Friday: Expansion lower

**High-Probability Days**:
| Day | Rating | Role |
|-----|--------|------|
| Thursday | 4/5 | Speculating on manipulation of range extreme |
| Friday | 5/5 | Ideal day — confirmed reversal + clear draw |

**Targets**:
- Thursday: Equilibrium (50% of consolidation range)
- Friday: Consolidation range extreme (high or low)

### 3. Midweek Reversal

Two variants: Accumulation and Retracement.

**Bullish Midweek Reversal**:
- Monday-Tuesday: Accumulation (sideways) or retracement (down into discount)
- Wednesday: Manipulation into H4+ discount PD array → **reversal day** (low of week)
- Thursday-Friday: Expansion toward draw on liquidity

**Bearish Midweek Reversal**: Inverse of above.

**High-Probability Days**:
| Day | Rating | Role |
|-----|--------|------|
| Wednesday | 3.5/5 | Reversal day |
| Thursday | 5/5 | Ideal day — bulk of expansion |
| Friday | 4.5/5 | Continuation |

**Negative Condition**: Two consecutive same-direction daily candles Monday-Tuesday toward weekly objective with no manipulation/accumulation → no valid profile.

## Three Daily Profiles

### 1. London Reversal
- London session (02:00-05:00 EST) forms the day's reversal (Judas swing)
- Price engages H1+ PD array above/below midnight open
- NY session carries the expansion

**Candle Patterns**:
- Bullish: OLHC (Open → Low in London → High in NY → Close near high)
- Bearish: OHLC (Open → High in London → Low in NY → Close near low)

### 2. New York Manipulation
- London consolidates (no reversal)
- NY creates the manipulation into external consolidation range + H1 PDA confluence
- Then expands toward daily draw on liquidity
- Most common on 8:30 AM high-impact news days (CPI, NFP, FOMC)

### 3. New York Reversal
- London forms the Judas swing (protraction)
- NY reverses and expands
- London pushes above/below midnight open → NY reverses at PDA → expands

## TGIF Setup (Friday Counter-Trend)

After the weekly objective is achieved by Thursday:
- Friday retraces **0.20-0.30** of the weekly range (measured from week high to low)
- Use SMT divergence for confluence
- Counter-trend play only — smaller targets

## Simplified Protocol

1. **Avoid Monday** — study the range for Tuesday
2. **Check economic calendar** — avoid days before first high-impact news of the week
3. **Build H4+ framework** — identify PD arrays for reversal and draw on liquidity
4. **Identify weekly profile** — Classic Expansion, Consolidation Reversal, or Midweek Reversal
5. **Confirm with H1 CISD** — H1-H4 candle close above/below breaker on the expected day

## PD Array Reference (Premium to Discount)

| Premium (Sell Zone) | | Discount (Buy Zone) |
|--------------------|-|---------------------|
| External High | | |
| Rejection Block (-RB) | | |
| Order Block (-OB) | | |
| Breaker Block (-BRK) | | |
| Fair Value Gap (-FVG) | | |
| | **Equilibrium (50%)** | |
| | | Fair Value Gap (+FVG) |
| | | Breaker Block (+BRK) |
| | | Order Block (+OB) |
| | | Rejection Block (+RB) |
| | | External Low |

## Agent Detection Logic

```
function identify_weekly_profile(daily_candles_this_week, day_of_week):
    mon = daily_candles_this_week[0] if len(daily_candles_this_week) > 0 else None
    tue = daily_candles_this_week[1] if len(daily_candles_this_week) > 1 else None
    wed = daily_candles_this_week[2] if len(daily_candles_this_week) > 2 else None
    
    if not tue:
        return UNKNOWN, "Need at least Tuesday data"
    
    # Check for Classic Expansion
    if mon and is_consolidation(mon) and is_manipulation(tue):
        return CLASSIC_EXPANSION, "Monday accumulated, Tuesday manipulated"
    
    # Check for Consolidation Reversal
    if mon and tue and is_consolidation(mon) and is_consolidation(tue):
        if wed and is_consolidation(wed):
            return CONSOLIDATION_REVERSAL, "Mon-Wed consolidated, expect Thu manipulation"
    
    # Check for Midweek Reversal
    if mon and tue:
        same_direction = (mon.close > mon.open) == (tue.close > tue.open)
        if not same_direction or is_small_range(mon):
            return MIDWEEK_REVERSAL, "Mon-Tue accumulation/retracement, expect Wed reversal"
    
    return UNKNOWN, "Profile not yet identifiable"

function get_daily_profile(london_candles, ny_candles, midnight_open):
    london_high = max(c.high for c in london_candles)
    london_low = min(c.low for c in london_candles)
    london_range = london_high - london_low
    
    # London Reversal: London makes the day's high or low
    if london_range > average_london_range * 1.2:
        if london_low < midnight_open:
            return LONDON_REVERSAL_BULLISH, "London swept below midnight open"
        elif london_high > midnight_open:
            return LONDON_REVERSAL_BEARISH, "London swept above midnight open"
    
    # NY Manipulation: London consolidated
    if london_range < average_london_range * 0.7:
        return NY_MANIPULATION, "London consolidated — expect NY manipulation"
    
    return NY_REVERSAL, "Default: London protracted, NY reverses"
```
