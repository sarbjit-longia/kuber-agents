# Power of Three (PO3) / AMD Cycle

## Definition

Power of Three (PO3) describes the three phases of any price move within a defined time range. Every candle on every timeframe follows this pattern. Understanding PO3 allows you to anticipate where the manipulation will occur and position for the true distribution move.

## The Three Phases

### 1. Accumulation (A)
- **What**: The consolidation phase where price builds a range
- **Purpose**: Institutions accumulate positions within a tight range
- **On chart**: Sideways, low-volatility price action; the open of the candle/session
- **Duration**: Varies by timeframe — can be minutes (on M1) or days (on Weekly)

### 2. Manipulation (M)
- **What**: The fake move in the opposite direction of the true intended move
- **Purpose**: Sweep liquidity (stop losses) to fill institutional orders at better prices
- **On chart**: A wick that extends in the opposite direction of the eventual close
- **Key rule**: This is where retail traders get trapped — they enter in the manipulation direction

### 3. Distribution (D)
- **What**: The true move in the actual intended direction
- **Purpose**: Institutions distribute (execute) their positions in the real direction
- **On chart**: The strong body/close of the candle that moves away from the manipulation
- **Key rule**: This is where you want to be positioned — in the direction of distribution

## OHLC Candle Framework

Every candle tells a PO3 story through its Open, High, Low, and Close:

### Bullish PO3: O → L → H → C (OLHC)
1. Price **Opens** (Accumulation)
2. Price dips **Lower** first (Manipulation — sweeps sell-side liquidity)
3. Price rallies to the **High** (Distribution begins)
4. Price **Closes** near the high (Distribution complete)

### Bearish PO3: O → H → L → C (OHLC)
1. Price **Opens** (Accumulation)
2. Price pushes **Higher** first (Manipulation — sweeps buy-side liquidity)
3. Price drops to the **Low** (Distribution begins)
4. Price **Closes** near the low (Distribution complete)

## PO3 Across Timeframes

### HTF Candle View
On a daily candle:
- The **open** = where accumulation happened
- The **wick** in the manipulation direction = the manipulation phase
- The **body close** in the distribution direction = the distribution phase

### LTF View of a Bullish Daily PO3
When you zoom into a bullish daily candle on M15/M5:
1. Asian session consolidation near the open (Accumulation)
2. London/early NY sweep below the Asian lows (Manipulation)
3. NY session displacement upward with FVGs (Distribution)
4. Price closes near session high

## Weekly PO3 Cycle

| Day | Phase | Notes |
|-----|-------|-------|
| **Monday** | Accumulation | Sets the week's initial range. Can be expansion if Friday was accumulation. |
| **Tuesday** | Manipulation | Often the day that creates the week's manipulation move (fake direction) |
| **Wednesday** | Manipulation / Distribution | Key reversal day. Often sets the week's actual high or low. |
| **Thursday** | Distribution | Follow-through in the real direction |
| **Friday** | Distribution / Reversal | Can continue or reverse; reduced probability for new setups |

### True Week Open
- **18:00 EST Sunday** marks the True Week Open
- The week's manipulation phase will often sweep above or below this level before distribution

## AMDX vs XAMD

Within any defined time range, expect one of two sequences:

### AMDX (Accumulation → Manipulation → Distribution → Continuation/Reversal)
- Standard sequence when a new cycle begins fresh
- Accumulation first, then fake move, then real move, then either continuation or reversal

### XAMD (Continuation/Reversal → Accumulation → Manipulation → Distribution)
- Occurs when the previous cycle's distribution carries over
- Price continues from the prior session's move, then accumulates, manipulates, and distributes again

### Rule
Determine which pattern is active based on the previous session's close and the current session's behavior.

## Daily PO3 Session Map

| Phase | Time (EST) | Session |
|-------|-----------|---------|
| Accumulation | 18:00 - 00:00 | Asia Session |
| Manipulation | 00:00 - 06:00 or 07:30 - 09:30 | London or NY Open |
| Distribution | 09:30 - 12:00 | NY AM Session |
| Continuation/X | 12:00 - 16:00 | NY PM Session |

## Practical Application

### Step 1: Identify the Phase
Ask: "Where are we in the PO3 cycle?"
- If price is ranging near the open → **Accumulation** (wait)
- If price just swept liquidity against bias → **Manipulation** (prepare to enter)
- If price is displacing in bias direction → **Distribution** (already in or late entry only)

### Step 2: Trade the Transition
The highest-probability entry is at the **Manipulation → Distribution transition**:
1. Wait for manipulation (liquidity sweep)
2. Confirm with LTF MSS + displacement
3. Enter in the distribution direction
4. Target the opposing liquidity pool

## Agent Detection Logic

```
function detect_po3_phase(candles, session_open, bias):
    current_price = candles[-1].close
    session_high = max(c.high for c in candles)
    session_low = min(c.low for c in candles)
    
    range_size = session_high - session_low
    distance_from_open = current_price - session_open
    
    if range_size < atr * 0.3:  # Tight range
        return ACCUMULATION
    
    if bias == BULLISH:
        if current_price < session_open and range_size > atr * 0.3:
            return MANIPULATION  # Price swept below open
        elif current_price > session_open and has_displacement(candles[-3:]):
            return DISTRIBUTION  # Displacing above open
    
    if bias == BEARISH:
        if current_price > session_open and range_size > atr * 0.3:
            return MANIPULATION  # Price swept above open
        elif current_price < session_open and has_displacement(candles[-3:]):
            return DISTRIBUTION  # Displacing below open
    
    return UNKNOWN

function identify_weekly_po3(daily_candles, week_start_sunday_6pm):
    monday = daily_candles[0]
    tuesday = daily_candles[1]
    wednesday = daily_candles[2]
    
    # Check if Tuesday manipulation occurred
    if monday.range < atr:  # Monday was accumulation (tight range)
        if tuesday swept monday's high or low:
            manipulation_day = TUESDAY
        elif wednesday swept tuesday's or monday's high or low:
            manipulation_day = WEDNESDAY
    
    return {
        "accumulation": monday,
        "manipulation_day": manipulation_day,
        "expected_distribution": THURSDAY
    }
```
