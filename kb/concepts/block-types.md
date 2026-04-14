# ICT Block Types — Complete Reference

*Source: ICT Block Types Guide by Lucius*

## Overview

Blocks are specific candle-level price structures that institutional traders use to enter, exit, and manage positions. Each block type has different formation rules, significance, and trading applications. There are **7 primary block types** in ICT methodology.

| Block Type | Role | Key Feature |
|-----------|------|-------------|
| [Order Block](#1-order-blocks) | Primary S/R from institutional orders | Last opposing candle before displacement |
| [Mitigation Block](#2-mitigation-blocks) | S/R from trapped traders exiting | Losing side mitigates losses on retrace |
| [Breaker Block](#3-breaker-blocks) | Flipped OB after structure break | Failed OB becomes S/R in opposite direction |
| [Rejection Block](#4-rejection-blocks) | S/R from wick-based rejection | Double-wick rejection at extremes |
| [Reclaimed Order Block](#5-reclaimed-order-blocks) | Old OBs reused in MMXM context | OBs from sell-side become buy-side S/R |
| [Propulsion Block](#6-propulsion-blocks) | Cascading S/R in trending markets | OB that bounced off another OB |
| [Vacuum Block](#7-vacuum-blocks) | Gap-fill S/R from volatility events | NFP/session gaps treated as ranges |

---

## 1. Order Blocks

### Definition
The **last opposing candle** before an expansive displacement move. It represents where institutional orders were placed.

### Bullish Order Block
- The **lowest candle with a down-close** that has the most range between open-close, near a "support" level
- When price retraces to this level, expect support (institutional buy orders resting here)

### Bearish Order Block
- The **highest candle with an up-close** that has the most range between open-close, near a "resistance" level
- When price retraces to this level, expect resistance (institutional sell orders resting here)

### Validation Rule
The OB is validated when its extreme (high of bullish OB / low of bearish OB) is **traded through** by a subsequent candle, then price reverses.

### Mean Threshold (50%) Rule
Use Fibonacci on the OB candle's open-to-close:
- **Bullish OB**: Price should NOT close below the 50% level. If it does → OB is likely invalidated.
- **Bearish OB**: Price should NOT close above the 50% level.

### Recommended Practice
Use only **candle bodies** (open to close), not wicks, for OB delineation — wicks vary between brokers.

### Trading Rules
- **Entry**: When price retraces to the OB open after displacement
- **Stop Loss**: Below the low (bullish) or above the high (bearish) of the OB candle
- **Take Profit**: Buy stops above (bullish) or sell stops below (bearish) as first/full TP

### Liquidity-Based Bias with OBs
- **Bullish**: Wait for 4H and lower to retrace. Anticipate discount + sell-side liquidity sweep. Look for price to respect the bullish OB → impulsive move up.
- **Bearish**: Wait for correction upward. Anticipate premium + buy-side liquidity sweep. Look for price to respect the bearish OB → strong reaction down.

### Detection Pseudocode

```python
def detect_order_blocks(candles, atr, min_displacement_ratio=1.5):
    """
    Find order blocks by looking for the last opposing candle 
    before a displacement move.
    """
    obs = []
    
    for i in range(2, len(candles) - 2):
        # Measure displacement: total move over next 3 candles
        move = candles[i + 2].close - candles[i].close
        
        # BULLISH DISPLACEMENT detected
        if move > atr * min_displacement_ratio:
            # Walk back to find the last DOWN-close candle
            for j in range(i, max(i - 5, 0), -1):
                if candles[j].close < candles[j].open:  # Down-close
                    body = abs(candles[j].close - candles[j].open)
                    obs.append({
                        "type": "BULLISH_OB",
                        "high": candles[j].high,
                        "low": candles[j].low,
                        "open": candles[j].open,
                        "close": candles[j].close,
                        "mean_threshold": (candles[j].open + candles[j].close) / 2,
                        "index": j,
                        "body_size": body
                    })
                    break
        
        # BEARISH DISPLACEMENT detected
        if move < -atr * min_displacement_ratio:
            for j in range(i, max(i - 5, 0), -1):
                if candles[j].close > candles[j].open:  # Up-close
                    body = abs(candles[j].close - candles[j].open)
                    obs.append({
                        "type": "BEARISH_OB",
                        "high": candles[j].high,
                        "low": candles[j].low,
                        "open": candles[j].open,
                        "close": candles[j].close,
                        "mean_threshold": (candles[j].open + candles[j].close) / 2,
                        "index": j,
                        "body_size": body
                    })
                    break
    
    return obs


def validate_order_block(ob, subsequent_candles):
    """
    Check if OB's mean threshold (50%) holds when price returns.
    """
    for candle in subsequent_candles:
        price_touched = False
        
        if ob["type"] == "BULLISH_OB":
            # Price retraced into the OB zone
            if candle.low <= ob["open"]:
                price_touched = True
                if candle.close < ob["mean_threshold"]:
                    return "INVALIDATED"  # Closed below 50%
                else:
                    return "VALIDATED"    # Held the 50% level
        
        elif ob["type"] == "BEARISH_OB":
            if candle.high >= ob["open"]:
                price_touched = True
                if candle.close > ob["mean_threshold"]:
                    return "INVALIDATED"
                else:
                    return "VALIDATED"
    
    return "UNTESTED"
```

---

## 2. Mitigation Blocks

### Definition
When price breaks structure and shifts direction, the **losing side** (trapped traders) will look to **mitigate their losses** when price returns to the origin of the move. The level where these trapped traders exit becomes the mitigation block.

### Bearish Mitigation Block
1. Price pushes into a resistance level
2. A short-term rally forms (traders go long)
3. **Market Structure Break (MSB)** — price breaks lower, shifting structure
4. Focus on the **last down-close candle** inside the low of the price action before the MSB
5. When price retraces back to this area → trapped longs exit (mitigate losses) → selling pressure
6. The level acts as resistance → price continues lower

### Bullish Mitigation Block
- Inverse: trapped shorts closing positions at a higher low formed after an upward structure shift
- Creates buying pressure when price returns

### Key Difference from Order Blocks
- **Order Block**: Formed BEFORE displacement (where institutional orders were placed)
- **Mitigation Block**: Formed AFTER a structure break (where trapped traders will exit)

### Detection Pseudocode

```python
def detect_mitigation_blocks(candles, swing_points):
    """
    Find mitigation blocks by identifying structure breaks and 
    the last opposing candle at the origin of the failed move.
    """
    mitigations = []
    
    for i in range(2, len(swing_points)):
        prev_swing = swing_points[i - 1]
        curr_swing = swing_points[i]
        
        # BEARISH MITIGATION: Price made a high, then broke structure lower
        if prev_swing.type == "HIGH" and curr_swing.type == "LOW":
            # Structure broke below a previous low
            earlier_low = find_previous_low_before(swing_points, prev_swing)
            if earlier_low and curr_swing.price < earlier_low.price:
                # MSB confirmed. Find the last down-close candle 
                # between the earlier low and the swing high
                candles_in_range = get_candles_between(
                    candles, earlier_low.timestamp, prev_swing.timestamp
                )
                for c in reversed(candles_in_range):
                    if c.close < c.open:  # Down-close candle
                        mitigations.append({
                            "type": "BEARISH_MITIGATION",
                            "level_high": c.high,
                            "level_low": c.low,
                            "open": c.open,
                            "close": c.close,
                            "context": "Trapped longs will exit here",
                            "index": c.index
                        })
                        break
        
        # BULLISH MITIGATION: Price made a low, then broke structure higher
        if prev_swing.type == "LOW" and curr_swing.type == "HIGH":
            earlier_high = find_previous_high_before(swing_points, prev_swing)
            if earlier_high and curr_swing.price > earlier_high.price:
                candles_in_range = get_candles_between(
                    candles, earlier_high.timestamp, prev_swing.timestamp
                )
                for c in reversed(candles_in_range):
                    if c.close > c.open:  # Up-close candle
                        mitigations.append({
                            "type": "BULLISH_MITIGATION",
                            "level_high": c.high,
                            "level_low": c.low,
                            "open": c.open,
                            "close": c.close,
                            "context": "Trapped shorts will exit here",
                            "index": c.index
                        })
                        break
    
    return mitigations
```

---

## 3. Breaker Blocks

### Definition
When a market structure shift causes a previous order block to **fail**, the failed OB "flips" its polarity — a bearish OB becomes bullish support, and vice versa. The breaker represents where market makers return to stop out "dumb money" before continuing.

### Bullish Breaker Block
- An **up-close candle** in the most recent swing HIGH prior to an old LOW being violated
- Price violates the old low (runs sell stops) → reprices higher → retraces to the old high's up-close candle
- This candle is now a bullish breaker block (support)

### Bearish Breaker Block
- A **down-close candle** in the most recent swing LOW prior to an old HIGH being violated
- Price runs above the old high → reprices lower → retraces to the old low's down-close candle
- This candle is now a bearish breaker block (resistance)

### Confirmation
Market Structure Break (MSB) must confirm the breaker is active.

### Detection Pseudocode

```python
def detect_breaker_blocks(candles, swing_points):
    """
    Find breaker blocks by identifying failed order blocks 
    after structure shifts.
    
    Pattern for Bullish Breaker:
      swing_low_1 → swing_high → swing_low_2 (below low_1) → higher_high
      The up-close candle at swing_high = bullish breaker
    
    Pattern for Bearish Breaker:
      swing_high_1 → swing_low → swing_high_2 (above high_1) → lower_low
      The down-close candle at swing_low = bearish breaker
    """
    breakers = []
    
    for i in range(3, len(swing_points)):
        p1 = swing_points[i - 3]
        p2 = swing_points[i - 2]
        p3 = swing_points[i - 1]
        p4 = swing_points[i]
        
        # BULLISH BREAKER: Low → High → Lower Low → Higher High
        if (p1.type == "LOW" and p2.type == "HIGH" and 
            p3.type == "LOW" and p4.type == "HIGH"):
            if p3.price < p1.price and p4.price > p2.price:
                # Find the up-close candle at p2 (the old swing high)
                breaker_candle = find_up_close_candle_near(candles, p2)
                if breaker_candle:
                    breakers.append({
                        "type": "BULLISH_BREAKER",
                        "high": breaker_candle.high,
                        "low": breaker_candle.low,
                        "open": breaker_candle.open,
                        "close": breaker_candle.close,
                        "formation": "Low→High→LowerLow→HigherHigh",
                        "msb_confirmed": True,
                        "index": breaker_candle.index
                    })
        
        # BEARISH BREAKER: High → Low → Higher High → Lower Low
        if (p1.type == "HIGH" and p2.type == "LOW" and 
            p3.type == "HIGH" and p4.type == "LOW"):
            if p3.price > p1.price and p4.price < p2.price:
                breaker_candle = find_down_close_candle_near(candles, p2)
                if breaker_candle:
                    breakers.append({
                        "type": "BEARISH_BREAKER",
                        "high": breaker_candle.high,
                        "low": breaker_candle.low,
                        "open": breaker_candle.open,
                        "close": breaker_candle.close,
                        "formation": "High→Low→HigherHigh→LowerLow",
                        "msb_confirmed": True,
                        "index": breaker_candle.index
                    })
    
    return breakers
```

---

## 4. Rejection Blocks

### Definition
Formed when **two consecutive candles create long wicks** beyond a level, showing double rejection. The wick area represents a zone where price cleared liquidity and was forcefully rejected.

### Bearish Rejection Block
- A price high forms with **two long wicks on the highs** of the candles
- Price pushes above the highest candle's **body** (not just wick), clearing buy-side liquidity
- The range from the highest body to the highest wick = **rejection block range**
- Treat as a bearish order block

**Sell Trigger**: When price trades back down to the **low** of the rejection block range
**Stop Loss**: Slightly above the highest wick

### Bullish Rejection Block
- A price low forms with **two long wicks on the lows** of the candles
- Price reaches below the body to run sell-side liquidity before repricing higher
- Treat as a bullish order block

**Buy Trigger**: When price trades back up to the **high** of the rejection block range
**Stop Loss**: Slightly below the lowest wick

### ICT 2024 Addition
If price forms a rejection block AND a CISD (Change in State of Delivery / OB), price should **NOT** tap into the rejection block — if it does, it nullifies the OB. Kill the trade.

### Detection Pseudocode

```python
def detect_rejection_blocks(candles, min_wick_ratio=0.4):
    """
    Find rejection blocks: two consecutive candles with long wicks 
    in the same direction at a swing point.
    """
    rejections = []
    
    for i in range(1, len(candles)):
        c1 = candles[i - 1]
        c2 = candles[i]
        
        c1_range = c1.high - c1.low
        c2_range = c2.high - c2.low
        if c1_range == 0 or c2_range == 0:
            continue
        
        # BEARISH REJECTION: Two long UPPER wicks
        c1_upper_wick = c1.high - max(c1.open, c1.close)
        c2_upper_wick = c2.high - max(c2.open, c2.close)
        
        if (c1_upper_wick / c1_range > min_wick_ratio and 
            c2_upper_wick / c2_range > min_wick_ratio):
            # Both candles have long upper wicks
            highest_body = max(max(c1.open, c1.close), max(c2.open, c2.close))
            highest_wick = max(c1.high, c2.high)
            lowest_body_of_pair = min(max(c1.open, c1.close), max(c2.open, c2.close))
            
            rejections.append({
                "type": "BEARISH_REJECTION",
                "range_high": highest_wick,       # Top of rejection zone
                "range_low": lowest_body_of_pair,  # Bottom of rejection zone
                "sell_trigger": lowest_body_of_pair,
                "stop_loss": highest_wick + buffer,
                "index": i
            })
        
        # BULLISH REJECTION: Two long LOWER wicks
        c1_lower_wick = min(c1.open, c1.close) - c1.low
        c2_lower_wick = min(c2.open, c2.close) - c2.low
        
        if (c1_lower_wick / c1_range > min_wick_ratio and 
            c2_lower_wick / c2_range > min_wick_ratio):
            lowest_body = min(min(c1.open, c1.close), min(c2.open, c2.close))
            lowest_wick = min(c1.low, c2.low)
            highest_body_of_pair = max(min(c1.open, c1.close), min(c2.open, c2.close))
            
            rejections.append({
                "type": "BULLISH_REJECTION",
                "range_high": highest_body_of_pair,
                "range_low": lowest_wick,
                "buy_trigger": highest_body_of_pair,
                "stop_loss": lowest_wick - buffer,
                "index": i
            })
    
    return rejections
```

---

## 5. Reclaimed Order Blocks

### Definition
Within Market Maker Models, order blocks from one side of the curve (buy-side or sell-side) get **reclaimed** when price enters the opposite side of the curve. Old OBs from the move into the key level become support/resistance for the move away from it.

### In a Market Maker Buy Model (MMBM)
- **Sell-side of curve** (price dropping to the low): OBs are bearish reference points
- **Buy-side of curve** (price bouncing up): Those same old bearish OBs from the sell-side get **reclaimed as bullish support**
- Price makes new higher highs, and old OBs become "reclaimed longs"

### In a Market Maker Sell Model (MMSM)
- **Buy-side of curve** (price rallying to the high): OBs are bullish reference points
- **Sell-side of curve** (price dropping): Old bullish OBs get **reclaimed as bearish resistance**

### Detection Pseudocode

```python
def detect_reclaimed_order_blocks(candles, mmxm_model, original_obs):
    """
    After a Market Maker Model reversal, old OBs from the 
    pre-reversal phase become reclaimed blocks on the post-reversal phase.
    """
    reclaimed = []
    
    if mmxm_model.type == "MMBM":
        reversal_point = mmxm_model.smart_money_reversal  # The low
        
        # OBs from the sell-side of curve (before the reversal)
        sellside_obs = [ob for ob in original_obs 
                        if ob["index"] < reversal_point.index]
        
        for ob in sellside_obs:
            # These were bearish OBs during the drop
            # Now they are reclaimed as bullish support
            reclaimed.append({
                "type": "RECLAIMED_BULLISH",
                "original_ob": ob,
                "high": ob["high"],
                "low": ob["low"],
                "role": "Support on buy-side of curve",
                "context": "Old sell-side OB now reclaimed as long"
            })
    
    elif mmxm_model.type == "MMSM":
        reversal_point = mmxm_model.smart_money_reversal  # The high
        
        buyside_obs = [ob for ob in original_obs 
                       if ob["index"] < reversal_point.index]
        
        for ob in buyside_obs:
            reclaimed.append({
                "type": "RECLAIMED_BEARISH",
                "original_ob": ob,
                "high": ob["high"],
                "low": ob["low"],
                "role": "Resistance on sell-side of curve",
                "context": "Old buy-side OB now reclaimed as short"
            })
    
    return reclaimed
```

---

## 6. Propulsion Blocks

### Definition
A candle that has previously traded **into** an order block and now **takes over the role** of support/resistance for continued movement. Think of it as a cascading OB — the reaction off the original OB creates a new reference point.

### Bullish Propulsion Block
- Multiple bullish OBs indicate bullish order flow
- Price drops into a bullish OB (already predisposed to go higher)
- The candle that bounces off the OB = **bullish propulsion block**
- On subsequent retests, price should **NOT** fall below the 50% (mean threshold) of the propulsion candle
- A reliable propulsion candle gives a strong reaction on retest

### Bearish Propulsion Block
- Underlying context must be bearish
- Price pulls into a bearish OB → candle adopts resistance role
- **Sell trigger**: When price trades back up into the **low** of the propulsion block
- Price should close under the 50% level

### Detection Pseudocode

```python
def detect_propulsion_blocks(candles, order_blocks, atr):
    """
    Find propulsion blocks: candles that reacted off an OB 
    and now serve as secondary S/R.
    """
    propulsions = []
    
    for ob in order_blocks:
        # Find candles that traded into this OB and bounced
        ob_candles = get_candles_after(candles, ob["index"])
        
        for c in ob_candles:
            if ob["type"] == "BULLISH_OB":
                # Candle traded down into the OB zone
                if c.low <= ob["open"] and c.low >= ob["low"]:
                    # Bounced: closed above the OB
                    if c.close > ob["open"]:
                        propulsion_50 = (c.open + c.close) / 2
                        propulsions.append({
                            "type": "BULLISH_PROPULSION",
                            "high": c.high,
                            "low": c.low,
                            "open": c.open,
                            "close": c.close,
                            "mean_threshold": propulsion_50,
                            "parent_ob": ob,
                            "rule": "Price should NOT close below 50%",
                            "index": c.index
                        })
                        break  # Only first reaction matters
            
            elif ob["type"] == "BEARISH_OB":
                if c.high >= ob["open"] and c.high <= ob["high"]:
                    if c.close < ob["open"]:
                        propulsion_50 = (c.open + c.close) / 2
                        propulsions.append({
                            "type": "BEARISH_PROPULSION",
                            "high": c.high,
                            "low": c.low,
                            "open": c.open,
                            "close": c.close,
                            "mean_threshold": propulsion_50,
                            "sell_trigger": c.low,
                            "parent_ob": ob,
                            "rule": "Price should close UNDER 50%",
                            "index": c.index
                        })
                        break
    
    return propulsions
```

---

## 7. Vacuum Blocks

### Definition
A gap in price created by a **volatility event** (NFP, session openings, major news). The gap forms by a "vacuum" of liquidity — no trades occurred in this price range. Treat the gap as a candle/range with its own high, low, and internal structure.

### Bullish Vacuum Block (Gap Up)
- Price opens **higher** than previous close, creating a gap
- Define the gap's **high** and **low** as if it were a candle
- Look for a **bullish order block** (down-close candle) within the gap
- This OB can stop the gap from filling entirely → buying opportunity
- If the gap fills 100% → different buying opportunity at the bottom, but if price then rallies, you do NOT want it to return to the fully filled vacuum block

### Bearish Vacuum Block (Gap Down)
- Price opens **lower**, creating a gap
- Look for a **bearish order block** (up-close candle) within the gap
- Same fill logic applies in reverse

### Gap Fill Probabilities
- **Corrective move** (partial fill, then continuation): **More probable**
- **Exhaustion gap** (full reversal): **Less probable**

### Detection Pseudocode

```python
def detect_vacuum_blocks(candles, min_gap_atr=0.5):
    """
    Find vacuum blocks: gaps between session closes and opens,
    typically from overnight/weekend volatility events.
    """
    vacuums = []
    atr = calculate_atr(candles)
    
    for i in range(1, len(candles)):
        prev = candles[i - 1]
        curr = candles[i]
        
        # Detect gap: current open significantly different from previous close
        gap = curr.open - prev.close
        
        if abs(gap) > atr * min_gap_atr:
            if gap > 0:
                # BULLISH VACUUM (gap up)
                vacuum = {
                    "type": "BULLISH_VACUUM",
                    "high": curr.open,       # Top of gap
                    "low": prev.close,       # Bottom of gap
                    "size": gap,
                    "ce": (curr.open + prev.close) / 2,  # 50% level
                    "index": i,
                    "fill_status": "UNFILLED"
                }
                
                # Look for internal OBs within the gap
                # (candles that trade within the gap range after it forms)
                internal_obs = find_obs_in_range(
                    candles[i:], prev.close, curr.open
                )
                vacuum["internal_obs"] = internal_obs
                vacuums.append(vacuum)
            
            elif gap < 0:
                # BEARISH VACUUM (gap down)
                vacuum = {
                    "type": "BEARISH_VACUUM",
                    "high": prev.close,
                    "low": curr.open,
                    "size": abs(gap),
                    "ce": (prev.close + curr.open) / 2,
                    "index": i,
                    "fill_status": "UNFILLED"
                }
                internal_obs = find_obs_in_range(
                    candles[i:], curr.open, prev.close
                )
                vacuum["internal_obs"] = internal_obs
                vacuums.append(vacuum)
    
    return vacuums


def check_vacuum_fill(vacuum, subsequent_candles):
    """Track whether a vacuum block has been partially or fully filled."""
    for candle in subsequent_candles:
        if vacuum["type"] == "BULLISH_VACUUM":
            if candle.low <= vacuum["low"]:
                return "FULLY_FILLED"  # 100% filled
            elif candle.low <= vacuum["ce"]:
                return "PARTIALLY_FILLED"  # Past 50%
        
        elif vacuum["type"] == "BEARISH_VACUUM":
            if candle.high >= vacuum["high"]:
                return "FULLY_FILLED"
            elif candle.high >= vacuum["ce"]:
                return "PARTIALLY_FILLED"
    
    return "UNFILLED"
```

---

## Master Block Scanner

```python
def scan_all_blocks(candles, swing_points=None, atr=None, mmxm=None):
    """
    Run all 7 block type detectors on a candle series.
    Returns a unified list of all detected blocks, sorted by timestamp.
    """
    if swing_points is None:
        swing_points = identify_swing_points(candles)
    if atr is None:
        atr = calculate_atr(candles)
    
    all_blocks = []
    
    # 1. Order Blocks
    obs = detect_order_blocks(candles, atr)
    all_blocks.extend(obs)
    
    # 2. Mitigation Blocks
    mitigations = detect_mitigation_blocks(candles, swing_points)
    all_blocks.extend(mitigations)
    
    # 3. Breaker Blocks
    breakers = detect_breaker_blocks(candles, swing_points)
    all_blocks.extend(breakers)
    
    # 4. Rejection Blocks
    rejections = detect_rejection_blocks(candles)
    all_blocks.extend(rejections)
    
    # 5. Reclaimed Order Blocks (requires MMXM context)
    if mmxm:
        reclaimed = detect_reclaimed_order_blocks(candles, mmxm, obs)
        all_blocks.extend(reclaimed)
    
    # 6. Propulsion Blocks
    propulsions = detect_propulsion_blocks(candles, obs, atr)
    all_blocks.extend(propulsions)
    
    # 7. Vacuum Blocks
    vacuums = detect_vacuum_blocks(candles)
    all_blocks.extend(vacuums)
    
    # Sort by candle index (chronological)
    all_blocks.sort(key=lambda b: b.get("index", 0))
    
    return all_blocks
```

## Block Hierarchy (Priority for Trading)

When multiple blocks overlap or are nearby, use this priority:

| Priority | Block Type | Why |
|----------|-----------|-----|
| 1 | **Breaker + FVG overlap** (Unicorn) | Highest probability — 3 confluences |
| 2 | **BSG (Break Structure Gap)** | FVG at structure break — trend's lifeblood |
| 3 | **Breaker Block** | Failed OB = strong polarity flip |
| 4 | **Order Block + FVG** | OB confirmed by FVG displacement |
| 5 | **Rejection Block** | Double-wick rejection = strong |
| 6 | **Mitigation Block** | Trapped traders exiting |
| 7 | **Propulsion Block** | Secondary / cascading OB |
| 8 | **Order Block alone** | Weakest on its own |
| 9 | **Vacuum Block** | Context-dependent (event-driven) |
