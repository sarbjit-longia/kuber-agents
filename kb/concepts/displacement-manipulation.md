# Displacement vs Manipulation

## Definition

**Displacement** and **Manipulation** are the two ways price interacts with a significant level. Distinguishing between them is the single most important skill in ICT methodology — it determines whether a move is genuine (continuation) or deceptive (reversal).

## Displacement

### What It Is
A violent, aggressive candle (or set of candles) that pushes **and closes** through a significant price level. Displacement signals genuine institutional intent behind a move.

### Characteristics
- Large-bodied candles with small or no wicks on the expansion side
- Candle **closes strongly** through the level (not just wicks through)
- Creates Fair Value Gaps (FVGs) in its wake
- Price continues moving in the displacement direction after the initial push
- One-sided price delivery (all candles in the same direction)

### Rule
**Displacement = Continuation.** When you see displacement through a level, expect price to continue in that direction.

## Manipulation

### What It Is
A deceptive move that pushes through a significant level to trigger stop losses and trap traders, then reverses. This is how large market participants engineer liquidity to fill their orders.

### Characteristics
- Price pushes through a level but **fails to close** decisively beyond it (wicks only)
- OR price briefly closes beyond but immediately reverses
- No FVGs form in the move (or weak/quickly-filled FVGs)
- Two-sided price delivery (indecisive, mixed candle directions)
- The move is designed to trigger stop losses clustered beyond the level

### Rule
**Manipulation = Reversal.** When you see manipulation at a level (price takes liquidity but fails to displace), expect price to reverse.

## How to Distinguish Between Them

### Method 1: HTF Candle Analysis
Watch the candle that purges liquidity:
- If the candle **closes beyond** the liquidity level with a strong body → Displacement
- If the candle **wicks beyond** but closes back inside → Manipulation
- If the candle closes beyond but the **next candle reverses** aggressively → Manipulation

### Method 2: LTF Confirmation
After liquidity is purged, drop to a lower timeframe (e.g., from H1 to M5):
- If LTF shows continued one-sided delivery beyond the level → Displacement
- If LTF shows a market structure shift (MSS) back in the opposite direction → Manipulation
- The MSS on LTF with displacement **confirms** the manipulation and signals the real direction

### Method 3: FVG Formation
- **Displacement creates FVGs** — look for clean 3-candle gaps forming in the expansion
- **Manipulation does NOT create FVGs** — the move is messy, overlapping, or immediately filled

## Pairing with Other Concepts

| Scenario | Signal | Action |
|----------|--------|--------|
| Liquidity sweep + No displacement | Manipulation | Trade against the sweep |
| Liquidity sweep + Displacement | Genuine breakout | Trade with the breakout |
| FVG tap + Price fails at midpoint | Valid FVG (displacement away) | Trade continuation |
| FVG tap + Price closes through | Inversion (manipulation of prior FVG) | Trade new direction |
| MSS + Displacement | Valid trend change | Enter after confirmation |
| MSS + No displacement | False signal | Wait / no trade |

## Examples

### Bullish Manipulation (Buy Setup)
1. Price is in a bullish HTF context
2. Price sweeps below a swing low (takes sell-side liquidity)
3. The candle that sweeps the low fails to displace lower — it wicks below and closes back above
4. On LTF, price shows an MSS to the upside with displacement
5. → Enter long. The sweep was manipulation; the real move is up.

### Bearish Manipulation (Sell Setup)
1. Price is in a bearish HTF context
2. Price sweeps above a swing high (takes buy-side liquidity)
3. The candle fails to displace higher — wicks above, closes back below
4. On LTF, price shows an MSS to the downside with displacement
5. → Enter short. The sweep was manipulation; the real move is down.

## Agent Detection Logic

```
function classify_move(candles, liquidity_level, direction):
    """
    Classify whether a move through a liquidity level is 
    displacement (genuine) or manipulation (deceptive).
    """
    breach_candle = find_candle_breaching(candles, liquidity_level)
    
    if direction == BULLISH_BREACH:  # Price going above level
        body_close_beyond = breach_candle.close > liquidity_level
        strong_body = (breach_candle.close - breach_candle.open) / (breach_candle.high - breach_candle.low) > 0.6
        fvg_formed = detect_fvg(candles, around=breach_candle)
        next_candles_continue = all(c.close > liquidity_level for c in next_3_candles)
    
    if body_close_beyond and strong_body and fvg_formed and next_candles_continue:
        return DISPLACEMENT  # Genuine move
    else:
        return MANIPULATION  # Deceptive move — expect reversal

function has_displacement(candle):
    """Check if a single candle shows displacement characteristics."""
    body = abs(candle.close - candle.open)
    range = candle.high - candle.low
    body_ratio = body / range if range > 0 else 0
    return body_ratio > 0.6  # Body is >60% of total range
```
