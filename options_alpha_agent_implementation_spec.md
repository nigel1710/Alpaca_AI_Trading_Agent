# Options Alpha Agent — Implementation Spec for Claude Code

**Team:** The Overfitters
**Event:** Alpaca AI Trading Agents Hackathon (Aug 28 – Sep 4, 2026), Track: Options Alpha Agents
**Source doc:** Options Alpha Agent — Approach & Implementation Plan v2
**Purpose of this file:** Single-pass build spec. Implement exactly what's described here; do not invent alternate strategies or skip the decision-intelligence layer. If something is ambiguous, prefer the interpretation that keeps risk controls strict and reasoning fully inspectable.

---

## 1. What We're Building

An autonomous options trading agent that runs on **Alpaca's paper trading environment**, using Alpaca's **Trading API**, **official MCP server**, and **CLI** as the execution backbone. The agent:

1. Scans a watchlist of underlyings.
2. Reads two signals per underlying: an **implied volatility (IV) condition** and a **trend condition**.
3. Maps those two signals to a candidate **options structure** via a fixed selection matrix.
4. Grades the candidate against a **scored checklist** (opportunity evaluation), producing exactly one of three outcomes: **TRADE / WATCH / REJECT**.
5. If TRADE, passes the order through an independent **risk gate**, then executes via Alpaca's MCP tools.
6. Logs every decision — taken or declined — as a **decision card** with full reasoning.
7. Surfaces all of this on a **financial-terminal-style dashboard**: live decision pipeline, positions, P&L curve, and a chronological reasoning log.

The build must be sequenced so **real paper trades start as early as possible** (by Day 3). The dashboard and decision-intelligence presentation layers are built against live/real data after go-live — never against mocked data, and never simulated in the frontend.

---

## 2. Non-Negotiable Constraints (read before writing any code)

- **No mocked/simulated dashboard state.** Every stage shown on the dashboard must correspond to a real backend event with a timestamp and payload, written to the same log the agent uses for its own control flow. Never fabricate progress animations or fake data to make the demo look good.
- **Defined risk only.** Every strategy the agent can deploy (credit spreads, iron condors, debit spreads) has a capped maximum loss at entry. Never implement a naked/undefined-risk structure.
- **Risk Gate is independent and cannot be bypassed.** Even if a candidate scores 100/100, it must still pass position sizing, concurrency, and event-avoidance checks before an order is placed.
- **Explainability is not optional/decorative.** Every TRADE, WATCH, REJECT, and EXPIRED state must be reconstructable from stored, structured data — never free-form prose. Decision card text should be templated from underlying numeric/boolean fields, not hand-written per trade.
- **Do not build presentation before go-live.** Sequence work so the trading loop is live and placing real orders before dashboard polish begins (see Section 9, Timeline).
- **Paper trading only.** All order placement targets Alpaca's paper trading account. Never wire in live/production trading credentials.
- **Small sample size discipline.** Anywhere the dashboard shows a rate/percentage/win-rate derived from fewer than 5 observations, show the raw counts instead (or alongside), not just a rate. Never present a win rate computed from 2–3 trades as if it were a stable statistic.

---

## 3. Tech Stack & Integration Requirements

