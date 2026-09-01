# Options Alpha Agent — Development Log

Summary of work done and issues encountered, for team reference.

---

## 1. Initial state and setup

- Repo pushed to GitHub as a public repo: `github.com/nigel1710/Alpaca_AI_Trading_Agent`.
- Confirmed `.env` / `.env.example` correctly gitignored, no secrets committed.
- Fixed a real (non-cosmetic) typo in `.env.example`: `DRY_RUN=flase` → `DRY_RUN=false`. The misspelled value silently evaluated as `True` regardless, since the settings parser only treats `"false"/"0"/"no"` as falsy.

---

## 2. Bugs found and fixed while getting the pipeline to run end-to-end

These were genuine defects, not tuning — each one blocked the pipeline from working at all until fixed.

| Bug | File | Fix |
|---|---|---|
| Alpaca stock bars request defaulted to the **SIP** data feed, which requires a paid subscription → 403 errors on every scan | `agent/perception/alpaca_client.py` | Explicitly request `feed=DataFeed.IEX` (available on free/paper accounts) |
| `alpaca-py`'s `BarSet` object doesn't support `symbol in bars` / `bars[symbol]` the way the code assumed — always returned empty, even with valid data | `agent/perception/alpaca_client.py` | Use `bars.data` dict directly instead |
| Open interest was **hardcoded to `0`** for every option contract, permanently failing the Liquidity hard gate (Check 7) regardless of real market conditions | `agent/perception/alpaca_client.py` | Added `_get_open_interest_map()` — fetches real OI via Alpaca's **Trading API** (`GetOptionContractsRequest`), since the market-data snapshot API was confirmed (via direct raw JSON inspection) to never report OI at all |
| `ALPACA_BASE_URL` had a stray `/v2` suffix, which combined with the code's own `/v2/orders` path to produce a broken double path (`.../v2/v2/orders`) — would have 404'd on the first real order attempt | local `.env` | Corrected to `https://paper-api.alpaca.markets` (no trailing path) |
| Dashboard's **production build** (`tsc && vite build`) failed across 6 React components — a style-dict pattern mixed plain `CSSProperties` objects with functions returning `CSSProperties` under one over-strict type, which only Vite's dev-mode (no type-check) tolerated | `dashboard/src/**` | Widened the type to `Record<string, any>` in all 6 files — no runtime behavior change, just makes the existing pattern type-check |

---

## 3. Deliberate temporary "demo hack" settings — since resolved

Early on, two thresholds were loosened in `config/settings.py` purely to exercise the full scoring/risk-gate pipeline locally without waiting on rare live market conditions:

- `IV_RICH_MULTIPLIER` temporarily `0.4` (real default `1.2`)
- `LIQUIDITY_OI_MIN` temporarily `0` (real default `100`) — this was really standing in for the OI bug above

**Both have since been reverted to their real defaults.** The OI bug itself was also genuinely fixed (see table above), so `LIQUIDITY_OI_MIN=100` is now a real, meaningful check again, not a bypassed one.

One threshold change was **kept intentionally, not reverted**: `DELTA_CEILING` raised from `0.20` to `0.30`. Low-delta (0.20) short strikes were consistently producing too little credit relative to spread width, failing Check 5 (Credit Quality) on real market data. This was verified to work — the first genuine `TRADE` outcome (IWM, score 85/100) came after this change, on live data, with real thresholds otherwise intact.

---

## 4. Going from simulated to real (paper) trading

- Flipped `DRY_RUN=false` locally.
- Verified a real order was accepted by Alpaca (SPY BULL_PUT, $0.83 credit, short 764P / long 759P) — confirmed both via direct API query (`status: ACCEPTED`) and visually in Alpaca's own paper trading dashboard (account `PA3MCAX999DW`).
- Hit one confusing detour: initially checked the wrong Alpaca paper account in the browser (a different, unrelated paper account under the same login) before finding the correct one matching the API keys in use.

---

## 5. Deployment (Render)

- Added `Dockerfile` (multi-stage: builds the React dashboard, then a Python/FastAPI runtime that serves the built dashboard as static files) and `render.yaml`.
- **Issue:** Render's repo picker only showed repos owned by the connecting GitHub account, not this team repo (owned by a different account). Worked around it using Render's "public repository URL" connection method instead of the GitHub App picker.
- **Consequence of that workaround:** Render's Blueprint "Manual Sync" doesn't actually pull new commits through this connection method — confirmed by pushing a new commit and finding no new sync entry appeared, even after multiple attempts and page refreshes. This also means **auto-deploy on push does not work** for this deployment; changes need a manual redeploy path.
- Live URL: `https://options-alpha-agent.onrender.com` — confirmed working end-to-end (health check, dashboard renders, real decisions produced from live market data).
- Added a `POST /api/scan` endpoint (manual trigger, since the free-tier deployment has no built-in scheduler) protected by a shared-secret header (`X-Scan-Token` / `SCAN_TRIGGER_TOKEN`), since the endpoint is public and unauthenticated by default — added specifically because `DRY_RUN=false` is set on the deployment, so an open endpoint would have let anyone trigger real orders.

