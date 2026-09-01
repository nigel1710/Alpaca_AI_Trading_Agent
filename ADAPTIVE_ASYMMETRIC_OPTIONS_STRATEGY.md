# Options Alpha Agent — Adaptive Asymmetric Options Strategy

## Strategic Design Recommendation

**Status:** Proposed strategy update  
**Purpose:** Replace the current single-strategy approach with a regime-adaptive, explainable options decision system designed to deliver defined risk and stronger reward potential.

---

## 1. Executive Summary

After reviewing the current **Medium-Risk, High-Reward Strategy Proposal** and the **Development Log**, the recommended direction is **not** to replace credit spreads completely with debit spreads.

Instead, the Options Alpha Agent should evolve into a:

> **Regime-Adaptive Hybrid Options Agent**

The agent should dynamically decide whether to:

- **Buy premium** using debit spreads
- **Sell premium** using credit spreads
- **Use a non-directional strategy** when appropriate
- **Stand aside** when no high-quality opportunity exists

This approach preserves the working parts of the existing system while adding the asymmetric reward profile needed for a stronger medium-risk, high-reward strategy.

---

# 2. The Core Problem With the Current Strategy

The current system primarily uses credit spreads:

- BULL_PUT
- BEAR_CALL
- IRON_CONDOR

Credit spreads generally have the following payoff profile:

- Higher probability of winning
- Small and capped reward
- Larger potential loss relative to reward

This creates a payoff shape of:

> **Many smaller wins with occasional larger losses**

While this can be a legitimate income strategy, it does not strongly match the objective of:

> **Medium Risk + High Reward**

Simply changing thresholds cannot solve this completely because the limitation comes from the payoff structure itself.

---

# 3. Why Debit Spreads Should Be Added

Debit spreads provide a more asymmetric payoff structure.

### Bull Call Debit Spread

Used when the market outlook is bullish.

- Buy a call closer to the money
- Sell a higher-strike call
- Pay a net debit

### Bear Put Debit Spread

Used when the market outlook is bearish.

- Buy a put closer to the money
- Sell a lower-strike put
- Pay a net debit

### Payoff Profile

For a debit spread:

- **Maximum loss:** Premium paid
- **Maximum reward:** Spread width minus premium paid
- **Risk:** Defined and capped
- **Reward:** Can be meaningfully larger than the risk

Example:

```text
Debit Paid:       $1.50
Spread Width:     $5.00

Maximum Loss:     $150
Maximum Reward:   $350

Reward/Risk:      2.33 : 1
```

This makes debit spreads a strong candidate for the high-reward component of the strategy.

---

# 4. Recommended Strategy Architecture

The agent should not ask:

> "Should I trade?"

It should first ask:

> "What type of trade best fits the current market regime?"

### Strategy Selection Matrix

| Market Condition | Recommended Action |
|---|---|
| Strong bullish trend + cheap volatility | **Bull Call Debit Spread** |
| Strong bearish trend + cheap volatility | **Bear Put Debit Spread** |
| Strong bullish trend + rich volatility | **Bull Put Credit Spread** |
| Strong bearish trend + rich volatility | **Bear Call Credit Spread** |
| Range-bound market + rich volatility | **Iron Condor** |
| Weak, conflicting, or low-quality conditions | **Stand Aside** |

This transforms the system from a single-strategy trading bot into a genuine **strategy-selection agent**.

---

# 5. Volatility Regime Detection

The strategy should distinguish between three volatility regimes:

```text
CHEAP
FAIR
RICH
```

A simple Version 1 implementation can use the existing relationship between:

- Implied Volatility
- Realized Volatility

Example starting framework:

```text
IV/RV < 0.90        → CHEAP

0.90 – 1.20         → FAIR

IV/RV > 1.20        → RICH
```

These values should initially be treated as calibration values rather than permanent market truths.

### Strategy Logic

```text
CHEAP Volatility + Strong Direction
        ↓
Debit Spread Candidate

RICH Volatility + Strong Direction
        ↓
Credit Spread Candidate

RICH Volatility + Range
        ↓
Iron Condor Candidate

FAIR Volatility
        ↓
Require stronger confirmation
```

---

# 6. Required Move vs Expected Move

A directional signal alone should not trigger a debit spread.

The agent must determine whether the underlying can realistically move enough for the trade to become profitable.

The system should compare:

```text
Required Move
        vs
Expected Move
```

### Example — Valid Trade

```text
Underlying Price:       $650

Debit Spread Breakeven: $654

Required Move:          +0.62%

Expected Move:          ±1.40%

Decision: PASS
```

### Example — Invalid Trade

```text
Required Move:          +2.10%

Expected Move:          ±1.00%

Decision: FAIL
```

This prevents attractive-looking reward/risk trades that require an unrealistic market move.

---

# 7. Reward/Risk Should Not Be the Only Filter

