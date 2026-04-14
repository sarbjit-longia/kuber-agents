# Premium and Discount

## Definition

Premium and Discount is a framework for determining whether price is "expensive" (premium) or "cheap" (discount) relative to a given range. It is the institutional equivalent of "buy low, sell high" — applied with mathematical precision using Fibonacci retracements.

## Core Principle

> "If trading is a business, candles are your product. Do you want to sell your product for a premium, or a discount?"

- **Buy in discount** (below fair value) within bullish impulses
- **Sell in premium** (above fair value) within bearish impulses

## How to Calculate

### Step 1: Identify the Impulse Leg
Find the most recent impulsive move (a move with displacement and FVGs):
- **Bullish impulse**: Measure from the swing low to the swing high
- **Bearish impulse**: Measure from the swing high to the swing low

### Step 2: Apply Fibonacci Retracement
Draw a Fibonacci retracement from the impulse low to the impulse high (or vice versa).

### Step 3: Read the Zones

| Fib Level | Zone | Meaning |
|-----------|------|---------|
| 0.0 | Bottom of range | Deepest discount |
| 0.236 | Deep discount | Strong buy zone |
| 0.382 | Discount | Good buy zone |
| 0.5 | **Equilibrium / Fair Value** | **Dividing line** |
| 0.618 | Premium | Good sell zone |
| 0.786 | Deep premium | Strong sell zone |
| 1.0 | Top of range | Highest premium |

### The 0.5 Level (Equilibrium)
- **Below 0.5** = Discount = Cheap = Look for LONGS in bullish context
- **Above 0.5** = Premium = Expensive = Look for SHORTS in bearish context
- The 0.5 level is also called **fair market value** or **equilibrium**

## Fibonacci Levels Used in ICT

| Level | Name | Usage |
|-------|------|-------|
| 0.236 | — | Shallow retracement |
| 0.382 | — | Common retracement level |
| 0.5 | Equilibrium | Fair market value dividing line |
| 0.618 | Golden ratio | Key reversal level |
| 0.705 | Optimal Trade Entry (OTE) | Primary entry zone |
| 0.786 | — | Deep retracement |
| 0.886 | — | Deepest valid retracement |

## Optimal Trade Entry (OTE)

The **OTE zone** is the 0.618 - 0.786 Fibonacci retracement area. This is where the highest probability entries occur:
- In a bullish impulse: OTE is in the 61.8%-78.6% retracement (discount zone)
- In a bearish impulse: OTE is in the 61.8%-78.6% retracement (premium zone)

## Applying Premium/Discount to FVGs

The Premium/Discount concept also applies within individual FVGs:

| FVG Level | Name |
|-----------|------|
| 0 | FVG Open (nearest edge) |
| 0.5 | FVG Midpoint |
| 1 | FVG Fill (far edge) |

### FVG Reaction Rules
- If price enters an FVG and **fails to close beyond the midpoint (0.5)** → Valid FVG, expect continuation
- If price **closes beyond the midpoint** → Invalid FVG, reassess
- If price **closes completely through** → Inversion (iFVG)

## Premium/Discount of Individual Candle Ranges

For precision entries within Market Maker Models, apply the 0/0.5/1 framework to individual candle bodies:
- Buy at the discount (lower half) of a bullish candle
- Sell at the premium (upper half) of a bearish candle

## Agent Detection Logic

```
function calculate_premium_discount(impulse_high, impulse_low, current_price):
    range = impulse_high - impulse_low
    equilibrium = impulse_low + (range * 0.5)
    
    fib_level = (current_price - impulse_low) / range
    
    if fib_level < 0.5:
        zone = DISCOUNT
    elif fib_level > 0.5:
        zone = PREMIUM
    else:
        zone = EQUILIBRIUM
    
    ote_low = impulse_low + (range * 0.618)
    ote_high = impulse_low + (range * 0.786)
    in_ote = ote_low <= current_price <= ote_high
    
    return {
        "zone": zone,
        "fib_level": fib_level,
        "equilibrium": equilibrium,
        "in_ote": in_ote,
        "ote_range": (ote_low, ote_high)
    }
```
