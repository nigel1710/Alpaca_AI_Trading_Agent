# Medium-Risk, High-Reward Strategy Proposal

Draft for team review. No code has been changed — this is a design document only.

---

## 1. Why the current strategy doesn't fit "medium risk, high reward"

The agent currently only sells **credit spreads** (BULL_PUT, BEAR_CALL, IRON_CONDOR). Structurally, credit spreads are:

- **Max reward per trade** = credit collected (small, fixed, capped)
- **Max loss per trade** = spread width − credit (can be several multiples of the reward)
- **Win rate** = typically high (short strikes chosen at low delta, ~70-80%+ theoretical win rate)
- **Shape**: many small wins, occasional larger loss

This is a legitimate, common income-generation strategy, but it is the *opposite* shape of "high reward." No amount of threshold tuning changes that — the payoff structure itself is capped-reward/uncapped(-ish)-risk. To get a genuinely higher-reward-per-trade profile, the strategy type itself has to change.

---

## 2. Proposed strategy: Debit spreads

**Debit spreads** (buy a call spread when bullish, buy a put spread when bearish) invert the shape:

- **Max loss per trade** = premium paid (small, fixed, capped, known in advance) → this is the "medium risk" part — risk is defined and limited, not unlimited like a naked long option
- **Max reward per trade** = spread width − premium paid (can be several multiples of the premium risked) → this is the "high reward" part
- **Win rate** = lower than credit spreads (you need the underlying to actually move in your favor before expiry, not just avoid moving against you)
- **Shape**: fewer wins, but each win is worth meaningfully more than what was risked

This is the natural "medium risk, high reward" candidate — better fit than naked long options (which would be *high* risk, since a single bad move can lose the whole premium with no spread cushion, and sizing math gets harder) and clearly more reward-oriented than credit spreads.

### Mechanics
- **BULL_CALL_DEBIT** (replaces/supplements BULL_PUT on an UP trend): buy a near-the-money call, sell a further OTM call. Net **debit** paid.
- **BEAR_PUT_DEBIT** (replaces/supplements BEAR_CALL on a DOWN trend): buy a near-the-money put, sell a further OTM put. Net **debit** paid.
- No natural debit equivalent for RANGE/IRON_CONDOR (debit spreads are directional by nature) — RANGE would likely stay STAND_ASIDE, or a separate non-directional strategy would need its own design.

---

## 3. The key open design question: which volatility condition should trigger entry?

This is the one decision I think the team needs to make deliberately, because getting it backwards produces a strategy that looks fine on paper but enters at bad prices.

- **Credit spreads want ELEVATED IV** (sell rich premium) — this is what `IV_RICH_MULTIPLIER` currently gates on.
- **Debit spreads want the opposite** — you're *buying* premium, so you want it *cheap* relative to how much the underlying actually moves (i.e., realized vol not already priced in). Buying debit spreads when IV is elevated means overpaying for the options, eating into the very reward edge that makes debit spreads attractive.

**My recommendation:** gate debit-spread entry on **DEPRESSED** volatility (the condition that currently just triggers `STAND_ASIDE` and does nothing). This would mean the two strategies become complementary instead of competing:
- ELEVATED vol + directional trend → credit spread (sell rich premium)
- DEPRESSED vol + directional trend → debit spread (buy cheap premium)
- No more STAND_ASIDE on directional-but-depressed days — that regime becomes the debit-spread opportunity instead

This is the specific point I flagged before you asked for this doc — happy to hear your team's reasoning if you see it differently (e.g., maybe you want debit spreads on ELEVATED-but-not-rich-enough-for-credit days instead, or some IV percentile-based approach rather than reusing the existing REALIZED_VOL ratio signal at all).

---

## 4. Checklist implications (agent/evaluation/checklist.py)

Several of the 9 checks are written in credit-spread language and would need adaptation or a parallel debit-spread version:

| Check | Credit-spread version (current) | Debit-spread equivalent (proposed) |
|---|---|---|
| 1. Premium rich | IV/RVol ≥ threshold (want rich) | IV/RVol ≤ threshold (want cheap) — inverted |
| 5. Credit quality | credit ≥ 30% of spread width | Something like "reward ≥ N× premium paid" (e.g., spread width − premium ≥ 2× premium, so max reward is at least 2x max risk) |
| 6. Probability profile | short strike delta ≤ ceiling (win-prob proxy) | long strike delta in a target range (how far ITM/ATM the bought leg is — affects both cost and win probability) |
| 7. Liquidity (hard gate) | bid-ask spread ≤ 10% of *credit* | bid-ask spread ≤ 10% of *premium paid* (same idea, different denominator) |

Checks 2 (volatility stable), 3 (trend clarity), 4 (directional agreement), 8 (event clear), 9 (portfolio fit) likely transfer over mostly as-is.

---

## 5. Risk sizing note

Max loss on a debit spread is capped at the premium paid — this is naturally smaller and more predictable than credit-spread max loss (which is spread width minus a thin credit, i.e., close to the full width). `MAX_LOSS_PCT` (2% of equity) would likely bind less often for debit spreads at the same size, meaning position sizing (`qty`, currently hardcoded to 1) could reasonably be revisited once this is live — but that's a separate decision, not needed to ship a first version.

---

## 6. What I have NOT decided (deliberately, for your team)

- Whether debit spreads **replace** the credit-spread strategies entirely, or **run alongside** them (e.g., credit spread on ELEVATED days, debit spread on DEPRESSED days, as in the recommendation above)
- The exact reward-to-risk floor for the debit-spread "Credit quality" equivalent (I used 2× as an illustrative number, not a firm recommendation)
- Whether IRON_CONDOR (RANGE trend) gets a debit-spread equivalent at all, or just stays out of scope for this change
- Position sizing changes

Once you've reviewed this and have a direction, let me know and I'll implement it.