A high reward/risk ratio can sometimes indicate a very low probability of success.

Example:

```text
Risk:       $50
Reward:     $450
R:R:        9:1
```

This may look attractive mathematically but could require an extremely unlikely market move.

Therefore, trade quality should combine:

```text
Reward/Risk
+
Trend Strength
+
Directional Agreement
+
Required Move
+
Expected Move
+
Liquidity
+
Event Risk
+
Portfolio Risk
```

---

# 8. Recommended Debit Spread Profile

For the first implementation, the agent should prefer relatively realistic directional spreads.

### Long Option

Suggested target:

```text
Delta: 0.45 – 0.65
```

The long option should generally be near-the-money rather than extremely far out-of-the-money.

### Short Option

Suggested target:

```text
Delta: 0.20 – 0.40
```

### Reward/Risk

Minimum:

```text
Reward/Risk ≥ 1.5
```

Preferred:

```text
Reward/Risk ≥ 2.0
```

However, Version 1 should avoid making 2.0 an absolute requirement if doing so eliminates too many otherwise valid opportunities.

---

# 9. Expiration Selection

Debit spreads are affected by time decay.

For the first version, the system should avoid relying on very short-dated directional options.

Recommended starting range:

```text
21–45 DTE
```

Preferred range:

```text
30–35 DTE
```

This gives the directional thesis time to develop while maintaining a meaningful reward profile.

---

# 10. Strategy-Aware Checklist

The existing checklist approach should be preserved.

However, it should become **strategy-aware**.

## Market Checks

1. Trend clarity
2. Directional agreement
3. Volatility stability
4. Event risk

## Debit Spread Checks

5. Volatility is cheap or reasonably priced
6. Reward/Risk is acceptable
7. Required move is realistic
8. Long/short strike selection is appropriate
9. Liquidity is sufficient

## Portfolio Check

10. Position fits within portfolio risk limits

This is stronger than forcing all strategies through a checklist written specifically for credit spreads.

---

# 11. Confidence-Based Decisions

The system should not produce only:

```text
TRADE
STAND_ASIDE
```

Instead, introduce confidence levels.

Example:

```text
80–100  → HIGH CONVICTION TRADE

65–79   → WATCHLIST / CONDITIONAL

Below 65 → STAND ASIDE
```

Example output:

```text
Agent Score: 88/100

Confidence:
HIGH

Decision:
TRADE
```

This makes the agent's decision process more transparent and deliberate.

---

# 12. The “Why Not?” Intelligence Layer

Every rejected trade should explain why it was rejected.

Instead of:

```text
STAND ASIDE
```

The agent should provide:

```text
SPY

Bullish trend detected.

Candidate:
Bull Call Debit Spread

Decision:
STAND ASIDE

Why?

✓ Trend is strong
✓ Direction is confirmed
✓ Volatility is attractive
✗ Reward/Risk is only 1.18
✗ Required move exceeds expected move
✓ Liquidity is acceptable
```

This makes **rejection intelligence** visible.

The agent demonstrates that standing aside is an active decision rather than a failure to find a trade.

---

# 13. The Trade Decision Card

Every decision should produce a structured decision card.

Example:

```text
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TRADE DECISION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Underlying:
IWM

Market Regime:
Bullish / Cheap Volatility

Strategy:
BULL CALL DEBIT SPREAD

Expiry:
Oct 16

Long Leg:
220 Call

Short Leg:
225 Call

Debit:
$1.55

Maximum Risk:
$155

Maximum Reward:
$345

Reward/Risk:
2.23 : 1

Required Move:
+0.8%

Expected Move:
±2.4%

Agent Score:
88 / 100

Decision:
TRADE

WHY?

✓ Strong bullish trend
✓ Momentum confirms direction
✓ Options relatively inexpensive
✓ 2.23× reward/risk
✓ Required move is realistic
✓ Good liquidity
✓ No immediate event risk

WHY NOT CREDIT SPREAD?

Volatility is not sufficiently rich to justify
premium selling.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

This should become one of the central features of the dashboard.

---

# 14. Separate Entry Scanning From Position Monitoring

This is a critical operational requirement.

The current development process identified that position monitoring depends on scan cycles.

That means:

```text
Position Opens
      ↓
Market Moves Against Position
      ↓
Scanner Does Not Run
      ↓
Stop-Loss Is Not Checked
```

The revised architecture should therefore separate:

```text
ENTRY SCANNER
```

from:

```text
POSITION MONITOR
```

### Recommended Flow

```text
First:
Monitor Existing Positions

