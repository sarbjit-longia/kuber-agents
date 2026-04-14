# Trading Knowledge Base

A structured collection of trading concepts, skills, strategies, and patterns designed to be consumed by AI trading agents. Each file contains precise, actionable definitions with quantitative rules that agents can use for trade analysis, entry/exit decisions, and risk management.

## Structure

```
kb/
├── concepts/               Core market concepts (foundational knowledge)
│   ├── market-structure.md
│   ├── liquidity.md
│   ├── fair-value-gap.md
│   ├── block-types.md
│   ├── premium-discount.md
│   ├── displacement-manipulation.md
│   ├── time-and-price.md
│   └── power-of-three.md
├── skills/                 Individual trading skills and techniques
│   ├── fair-value-gap.md
│   ├── inverse-fair-value-gap.md
│   ├── order-blocks.md
│   ├── breaker-blocks.md
│   ├── manipulation-blocks.md
│   ├── smt-divergence.md
│   ├── market-structure-shift.md
│   ├── killzones.md
│   ├── daily-bias.md
│   └── timeframe-alignment.md
├── strategies/             Complete trading strategies with entry/exit rules
│   ├── market-maker-model.md
│   ├── 3-step-liquidity-system.md
│   ├── 6-figure-ict-strategy.md
│   ├── silver-bullet.md
│   ├── range-expansion.md
│   ├── smm-entry-model.md
│   ├── ifvg-trading-model.md
│   ├── manipulation-block-strategy.md
│   └── unicorn-model.md
├── patterns/               Chart pattern recognition
│   ├── harmonic/           Harmonic patterns (Gartley, Butterfly, etc.)
│   ├── classic/            Classic chart patterns (Triangle, Rectangle, etc.)
│   └── candlestick/        Candlestick patterns (Hammer, Engulfing, etc.)
└── images/                 Reference diagrams and charts
    ├── cheatsheets/
    ├── concepts/
    ├── patterns/
    ├── skills/
    └── strategies/
```

## How Agents Should Use This Knowledge Base

### Dependency Order
1. **Read concepts/ first** — these are prerequisites for everything else
2. **Read skills/** — individual techniques that compose into strategies
3. **Read strategies/** — complete trading systems built from concepts + skills
4. **Read patterns/** — supplementary pattern recognition

### Key Principles
- **Bias before entry**: Always determine HTF directional bias before looking for entries
- **Liquidity is the target**: Price moves from internal liquidity (FVGs) to external liquidity (swing highs/lows)
- **Displacement confirms**: Valid moves show displacement (aggressive candles closing through levels)
- **Time matters**: Only look for entries during killzone windows (London 01:30-04:30 EST, NY 07:30-10:30 EST)
- **Minimum 2R**: Never take a trade with less than 2:1 reward-to-risk ratio

### For Agent Implementation
Each file contains:
- **Definition**: Precise, unambiguous definition of the concept
- **Identification Rules**: Quantitative criteria for detecting the pattern/setup
- **Entry/Exit Rules**: Specific conditions for trade execution (where applicable)
- **Risk Management**: Stop loss placement and position sizing rules
- **Agent Detection Logic**: Pseudocode or algorithmic steps for automated detection
