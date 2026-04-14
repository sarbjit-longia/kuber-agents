# Market Maker Model (MMXM)

## Definition

The Market Maker Model (MMXM) is a framework for visualizing the complete cycle of institutional price delivery — from accumulation through manipulation to distribution. It describes how market makers engineer liquidity, reverse price, and deliver it to the opposing target. MMXM is the unifying strategy that ties together all ICT concepts.

## Two Models

### Market Maker Buy Model (MMBM)
Price is being delivered **upward** (bullish). The overall structure moves from a sell-side low to a buy-side high.

**Phases**:
1. **Original Consolidation** — Price ranges at a premium level. Smart money begins distributing short positions to retail buyers.
2. **Sell-Side Delivery (Distribution)** — Price drops aggressively. Retail traders go short. Smart money is accumulating at lower prices.
3. **Smart Money Reversal** — The absolute low. Liquidity is swept (sell-side liquidity taken). Price reverses.
4. **Buy-Side Delivery (Accumulation → Distribution)** — Price expands upward toward the original consolidation and beyond. This is where entries happen.

**Target**: The original consolidation level (or the buy-side liquidity above it).

### Market Maker Sell Model (MMSM)
Price is being delivered **downward** (bearish). The overall structure moves from a buy-side high to a sell-side low.

**Phases**:
1. **Original Consolidation** — Price ranges at a discount level. Smart money begins accumulating long positions from retail sellers.
2. **Buy-Side Delivery (Accumulation)** — Price rallies. Retail traders go long. Smart money is distributing at higher prices.
3. **Smart Money Reversal** — The absolute high. Buy-side liquidity is swept. Price reverses.
4. **Sell-Side Delivery (Distribution)** — Price drops toward the original consolidation and beyond. Entries happen here.

**Target**: The original consolidation level (or the sell-side liquidity below it).

## Buy-Side vs Sell-Side of the Curve

| Phase | Description | What's Happening |
|-------|-------------|-----------------|
| **Buy-Side of Curve** | Price moving upward toward a Point of Interest (POI) | Institutions selling into strength, building short inventory |
| **Sell-Side of Curve** | Price moving downward toward a level | Institutions buying into weakness, building long inventory |
| **Smart Money Reversal** | The swing point where price changes direction | The transition point — sweep of liquidity triggers the reversal |

## How to Identify MMXM on a Chart

### Step 1: Identify Three Consolidations
A classic MMXM shows three consolidation zones as price moves into a key level:
1. First consolidation (furthest from reversal)
2. Second consolidation
3. Third consolidation (closest to the reversal point)

### Step 2: Mark the Smart Money Reversal
The extreme swing point where:
- Liquidity is swept (high/low taken)
- An MSS or engulfing pattern occurs
- Displacement begins in the reversal direction

### Step 3: Project the Target
When the market reverses, target the **first consolidation** (the original consolidation) to be taken out.

## MMXM Entry Signals

### Signal 1: Sweep + Engulfing
The first entry within an MMXM:
- Liquidity is swept at the extreme
- An engulfing candle forms in the opposite direction
- Enter on the engulfing candle or wait for retracement

### Signal 2: Key Level to Key Level
Price moves from one PD array to another:
- Opposing liquidity is swept
- Price moves through an engulfing pattern
- Passes through a previous low/high that was taken
- Targets an FVG or the next PD array

### Signal 3: Premium/Discount of Candle Range
Apply 0/0.5/1 Fibonacci levels to individual candle bodies for precision:
- Buy at the discount (lower half) of a bullish candle in a MMBM
- Sell at the premium (upper half) of a bearish candle in a MMSM

## MMXM with SMT Divergence (Highest Probability)

### 3-Step Setup

**Step 1 — HTF Key Level**: Identify the HTF narrative. Look for an MMXM forming on the HTF. Best case: find an FVG left behind after a market structure shift.

**Step 2 — SMT within HTF Key Level**: On the LTF, check for SMT Divergence at the smart money reversal point within the HTF key level. This confirms the phase completion.

**Step 3 — LTF MMXM**: Look for a complete MMXM forming on the LTF within the HTF key level. An MMXM within an MMXM (fractal nesting) is the highest probability setup.

### Take Profit
- **Option 1**: LTF MMXM original consolidation (smaller, quicker trade)
- **Option 2**: HTF MMXM original consolidation (larger, longer trade)
- **Recommended**: Partial at Option 1, full close at Option 2

## IRL/ERL Within MMXM

| Concept | MMXM Context |
|---------|-------------|
| **IRL (FVGs)** | Found within the delivery phases; price trades through these |
| **ERL (Highs/Lows)** | The targets at each phase boundary |
| **Smart Money Reversal** | Always occurs at ERL (liquidity sweep) |
| **Entry** | Often at IRL (FVG retracement) after the reversal |

Price flow: **ERL → IRL → ERL** (sweep liquidity → retrace to FVG → expand to next liquidity)

## Reclaimed Order Blocks Within MMXM

Within the MMXM structure, order blocks from one side of the curve get "reclaimed" on the other side:
- **Bullish Reclaimed OB**: OBs from the sell-side of curve that become support on the buy-side
- **Bearish Reclaimed OB**: OBs from the buy-side of curve that become resistance on the sell-side

## Agent Detection Logic

```
function detect_market_maker_model(candles, htf_key_levels=None):
    swings = identify_swing_points(candles)
    
    # Look for the classic pattern: 3 consolidations moving into a key level
    consolidations = detect_consolidation_zones(candles)
    
    if len(consolidations) >= 3:
        # Check if consolidations are progressively moving in one direction
        if is_ascending(consolidations):
            # Potential MMSM: price being delivered upward before reversal
            reversal_point = find_highest_point(candles, after=consolidations[-1])
            if reversal_point and is_liquidity_sweep(reversal_point, htf_key_levels):
                return MMSM(
                    original_consolidation=consolidations[0],
                    reversal=reversal_point,
                    target=consolidations[0].low,
                    current_phase=determine_current_phase(candles, reversal_point)
                )
        
        elif is_descending(consolidations):
            # Potential MMBM: price being delivered downward before reversal
            reversal_point = find_lowest_point(candles, after=consolidations[-1])
            if reversal_point and is_liquidity_sweep(reversal_point, htf_key_levels):
                return MMBM(
                    original_consolidation=consolidations[0],
                    reversal=reversal_point,
                    target=consolidations[0].high,
                    current_phase=determine_current_phase(candles, reversal_point)
                )
    
    return None

function detect_consolidation_zones(candles, min_candles=5, max_range_atr=0.5):
    """Identify zones where price consolidates (ranges)."""
    zones = []
    atr = calculate_atr(candles)
    
    for i in range(len(candles) - min_candles):
        window = candles[i:i+min_candles]
        high = max(c.high for c in window)
        low = min(c.low for c in window)
        
        if (high - low) < atr * max_range_atr:
            zones.append(ConsolidationZone(
                high=high, low=low,
                start=i, end=i+min_candles
            ))
    
    return merge_overlapping(zones)
```