- **Execution backbone:** Alpaca Trading API, accessed via Alpaca's **official MCP server** (perception + action) and Alpaca **CLI** (setup/verification tasks, e.g., confirming options approval level and multi-leg order support).
- The agent's full perception → decision → action loop must be **agent-driven through Alpaca's MCP tools** — not manually triggered scripts calling a REST client directly wherever an MCP tool exists for that purpose. Market data retrieval, options-chain retrieval, account/position state, and order placement should all go through MCP tool calls.
- **Backend:** Your choice of language/framework, but structure it so every pipeline stage (Section 6) emits a discrete, loggable event. Recommend Python for the agent/strategy engine (consistent with the team's existing screener codebase) with a lightweight persistence layer (SQLite or similar — anything that lets the dashboard query structured history; avoid dumping everything into flat log files only).
- **Frontend/dashboard:** Financial-terminal aesthetic (dark theme, monospace/numeric emphasis, dense information layout — consistent with the team's prior React dashboard work). React is the default choice; poll or subscribe to the backend's event log/store for live updates. The dashboard must render **recorded backend state only** — it is a viewer, not a simulator.
- **Config-driven strategy parameters.** All numeric thresholds referenced in Sections 4–5 (moving average periods, IV percentile cutoffs, delta ceilings, credit-to-width fractions, position size caps, concurrency caps, score-band cutoffs, WATCH expiry windows) must live in a single config file/module, not hardcoded inline across multiple files. This lets thresholds be recalibrated after the Day 2 observation-only run without a code rewrite.

---

## 4. Strategy Design

### 4.1 Volatility Signal
For each underlying, compute how "rich" current at-the-money implied volatility is relative to the underlying's own recent realized volatility. Classify as:
- **Elevated** (premium is rich — favors premium-selling strategies)
- **Depressed** (premium is cheap — favors premium-buying strategies or standing aside)

### 4.2 Trend Signal
Use a short-vs-long moving average relationship on the underlying's price (same technique family as the team's existing NSE equity screener, adapted here for directional bias rather than a binary buy/sell signal). Classify as:
- **Clear uptrend**
- **Clear downtrend**
- **Range-bound** (no clear separation between short and long MAs beyond the configured threshold)

### 4.3 Strategy Selection Matrix

| Volatility Condition | Trend Condition | Structure Deployed |
|---|---|---|
| Elevated | Clear uptrend | Bull put credit spread |
| Elevated | Clear downtrend | Bear call credit spread |
| Elevated | Range-bound | Iron condor |
| Depressed | Any | No premium-selling trade; agent stands aside, or considers a small defined-risk directional debit spread only if trend conviction is high |

Matrix output is only a **candidate** — it does not authorize a trade by itself. It feeds into the Opportunity Evaluation framework (Section 5).

### 4.4 Risk Management Rules (hard constraints, enforced pre-order)
- **Position sizing:** max possible loss on any single trade capped at a small, fixed % of total paper account equity (configurable; pick a conservative default, e.g., 1–2%, and document it in the config).
- **Portfolio limits:** max number of concurrent open positions (configurable).
- **Event avoidance:** no new positions on underlyings with earnings or other major scheduled events before the option's expiry.
- **Exit discipline:** every position gets a pre-defined profit target, a pre-defined stop-loss (expressed as a multiple of premium collected), and a hard time-based exit as expiry approaches. Implement exit monitoring as part of the same loop that manages open positions — this needs to run continuously alongside new-opportunity scanning, not as an afterthought.

---

## 5. Decision Intelligence Layer

### 5.1 Opportunity Evaluation Framework
A pass/fail scored checklist — **not** a weighted/fitted model. Each check is worth a fixed number of points; the opportunity score is the sum of points from checks that passed. Every score must be displayed with its full breakdown (each check, its measured value, pass/fail).

| # | Check | Condition Tested | Points |
|---|---|---|---|
| 1 | Premium rich | Current ATM IV meaningfully above underlying's recent realized volatility | 15 |
| 2 | Volatility stable | IV is not expanding sharply into entry | 10 |
| 3 | Trend clarity | Short/long MAs separated by more than the defined threshold | 15 |
| 4 | Directional agreement | Selected structure's bias matches measured trend direction | 10 |
| 5 | Credit quality | Credit received ≥ defined fraction of spread width | 15 |
| 6 | Probability profile | Short-strike delta ≤ defined ceiling | 10 |
| 7 | Liquidity **(hard gate)** | Spread bid-ask within defined % of credit, AND open interest clears the floor | 10 |
| 8 | Event clear **(hard gate)** | No earnings/major scheduled event before expiry | 10 |
| 9 | Portfolio fit **(hard gate)** | Adding position keeps directional exposure and position count within limits | 5 |

**Hard gates:** Checks 7, 8, 9 are mandatory. Failing any one of them → REJECT outright, regardless of total score. Implement this as a short-circuit: evaluate hard gates first (or at minimum, evaluate them independently of the score sum so a high score can never override a failed gate).

**Score bands:**
- 80–100 → Strong opportunity → proceed to Risk Gate → TRADE if approved
- 60–79 → Moderate opportunity → WATCH, re-evaluate next cycle
- Below 60 → Weak opportunity → REJECT, with failing checks recorded

**Calibration step (Day 2, before any live order placement):** Run the scorer in **observation-only mode** for at least one full session against real chains. Inspect the distribution of produced scores. If genuine opportunities cluster below the execution band, or if nearly everything clears, adjust the thresholds in config before Day 3 go-live. Build a simple way to dump/inspect this score distribution (a CLI report or a log query is fine — doesn't need a UI).

### 5.2 The "Why Not?" Layer — TRADE / WATCH / REJECT / EXPIRED

Every evaluated opportunity resolves to exactly one state:

| State | Meaning | What gets recorded |
|---|---|---|
| TRADE | All hard gates cleared, score in execution band, risk gate approved | Full decision card, order details, entry reasoning |
| WATCH | Structurally sound but one or more conditions not yet strong enough | Failing checks, current score, the specific condition that would promote it to TRADE |
| REJECT | Fails a hard gate or scores below threshold | The specific rule/check that caused rejection |
| EXPIRED | A WATCH item whose promotion window elapsed without meeting its promotion condition | Reason for expiry, original watch reasoning |

**WATCH lifecycle:** WATCH is a tracked, stateful entity, not a log line. Each watched item needs:
- A timestamp of when it entered WATCH
- An expiry window (configurable)
- The specific promoting condition it's waiting on
- A state transition log (WATCH → TRADE, or WATCH → EXPIRED) that the dashboard can visualize as movement over a session

Implement WATCH items as persisted records that get re-evaluated on every subsequent scan cycle, not recomputed from scratch with no memory of prior state.

### 5.3 Visible Decision Pipeline (stages to emit as real backend events)
1. **Market Scan** — scanning the watchlist for available opportunities
2. **Market Analysis** — detecting volatility and trend conditions per underlying
3. **Strategy Selection** — applying the strategy matrix
4. **Opportunity Evaluation** — running the checklist, computing the score
5. **Risk Review** — validating position sizing, exposure, portfolio limits
6. **Final Decision** — TRADE, WATCH, or REJECT

Each stage = one real event with timestamp + payload, written to a persistent event log the dashboard reads from. Do not let the frontend advance a progress bar independently of backend events.

### 5.4 Decision Cards
Templated, data-driven — never free-form prose. Required fields:
- Underlying
- Market regime (volatility condition + trend condition)
- Selected strategy
- Opportunity score (X/100) with list of checks passed / failed
- Position details (credit received, spread width, breakeven, max loss, days to expiry) — for TRADE cards
- Risk Gate result (approved/rejected + why)
- Final decision (EXECUTE TRADE / NO TRADE / WATCH / EXPIRED) + reason if declined/expired

Build a single card-rendering component/template that consumes a structured decision object — reuse it everywhere (dashboard, any exported screenshots, docs), so card text can never drift from the underlying data.

---

## 6. System Architecture (perception → decision → action loop)

| Stage | Responsibility |
|---|---|
| Perception | Pull account state, positions, market/options-chain data via Alpaca MCP tools for the watchlist |
| Signal Evaluation | Compute volatility + trend condition per underlying; determine matrix cell |
| Opportunity Evaluation | Run scored checklist, apply hard gates, assign TRADE/WATCH/REJECT |
| Decision | Select specific structure, strikes, and expiry consistent with the signal reading (or no action) |
| Risk Gate | Independently validate against sizing, concurrency, event-avoidance rules |
| Execution | Place/manage orders via Alpaca Trading API through the MCP server; monitor open positions against exit rules |
| Logging & Presentation | Record every decision (including declines) as a decision card; surface on dashboard with live P&L |

Full flow: `market scan → regime detection → strategy selection → opportunity scoring → risk evaluation → TRADE/WATCH/REJECT → execution → decision card + reasoning log → position and decision-quality monitoring`

Nothing in perception, decision, or execution should require manual triggering — the loop should run on a schedule/interval end-to-end.

---

## 7. Decision Quality Monitoring

### 7.1 Activity Ledger (raw counts — no derived ratios)
- Opportunities scanned, by underlying
- Decisions issued: counts of TRADE / WATCH / REJECT / EXPIRED
- Rejection reasons, ranked by frequency
- Checks most frequently failed (shows which condition is actually binding)
- WATCH items promoted to TRADE, and the promoting condition

### 7.2 Outcome Measures (report with explicit sample sizes)
- Realized and open P&L, account equity curve across the window
- Trades closed at profit target vs. stop vs. time-based exit
- Result per closed position, listed individually
- Average opportunity score: executed trades vs. declined ones

### 7.3 Filter Value Baseline
Alongside the live agent, track — without trading them — two naive baselines on the same watchlist/window:
- **Unfiltered baseline:** every setup the strategy matrix matches, ignoring the opportunity score and soft checks
- **Passive baseline:** buy-and-hold the primary underlying

These carry no capital/risk. Implement as an additional recorder that runs inside the same scan loop the live agent already executes, storing what each baseline "would have done" for later comparison on the dashboard/report.

### 7.4 Presentation Discipline
- Segments with fewer than 5 observations show raw counts, not rates.
- Segmented breakdowns (by regime, by strategy) are illustrative of mechanism, never presented as performance statistics given the small sample size expected over ~5 sessions.

---

## 8. Dashboard Requirements (financial-terminal style)

Must show, all backed by real recorded state:
1. Live decision pipeline, stage by stage, as the agent works through each cycle
2. Current open positions with live mark-to-market P&L
3. Running account equity/P&L curve across the judging window, with the two baseline curves overlaid
4. Chronological reasoning log of decision cards — trades taken, watched, and declined, with reasons
5. Current volatility and trend readings per watchlist underlying (so regime detection is visible in real time)

Style reference: dark theme, dense/numeric layout, monospace accents — consistent with the team's prior financial dashboard work. Keep this a single cohesive view (or a small number of linked views) rather than a sprawling multi-page app.

---

## 9. Build Order (must be followed — do not build dashboard before go-live)

| Phase | Focus | Deliverable |
|---|---|---|
| Day 1 | Foundation | Paper trading account set up; Alpaca CLI + MCP server connected end-to-end; verify account options approval level and multi-leg order support; finalize and write down all strategy rules and numeric risk limits into config |
| Day 2 | Signal layer | Implement + validate volatility and trend signals against historical and live data (no live orders yet); run opportunity scorer in observation-only mode; calibrate thresholds against real score distribution |
| Day 3 | Go-live | Connect decision layer to real order placement with risk gate active; place and log first real paper trades; start baseline recorders |
| Day 4–5 | Live operation + dashboard | Agent runs continuously, accumulating track record; build decision pipeline view, decision cards, and monitoring panels against real, live data |
| Day 6 | Freeze & document | Code freeze; agent continues trading passively; draft video, slides, README using real screenshots and real results |
| Day 7 | Submission | Package repository, hosted demo, video, slides, account ID; buffer for last issues |

Implement in this order. Do not front-load dashboard/UI work — the trading loop and real order flow must exist and be running before significant frontend work begins.

---

## 10. Suggested Project Structure (guidance, not prescriptive)

- `config/` — all thresholds, risk limits, watchlist, score-band cutoffs (single source of truth)
- `agent/perception/` — Alpaca MCP data pulls (account, positions, chains, price history)
- `agent/signals/` — volatility signal, trend signal
- `agent/strategy/` — selection matrix logic, structure/strike/expiry selection
- `agent/evaluation/` — scored checklist, hard gates, score-band resolution
- `agent/risk/` — risk gate (sizing, concurrency, event-avoidance)
- `agent/execution/` — order placement + open-position exit monitoring via Alpaca MCP/API
- `agent/watch/` — WATCH state persistence, promotion/expiry logic
- `agent/baselines/` — unfiltered + passive baseline recorders
- `agent/logging/` — event log + decision card generation (single template, structured input)
- `storage/` — persistence layer (SQLite or equivalent) for decisions, positions, events, baselines
- `dashboard/` — React frontend consuming the event/decision store
- `docs/` — README, submission materials

---

## 11. Deliverables Required for Submission (keep in mind while building)
- Public GitHub repository
- Hosted demo
- Video walkthrough (showing the agent operating live, not a scripted walkthrough of static screens)
- Slide presentation
- Alpaca paper trading account ID (judges will verify results against the live account — so all reported numbers must be traceable to real account activity, not fabricated for the demo)

---

## 12. Summary of What "Done" Looks Like
- Agent has been placing real, defined-risk paper trades since Day 3, entirely through Alpaca MCP tools, governed by the strategy matrix + risk rules above.
- Every opportunity the agent has looked at — traded, watched, rejected, or expired — has a decision card generated from real structured data.
- Dashboard shows the live pipeline, positions, equity curve (with baselines), and the reasoning log, with nothing simulated in the frontend.
- Activity ledger and outcome measures are queryable, with sample-size discipline respected everywhere a rate is shown.
- Config-driven thresholds mean recalibration doesn't require touching core logic.