Then:
Search for New Opportunities
```

No new position should be prioritized over checking existing risk.

---

# 15. Strategy Design Must Match Infrastructure Reliability

Because automated scheduling has experienced reliability issues, Version 1 should avoid strategies requiring extremely rapid intraday reaction.

Therefore, the initial implementation should prefer:

```text
21–45 DTE directional trades
```

rather than:

```text
0DTE
1DTE
Ultra-short-term strategies
```

The strategy should match what the current infrastructure can reliably monitor.

---

# 16. Position Sizing

Do not introduce dynamic position sizing yet.

For the first implementation:

```text
Quantity = 1
```

The priority should be demonstrating:

```text
Correct Signal
+
Correct Strategy Selection
+
Correct Contract Selection
+
Correct Execution
+
Correct Monitoring
+
Correct Exit
```

Dynamic sizing can be added after the strategy logic and monitoring system are stable.

---

# 17. Recommended Decision Engine

The complete architecture should be:

```text
MARKET DATA
     ↓
REGIME DETECTOR
     ↓
Trend
Volatility
Momentum
Event Risk
     ↓
STRATEGY SELECTOR
     ↓

Cheap IV + Direction
        ↓
Debit Spread

Rich IV + Direction
        ↓
Credit Spread

Rich IV + Range
        ↓
Iron Condor

Weak / Conflicting Market
        ↓
Stand Aside

     ↓
CONTRACT SEARCH
     ↓
GENERATE MULTIPLE CANDIDATES
     ↓
TRADE SCORING
     ↓
Reward/Risk
+
Trend Strength
+
Required Move
+
Liquidity
+
Event Risk
+
Portfolio Risk
     ↓
RISK MANAGER
     ↓
TRADE / REJECT
     ↓
POSITION MONITOR
     ↓
EXIT / HOLD / CLOSE
```

---

# 18. What Should Be Preserved From the Existing System

The existing credit-spread infrastructure should not be discarded.

The system has already demonstrated that it can:

- Fetch real market data
- Evaluate liquidity
- Apply checklist scoring
- Produce genuine trade decisions
- Submit paper-trading orders
- Monitor option positions

Credit spreads should therefore become one component of a broader strategy-selection system.

The new philosophy should be:

> **Do not always sell premium.**
>
> **Do not always buy premium.**
>
> **Select the strategy that best matches the market regime.**

---

# 19. What Should Not Be Added Yet

To keep Version 1 focused, the following should remain out of scope:

- Machine learning prediction models
- Reinforcement learning
- Naked options
- Dynamic position sizing
- Butterflies
- Calendars
- Diagonals
- Complex adjustment strategies
- Advanced volatility-surface modeling

The intelligence of the agent should come from **better decision-making**, not unnecessary strategy complexity.

---

# 20. Final Strategy Definition

## Adaptive Asymmetric Options Strategy

### Objective

> Identify opportunities where downside is explicitly defined, upside meaningfully exceeds downside when appropriate, and the options structure is selected according to market regime and volatility conditions.

### Core Rules

```text
1. Detect the market regime.

2. Determine directional strength.

3. Determine the volatility regime.

4. Cheap volatility + strong direction:
   → Consider debit spreads.

5. Rich volatility + strong direction:
   → Consider credit spreads.

6. Rich volatility + range:
   → Consider iron condors.

7. Generate multiple contract candidates.

8. Score candidates using:
   - Reward/Risk
   - Trend strength
   - Directional agreement
   - Required move
   - Expected move
   - Liquidity
   - Event risk
   - Portfolio risk

9. Select the highest-quality candidate.

10. Trade only when the score exceeds
    the minimum conviction threshold.

11. Otherwise stand aside.

12. Explain WHY NOT for rejected trades.

13. Monitor existing positions before
    opening new positions.
```

---

# 21. Implementation Priorities

| Priority | Task | Importance |
|---|---|---|
| P0 | Reliable position monitoring and exit execution | Critical |
| P0 | Debit spread construction | Critical |
| P0 | Debit-specific checklist | Critical |
| P1 | Volatility regime strategy selector | Very High |
| P1 | Required move vs expected move calculation | Very High |
| P1 | Candidate spread ranking | Very High |
| P1 | “Why Not?” intelligence | Very High |
| P1 | Trade Decision Card | Very High |
| P2 | Persistent decision history | Medium |
| P2 | Dynamic position sizing | Later |
| P3 | Additional strategy structures | Later |

---

# 22. Final Recommendation

The debit-spread proposal is a strong starting point, but it should not be implemented unchanged.

The recommended final architecture is:

> **Credit Spreads + Debit Spreads + Market Regime Detection + Strategy Selection + Candidate Ranking + Explainable Rejection + Strict Risk Management**

The strongest feature of the Options Alpha Agent should not simply be its ability to find a trade.

Its intelligence should be demonstrated through its ability to say:

> **“I analyzed the market, compared available strategies, rejected inappropriate alternatives, selected the structure that best matched the current regime, and can clearly explain why.”**

That is the recommended strategy direction for the next phase of the Options Alpha Agent.
