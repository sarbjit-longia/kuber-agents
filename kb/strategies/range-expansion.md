# Range Expansion Strategy

## Definition

Described as "the simplest ICT strategy." It identifies an impulse move, waits for a retracement into premium/discount with a liquidity sweep, then enters on confirmation of continuation. Uses Fibonacci for both entry zones and targets.

## 3-Step Process

### Step 1: Identify Impulse + Apply Fibonacci (HTF)

**What is an impulse?**
Any expansive move from a low to a high (or vice versa) that pushes and **closes violently** through a previous high or low. The impulse reveals:
- The overall direction (which side — buyers or sellers — is in control)
- Where premium and discount zones are

**Process**:
1. Find the most recent impulse on the HTF (H4, H1, or Daily)
2. Apply a Fibonacci retracement to the impulse leg
3. Identify zones:
   - **Discount** (below 0.5) = Look for buys in bullish impulses
   - **Premium** (above 0.5) = Look for sells in bearish impulses

### Step 2: LTF Sweep + Rejection

Switch to a lower timeframe within the impulse.

**Process**:
1. Wait for liquidity to form around discount (lows, for buys) or premium (highs, for sells)
2. Wait for that liquidity to be **swept**
3. Watch for a **violent rejection/reaction** after the sweep

**Confirmation signals** (probability increasers):
- Price is also trading into an FVG prior to the reversal
- The candle that signifies the reversal pushes violently back through the swept high/low
- The rejection creates displacement (large body candle, FVGs forming)

### Step 3: Entry + Targeting

**Entry** — on any of these confirmations:
- A Market Structure Shift (MSS)
- A change in the state of delivery (CISD)
- A failure to displace at the liquidity level (manipulation confirmed)

**Stop Loss**: At the low/high made during the liquidity sweep

**Targeting** — use the HTF impulse to derive targets:
1. Look for a **Market Maker Model**: a series of 3 consolidations moving into a key level
2. When the market reverses, target the **original (first) consolidation** to be taken out
3. Additional targets: the opposing Fibonacci extension levels (-1, -1.618, -2)

**The Narrative**: Price trading into a key level that is likely to cause a reversal provides the reason for expecting a Market Maker Model to complete.

## Fibonacci Levels for Entry and Targeting

### Entry Zones (Retracement)

| Level | Zone | Usage |
|-------|------|-------|
| 0.382 | Discount | Shallowest entry zone |
| 0.5 | Equilibrium | Fair value dividing line |
| 0.618 | OTE zone start | Optimal trade entry begins |
| 0.705 | OTE sweet spot | Best entry within OTE |
| 0.786 | OTE zone end | Deepest valid entry |

### Target Zones (Extension)

| Level | Usage |
|-------|-------|
| -0.272 | First extension target |
| -0.618 | Second extension target |
| -1.0 | Full measured move |
| -1.618 | Extended target |
| -2.0 | Full extension (Market Maker Model original consolidation) |

## Example Workflow

### Bullish Setup
1. **HTF**: Daily chart shows bullish impulse from $100 to $120 (broke above previous high at $115 with displacement)
2. **Fibonacci**: Drawn from $100 (low) to $120 (high). Discount zone = below $110 (0.5 level). OTE = $107.64 (0.618) to $104.28 (0.786).
3. **LTF**: On H1, price retraces into the $107-$105 zone. Equal lows form at $106. Price sweeps below $106 to $105.50.
4. **Rejection**: Price violently bounces from $105.50. Large bullish candle with FVG. MSS on M15 confirms.
5. **Entry**: Long at $106.50 (MSS level). Stop at $105.30 (below sweep low). Risk = $1.20.
6. **Target**: $120 (impulse high) or beyond. R:R = 11:1+.

## Agent Detection Logic

```
function range_expansion_scan(htf_candles, ltf_candles):
    # Step 1: Find impulse on HTF
    impulse = find_most_recent_impulse(htf_candles)
    if not impulse:
        return NO_TRADE, "No clear impulse on HTF"
    
    # Calculate premium/discount
    fib = calculate_fibonacci(impulse.low, impulse.high)
    current_price = ltf_candles[-1].close
    
    if impulse.direction == BULLISH:
        if current_price > fib[0.5]:
            return NO_TRADE, "Price in premium for bullish impulse"
        entry_zone = (fib[0.618], fib[0.786])  # OTE zone
        bias = BULLISH
    else:
        if current_price < fib[0.5]:
            return NO_TRADE, "Price in discount for bearish impulse"
        entry_zone = (fib[0.382], fib[0.214])  # Premium OTE zone
        bias = BEARISH
    
    # Step 2: Check for liquidity sweep at entry zone
    if not (entry_zone[0] <= current_price <= entry_zone[1]):
        return NO_TRADE, "Price not in OTE zone"
    
    # Look for sweep + rejection
    ltf_liquidity = find_liquidity_levels(ltf_candles)
    sweep = detect_liquidity_sweep(ltf_candles[-20:], ltf_liquidity)
    
    if not sweep:
        return NO_TRADE, "No liquidity sweep at OTE"
    
    rejection = detect_rejection_after_sweep(ltf_candles, sweep)
    if not rejection:
        return NO_TRADE, "No rejection after sweep"
    
    # Step 3: Entry
    mss = detect_mss(ltf_candles, current_structure=opposite(bias))
    if not mss:
        return NO_TRADE, "No MSS confirmation"
    
    entry = mss.candle.close
    stop = sweep.extreme_price
    risk = abs(entry - stop)
    
    # Target: impulse high/low or MMXM original consolidation
    if bias == BULLISH:
        target = impulse.high  # Minimum target
    else:
        target = impulse.low
    
    reward = abs(target - entry)
    
    return TRADE_SIGNAL(
        direction=bias,
        entry=entry,
        stop_loss=stop,
        take_profit=target,
        r_multiple=reward / risk,
        fib_entry_level=calculate_fib_level(entry, impulse.low, impulse.high)
    )
```
