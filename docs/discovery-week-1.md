# Discovery Week 1 — Find 5 Specific Humans

Created 2026-04-27 from `/office-hours` Assignment. Fill this in by Friday.

The point: name 5 actual humans, not categories. If you can't fill 5 slots by Friday, that's the finding — your retail channel is unsolved and the right move is to consider the B2B pivot earlier.

---

## Where to look (channels in priority order)

1. **Your own past life.** Ex-coworkers at tech companies who trade. Friends from college who got into options. The neighbor who's mentioned trading. Start where the bar is lowest.
2. **r/algotrading** (Reddit). Active subreddit, retail algo traders are vocal. Look at recent post authors who described frustrations with their setup.
3. **r/options** (Reddit). Larger, less algo-focused, but options traders are your archetype.
4. **Twitter/X algo-trading community.** Search `from:user "Pine Script" frustrated`, `"my bot blew up"`, `"I want to automate"`. Recent tweets, real frustration.
5. **Public trading Discords.** TradingView Discord, QuantConnect community, FTMO Discord, MyForexFunds-alumni Discords. Look for active members complaining about their workflow.
6. **GitHub.** Search for repos like `personal-trading-bot`, `pine-script-strategy`, `tradingview-webhook`. Authors are by definition technical retail traders building automation. They're your archetype.

## The candidates table

Fill in 5 slots. "Other" tab in your head if you find more — list 8-10 and pick the 5 most likely to actually respond.

| # | Name / Handle | Where you found them | What you know about them | Why they might want this | Contact method | Outreach status |
|---|---------------|----------------------|--------------------------|--------------------------|----------------|-----------------|
| 1 |  |  |  |  |  | not yet |
| 2 |  |  |  |  |  | not yet |
| 3 |  |  |  |  |  | not yet |
| 4 |  |  |  |  |  | not yet |
| 5 |  |  |  |  |  | not yet |

**"What you know about them"** examples:
- "Posted on r/algotrading 3 days ago complaining that their TradingView webhook keeps timing out during NFP releases"
- "GitHub user with 2 Pine Script repos and a half-built Python trading bot, last commit 2 weeks ago"
- "Twitter handle, ~800 followers, regularly posts options PnL screenshots, mentioned wanting to automate but doesn't code Python"
- "Ex-coworker from Acme Corp, side-trades futures evenings, complained about juggling 4 tools at last team dinner"

**"Why they might want this"** examples:
- "Their stack is brittle and they've said so publicly"
- "They're code-fluent but tired of maintaining their own bot"
- "They want AI/agent reasoning visible, not autonomous black-box trading"

If "what you know about them" is empty for any slot, you don't know that person well enough yet. Replace them or research more.

## Outreach template (cold)

Subject (email) or first DM line: short and specific to them, not generic.

```
Hi [name],

Saw your [post / commit / tweet] about [specific frustration they expressed].
I'm building a tool that lets you describe trading strategies in plain English
and watch multiple AI agents reason about each trade — the agents debate, you
see why every decision was made, and you can audit everything. Paper trading
on OANDA forex while we test.

Looking for 5 people to give me 20 minutes of feedback before I open it up.
You'd see a 90-second demo and try one strategy yourself. No commitment.

Worth a quick call?

— [your name]
```

**Variants by channel:**
- **Reddit DM:** Drop the subject line, lead with "Saw your post about [X]..."
- **Twitter DM:** Compress to 280 chars. "Saw your tweet about [X]. Building a tool that does [Y] — want a 90-sec demo?"
- **GitHub:** Use their commit-author email if public, or open an issue on their repo if appropriate (only if very relevant; this can feel intrusive)
- **Ex-coworker / friend:** Drop the formality. "Hey, you mentioned trading evenings — building something I want your eyes on. 20 min?"

## What you're listening for in the 20-minute call

You're not pitching. You're learning. The Codex challenge said the deeper pain is *"I cannot safely change live strategy logic without breaking execution"* — the right interview question is:

> *"Walk me through the last time you wanted to change your live trading strategy and didn't. What stopped you?"*

Other questions:
- What does your current setup look like? (List all the tools.)
- What broke last? How did you find out?
- What would you pay for to make this go away?
- If a tool let you describe your strategy in plain English and the AI handled the rest, what would worry you about trusting it?

**Take notes verbatim.** Their words become your marketing copy and your deposit-page copy. Don't paraphrase.

## Tracking deposit conversion (Phase 2)

After the demo + interview, follow up within 24 hours: *"Thanks for the time. I'm offering 5 design-partner slots at $99 (non-refundable, fully credited toward your first 3 months when we launch). Want one?"*

Track:

| # | Name | Demo date | Outcome | Notes |
|---|------|-----------|---------|-------|
| 1 |  |  |  |  |

**Outcomes to track:** `deposited` / `said-yes-but-didn't-pay` / `wants-follow-up` / `polite-no` / `ghosted`

The first three lump as "interest"; only `deposited` counts as demand.

## Decision rules

- **By Friday, fewer than 5 names filled in:** retail channel is unsolved. Evaluate B2B pivot now, not after Phase 1 build.
- **By end of week 4, fewer than 10 conversations booked:** outreach quality bar is too low or the channels don't have enough density. Time to think about whether the audience exists.
- **By end of week 6, fewer than 2 deposits:** pivot to B2B (prop firms, RIAs, family offices). Same product, different buyer.
- **3+ deposits by week 6:** retail signal confirmed. Phase 3 build with conviction.
