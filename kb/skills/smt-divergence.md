# SMT Divergence (Smart Money Tool)

## Definition

SMT (Smart Money Tool) Divergence identifies manipulation occurring across **correlated assets**. When two markets that normally move together diverge at key swing points — one making a new extreme while the other fails to — it signals institutional sponsorship for a reversal. SMT is one of the most powerful confirmation tools in ICT methodology.

## How It Works

### Bullish SMT Divergence
- **Asset A** makes a new **lower low**
- **Asset B** (correlated) **fails** to make a new lower low (holds its previous low or makes a higher low)
- → The market is tipping its hand: smart money is buying. Expect bullish reversal.
- **Entry**: Take the long on the asset that held (Asset B), which provides the better entry

### Bearish SMT Divergence
- **Asset A** makes a new **higher high**
- **Asset B** (correlated) **fails** to make a new higher high (holds its previous high or makes a lower high)
- → Smart money is selling. Expect bearish reversal.
- **Entry**: Take the short on the asset that held (Asset B)

## Correlated Asset Pairs

### Index Futures
| Asset A | Asset B | Correlation |
|---------|---------|-------------|
| NQ (Nasdaq) | ES (S&P 500) | Positive |
| NQ | YM (Dow) | Positive |
| ES | YM | Positive |
| NQ/ES/YM | DXY (Dollar) | Inverse |

### Forex
| Asset A | Asset B | Correlation |
|---------|---------|-------------|
| EURUSD | DXY | **Inverse** — compare DXY highs to EURUSD lows, and vice versa |
| GBPUSD | DXY | Inverse |
| EURUSD | GBPUSD | Positive |

### Crypto
| Asset A | Asset B | Correlation |
|---------|---------|-------------|
| BTC | ETH | Positive |

### Inverse Correlation Note
For inversely correlated pairs (e.g., EURUSD vs DXY):
- Look at **DXY highs** while looking at **EURUSD lows** (and vice versa)
- If DXY makes a higher high but EURUSD does NOT make a lower low → Bullish EURUSD

## When SMT Is Most Significant

SMT divergence is most powerful when it occurs:

| Condition | Why |
|-----------|-----|
| At **time-based liquidity** highs/lows | Session highs/lows, daily highs/lows are institutional reference points |
| During **killzone** windows | 01:30-04:30 EST or 07:30-10:30 EST |
| At **HTF key levels** | FVGs, order blocks, breaker blocks on higher timeframes |
| Within a **Market Maker Model** | Confirms phase completion (accumulation → manipulation transition) |
| **Where and when** matters more than the divergence itself | Context determines significance |

## SMT + MMXM Combined Framework

The most powerful application of SMT is within Market Maker Models:

### Market Maker Buy Model (MMBM) with SMT
1. **Original Consolidation** — SMT may appear at the start
2. **Distribution / Downward Move** — SMT at the lows signals accumulation
3. **Smart Money Reversal** — SMT at the absolute low confirms the reversal
4. **Accumulation / Entry** — SMT confirms the long entry

### Market Maker Sell Model (MMSM) with SMT
1. **Original Consolidation** — SMT may appear at the start
2. **Accumulation / Upward Move** — SMT at the highs signals distribution
3. **Smart Money Reversal** — SMT at the absolute high confirms the reversal
4. **Distribution / Entry** — SMT confirms the short entry

### 3-Step High Probability Setup

**Step 1 — HTF Key Level**: Identify the higher timeframe narrative. Look for an MMXM on the HTF. Best case: find an FVG left behind after a market structure shift.

**Step 2 — SMT within the HTF Key Level**: On the LTF, check if SMT Divergence occurs within the HTF key level (e.g., within an HTF FVG). This confirms the phase completion.

**Step 3 — LTF Market Maker Model**: Look for a complete MMXM forming on the LTF within the HTF key level. When an MMXM forms within an MMXM (fractal), this is one of the highest probability models.

### Take Profit
1. **Option 1**: LTF MMXM original consolidation — quicker trade, smaller R:R
2. **Option 2**: HTF MMXM original consolidation — longer trade, larger R:R
3. **Recommended**: Take partials at Option 1, full close at Option 2

## Turtle Soup Connection

SMT provides the **Turtle Soup entry** — the correlated asset that fails to make a new extreme provides the entry, while traders watching only the other asset are still waiting for a liquidity raid that will never come.

## Agent Detection Logic

```
function detect_smt_divergence(candles_a, candles_b, correlation=POSITIVE):
    """
    Detect SMT divergence between two correlated instruments.
    candles_a and candles_b should be time-aligned.
    """
    divergences = []
    
    swings_a = identify_swing_points(candles_a)
    swings_b = identify_swing_points(candles_b)
    
    # Align swing points by time proximity
    for swing_a in swings_a:
        closest_b = find_nearest_swing(swings_b, swing_a.timestamp, tolerance=timedelta(minutes=15))
        if not closest_b:
            continue
        
        if correlation == POSITIVE:
            # Bullish SMT: A makes lower low, B holds
            if (swing_a.type == LOW and closest_b.type == LOW
                and swing_a.price < swing_a.previous_low
                and closest_b.price >= closest_b.previous_low):
                divergences.append(BullishSMT(
                    asset_a_swing=swing_a,
                    asset_b_swing=closest_b,
                    timestamp=swing_a.timestamp
                ))
            
            # Bearish SMT: A makes higher high, B holds
            if (swing_a.type == HIGH and closest_b.type == HIGH
                and swing_a.price > swing_a.previous_high
                and closest_b.price <= closest_b.previous_high):
                divergences.append(BearishSMT(
                    asset_a_swing=swing_a,
                    asset_b_swing=closest_b,
                    timestamp=swing_a.timestamp
                ))
        
        elif correlation == INVERSE:
            # For inverse pairs (e.g., EURUSD vs DXY)
            # Bullish for Asset A: A makes lower low, B makes higher high (expected)
            # SMT = A makes lower low but B does NOT make higher high
            if (swing_a.type == LOW and closest_b.type == HIGH
                and swing_a.price < swing_a.previous_low
                and closest_b.price <= closest_b.previous_high):
                divergences.append(BullishSMT(
                    asset_a_swing=swing_a,
                    asset_b_swing=closest_b,
                    timestamp=swing_a.timestamp
                ))
    
    return divergences
```
