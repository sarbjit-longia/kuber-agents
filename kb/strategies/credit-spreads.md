# Credit Spread Strategy

## Definition

A credit spread involves selling a closer-to-the-money option and buying a further-out-of-the-money option for protection, collecting a net premium (credit). This strategy profits from time decay (theta) and is designed for high-probability, defined-risk trading.

## Types

### Bull Put Spread (Bullish)
- **Sell** an OTM put (higher strike)
- **Buy** a further OTM put (lower strike) for protection
- Profit if price stays above the sold put's strike at expiration

### Bear Call Spread (Bearish)
- **Sell** an OTM call (lower strike)
- **Buy** a further OTM call (higher strike) for protection
- Profit if price stays below the sold call's strike at expiration

## SPY Credit Spread Rules (Intraday / Short-Duration)

### Ground Rules

| Rule | Detail |
|------|--------|
| **Avoid Monday expiration** | Weekend risk (news, geopolitical events) can destroy positions |
| **Best expirations** | Wednesday and Friday |
| **Selling strike** | 4-5 strikes OTM |
| **Protection strike** | 6-7 strikes OTM |
| **Sweet spot premium** | $0.05 - $0.06 |
| **Max drawdown cutoff** | 20% |
| **Profit target** | ~10% of collateral |
| **Do not chase fills** | If limit at $0.05, don't change to $0.04 |

### Observed Results
- Never lost on a credit spread filled at $0.05
- 75% win / 25% loss overall
- Account grew 100%+ in 16 trading days

### Risks
- **NEWS, PRESIDENTIAL TWEETS, OR GEOPOLITICAL EVENTS** can kill your spread if on the wrong side
- Overnight risk is real — avoid Monday expirations for this reason
- Same-day expiration requires extra care — take profits when up

## TastyTrade Options Commandments

### Entry Rules
1. **Sell premium when IV Rank > 50%** — this is the primary trade selector
2. **Theta >= 0.1% per day** — minimum compensation for risk. High IV = 0.5-1% theta/day
3. **Trade only liquid products** — minimum 2M shares/day volume, bid/ask spread ideally 1 cent
4. **Risk 1-2% buying power per trade** — ideal is 0.25-0.5% of portfolio
5. **Keep at least 50% portfolio in cash**

### Exit Rules
| Condition | Action |
|-----------|--------|
| **Winners** | Close at 50% of maximum profit |
| **Losers (undefined risk)** | Roll down and out to extend duration |
| **Losers (defined risk)** | Accept the loss |
| **Time-based** | Close at 2x original credit received (e.g., $1 credit → close at $3 value) |

### Position Management
- **Manage winners, not losers** — take profits mechanically
- **No stop orders** — prefer active/reactive management
- **Extend duration to be right** — roll strategies to give more time
- **Trade often** — more trades = better probability convergence
- **Portfolio probability 65-75%** target

### VIX Integration

| VIX Metric | Formula |
|------------|---------|
| 1-day expected move | VIX / 15.87 |
| 1-week expected move | VIX / 7.21 |
| 1-month expected move | VIX / 3.46 |

**Use VIX expected moves** to size credit spread width and strike selection:
- If VIX = 20 → 1-day expected move = 20/15.87 = 1.26%
- Sell strikes beyond the expected move for higher probability

### VIX-SPY Correlation
- Average correlation: -69.70% (inverse)
- For every $1 SPY moves, VIX inverses by ~$0.75
- VIX > 30 = elevated fear = wider spreads, more premium to collect

## Implied Volatility Rules

| IV Rank | Action |
|---------|--------|
| > 50% | Sell premium — best environment for credit spreads |
| 30-50% | Selective selling — moderate opportunity |
| < 30% | Avoid selling premium — not enough compensation for risk |

**IV Crush Warning**: Stock can move in your favor but option value can still drop due to IV collapse. A $5 move up might cause a call to lose value if IV drops from 50% to 22%.

## Agent Detection Logic

```
function evaluate_credit_spread_opportunity(symbol, options_chain, vix):
    # Check IV Rank
    iv_rank = calculate_iv_rank(symbol)
    if iv_rank < 50:
        return NO_TRADE, f"IV Rank {iv_rank}% too low (need >50%)"
    
    # Check liquidity
    volume = get_daily_volume(symbol)
    if volume < 2_000_000:
        return NO_TRADE, "Insufficient volume"
    
    # Calculate expected move
    expected_1day = vix / 15.87 / 100  # As decimal
    current_price = get_current_price(symbol)
    
    # For bull put spread (bullish)
    sell_strike = current_price * (1 - expected_1day * 1.5)  # 1.5x expected move OTM
    buy_strike = sell_strike - (current_price * 0.01)  # $1-wide or percentage
    
    # Check theta
    spread_credit = get_spread_credit(options_chain, sell_strike, buy_strike, PUT)
    collateral = abs(sell_strike - buy_strike) * 100
    theta = calculate_theta(options_chain, sell_strike, buy_strike)
    theta_pct = theta / collateral
    
    if theta_pct < 0.001:  # 0.1% per day minimum
        return NO_TRADE, f"Theta {theta_pct:.4f}% too low"
    
    # Check premium sweet spot
    if spread_credit < 0.04 or spread_credit > 0.10:
        return NO_TRADE, f"Premium ${spread_credit} outside sweet spot"
    
    return TRADE_SIGNAL(
        strategy="BULL_PUT_SPREAD",
        sell_strike=sell_strike,
        buy_strike=buy_strike,
        credit=spread_credit,
        max_loss=collateral - spread_credit * 100,
        probability=calculate_prob_otm(sell_strike),
        exit_at_50pct=spread_credit * 0.5
    )
```