---

## 6. Automated scheduling — unresolved issue

- Render's own Cron Job feature turned out to require a **paid plan** — confirmed too costly for this project, so that approach was dropped (config removed from `render.yaml` before it could be provisioned).
- Replaced with a **free GitHub Actions scheduled workflow** (`.github/workflows/scan.yml`) — runs every 15 min during market hours, calls the same token-protected `/api/scan` endpoint. `SCAN_TRIGGER_TOKEN` stored as a GitHub Actions repo secret.
- Manual test runs (`workflow_dispatch`) work correctly every time.
- **Open issue:** the actual `schedule:` cron trigger has not fired even once in ~3+ hours and 9+ missed time slots, despite the workflow showing as `active`. This matches a known (if frustrating) GitHub Actions behavior where brand-new scheduled workflows can take a while for GitHub's backend scheduler to start honoring — no fixed timeline, not something fixable from our side. **Currently working around this by manually triggering scans as needed** rather than relying on the schedule.
- Side effect: because the schedule never fired, the Render free-tier instance sat idle long enough to spin down at least once, which reset its (ephemeral, non-persistent) SQLite database — wiping decision history until the next manual trigger repopulated it. This is expected behavior for Render's free tier, not a separate bug, but worth knowing: **decision history on the deployed dashboard is not durable** across spin-downs/redeploys.

---

## 7. Open position monitoring — investigated, not yet re-triggered

- The live SPY BULL_PUT position showed a growing unrealized loss (~$100+) when checked directly in Alpaca's dashboard.
- Investigated whether the automated stop-loss (`STOP_LOSS_MULTIPLE = 2.0`) had a bug. **Conclusion: the exit logic itself is correct** — verified with live quotes that the position's real cost-to-close (~$1.82–2.16) already exceeds the stop threshold (~$1.67).
- Root cause: `monitor_open_positions()` only runs as part of a scan cycle, and scans have only been happening on manual triggers (tied to the scheduling issue above) rather than continuously. The position simply hasn't been re-checked since it crossed the stop threshold — it should close automatically on the next scan.

---

## 8. Strategy direction — in progress

- Team decided to move toward a "medium risk, high reward" strategy, as the current credit-spread-only approach is structurally the opposite (small capped reward, larger possible loss).
- Wrote up a design proposal (`MEDIUM_RISK_HIGH_REWARD_PROPOSAL.md`) covering: why credit spreads don't fit that goal, a proposed debit-spread strategy as the natural fit, one pivotal open design question (debit spreads want the *opposite* volatility signal from credit spreads — cheap IV to buy into, not rich IV to sell), how each of the 9 checklist checks would need to adapt, and a list of decisions deliberately left open for the team.
- **No implementation yet** — awaiting team review/decision on the open questions in that doc.

---

## 9. Current submission status

| Requirement | Status |
|---|---|
| Public GitHub Repo | Done — `github.com/nigel1710/Alpaca_AI_Trading_Agent` |
| Demo Application Platform | Done — Render |
| Application URL | Done — `https://options-alpha-agent.onrender.com` |
| Alpaca Paper Trading Account ID | Done — `PA3MCAX999DW` |

---

## 10. Known outstanding issues (not yet fixed)

- **GitHub Actions schedule not firing automatically** — see §6. Currently mitigated by manual triggering.
- **Deployed dashboard data isn't durable** — resets on Render free-tier spin-down/redeploy (ephemeral SQLite).
- **Dashboard's "ET" clock is mislabeled** — it displays the viewer's local browser timezone, not actual US Eastern Time (`App.tsx` uses `new Date().toLocaleTimeString()` with no timezone conversion). Cosmetic, not yet fixed.
- **yfinance earnings fetch throws a harmless warning on every scan** — `ticker.calendar` returns a dict (not a DataFrame) in the installed yfinance version, causing a caught `AttributeError`. Check 8 correctly defaults to PASS regardless, so this doesn't affect decisions — just log noise. Low priority.
- **Render Blueprint auto-sync doesn't work** for this repo connection method — see §5. Future `render.yaml` changes will need manual service reconfiguration or a properly authenticated GitHub connection (would need the repo owner to grant access).
- **Regime Readings panel** has occasionally shown stale/mismatched data relative to the latest cycle (cosmetic, not investigated in depth).
