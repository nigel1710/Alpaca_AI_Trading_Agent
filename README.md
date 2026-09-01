# Options Alpha Agent

**Team:** The Overfitters
**Event:** Alpaca AI Trading Agents Hackathon (Aug 28 – Sep 4, 2026)
**Track:** Options Alpha Agents

An autonomous options trading agent running on Alpaca's paper trading environment. It scans SPY/QQQ/IWM for credit spread and iron condor opportunities, scores each candidate against a 9-check checklist, and executes defined-risk trades through a strict Risk Gate — logging every decision with full reasoning for display on a financial-terminal-style React dashboard.

---

## Architecture

```
Perception → Signal Evaluation → Opportunity Scoring → Risk Gate → Execution
     ↓              ↓                    ↓                ↓           ↓
  Alpaca API    IV + Trend          9-check scored    Independent  mleg orders
  bars/chain    signals             checklist         gate (never  via Alpaca
  account       classify vol        TRADE/WATCH/      bypassed)    API
                classify trend      REJECT
                                         ↓
                                   SQLite decisions/events → FastAPI → React dashboard
```

---

## Setup

### 1. Python environment

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment variables

```bash
cp .env.example .env
# Edit .env and fill in your Alpaca paper credentials:
#   ALPACA_API_KEY=your_paper_key
#   ALPACA_SECRET_KEY=your_paper_secret
#   ALPACA_BASE_URL=https://paper-api.alpaca.markets  (already set)
#   DRY_RUN=true  (change to false when ready for real paper orders)
```

**Never commit `.env` — it is gitignored.**

### 3. Alpaca MCP server (optional, for Claude Code integration)

See `mcp/README.md`. Configure at user level — never inside this repo.

---

## Running the agent

### Single scan cycle (verify the loop)

```bash
python -m cli.main scan --verbose
```

Prints each pipeline stage as it runs:
```
[MARKET SCAN]   Scanning: SPY, QQQ, IWM | cycle=a1b2c3d4
[MARKET ANALYSIS SPY]  Trend: UP (sep=0.87%), Vol: ELEVATED (ratio=1.45)
[STRATEGY SPY]  Selected: BULL_PUT
[EVALUATION SPY]  Score: 75/100  Outcome: WATCH
[RISK GATE SPY]  APPROVED: All risk checks passed
[TRADE SPY]  Order placed: dry-run-abc123
```

### Monitor open positions only (no entry scanning)

```bash
python -m cli.main monitor
```

Checks every open position against its exit rules (profit target, stop loss,
time exit) and closes what triggers. Kept separate from `scan` on purpose so
open risk can be checked more often than new opportunities are sought — the
scanner not running must never mean a stop-loss goes unchecked.

It also **reconciles with the broker first**: any option position Alpaca
reports that has no local record is rebuilt from the broker's own fills and
brought back under exit management. This matters on hosted deployments with
an ephemeral filesystem, where a restart can wipe the database while the
positions live on.

### Continuous agent loop (market hours only)

```bash
python -m agent.main
```

Runs every 15 minutes, 9:30–16:00 ET, Monday–Friday. Handles SIGINT/SIGTERM gracefully.

### Scheduling on the hosted deployment

The deployment does **not** use external cron. GitHub Actions' scheduled
runner never fired for this repository (zero scheduled runs over several
hours inside the window, while manual dispatches worked every time), and
Render's cron jobs require a paid plan. Instead the schedule runs inside the
app (`agent/scheduler.py`), started with the API server when
`ENABLE_SCHEDULER=true`:

- **positions monitored** every `MONITOR_INTERVAL_MINUTES` (default 5)
- **new opportunities scanned** every `SCAN_INTERVAL_MINUTES` (default 15)
- market hours only, in real Eastern time (follows DST automatically)

**One external dependency remains.** A free Render instance spins down after
~15 minutes without inbound HTTP traffic, which stops the scheduler with it.
Point any uptime pinger (UptimeRobot, Better Uptime, Cronitor) at:

```
GET https://<your-app>.onrender.com/api/health
```

every 5 minutes. That request needs no authentication, keeps the instance
awake, and returns the scheduler's state so the same ping doubles as a
health check:

```json
{"status":"ok","scheduler_enabled":true,"scheduler_running":true,"market_hours":true}
```

If `scheduler_running` is ever `false` while `scheduler_enabled` is `true`,
the background task died and the service needs a restart.

To force a scan on demand (before a demo, say):

```bash
curl -X POST -H "X-Scan-Token: $SCAN_TRIGGER_TOKEN" \
  https://<your-app>.onrender.com/api/scan

# exits only:
curl -X POST -H "X-Scan-Token: $SCAN_TRIGGER_TOKEN" \
  https://<your-app>.onrender.com/api/monitor
```

### Score distribution report

```bash
python -m cli.main score-report --days 1
```

Prints score histogram, check failure frequency, outcome counts, and rejection reasons.
Respects sample-size discipline: rates shown only when N≥5.

### End-of-window flatten (close all positions)

```bash
python -m cli.main flatten --confirm
```

Closes all open positions with reason `FLATTEN`. Requires `--confirm` flag.

---

## REST API + Dashboard

### Start the API server

```bash
uvicorn api.server:app --reload --port 8000
```

Available endpoints:
- `GET /api/events` — pipeline stage events
- `GET /api/decisions` — scored decision cards
- `GET /api/positions` — open positions
- `GET /api/watch_items` — WATCH state items
- `GET /api/account` — live Alpaca account state
- `GET /api/pipeline/latest` — most recent scan cycle events
- `GET /api/baselines` — unfiltered + passive baseline records
- `GET /api/circuit_breaker/today` — daily circuit breaker state
- `GET /api/health` — health check

### Start the dashboard

```bash
cd dashboard
npm install
npm run dev
```

Open http://localhost:5173. The dashboard polls the API every 5 seconds and renders **recorded backend state only** — nothing is simulated in the frontend.

To build for production (served by the FastAPI server):

```bash
cd dashboard && npm run build
# dashboard/dist/ is now served at /
```

---

## Configuration

All thresholds live in `config/settings.py` — no inline hardcoding anywhere else.

| Parameter | Default | Description |
|---|---|---|
| `WATCHLIST` | `["SPY","QQQ","IWM"]` | Underlyings to scan |
| `DTE_MIN` / `DTE_MAX` | 2 / 9 | Expiry window (days to expiry) |
| `EXPIRY_CUTOFF` | `2026-09-04` | No expiries on or after this date |
| `MA_SHORT` / `MA_LONG` | 10 / 30 | Moving average periods |
| `TREND_CLARITY_THRESHOLD` | 0.005 | Min MA separation (0.5% of price) |
| `IV_RICH_MULTIPLIER` | 1.2 | ATM IV / 20d RVol ratio for ELEVATED |
| `IV_STABLE_MULTIPLIER` | 1.15 | ATM IV / 3d avg ratio for stability |
| `CREDIT_WIDTH_FLOOR` | 0.30 | Min credit as fraction of spread width |
| `DELTA_CEILING` | 0.20 | Max short-strike delta |
| `LIQUIDITY_SPREAD_MAX` | 0.10 | Max bid-ask spread as fraction of credit |
| `LIQUIDITY_OI_MIN` | 100 | Min open interest per leg |
| `MAX_LOSS_PCT` | 0.02 | Max loss per trade (2% of equity) |
| `MAX_CONCURRENT_POSITIONS` | 4 | Max open positions at once |
| `PROFIT_TARGET` | 0.50 | Close at 50% of credit collected |
| `STOP_LOSS_MULTIPLE` | 2.0 | Close at 2× credit collected |
| `TIME_EXIT_DTE` | 1 | Time-based exit at 1 DTE |
| `WATCH_EXPIRY_CYCLES` | 2 | WATCH items expire after 2 scan cycles |
| `SCAN_INTERVAL_MINUTES` | 15 | Scan frequency during market hours |
| `SCORE_TRADE_MIN` | 80 | Minimum score to attempt trade |
| `SCORE_WATCH_MIN` | 60 | Minimum score to enter WATCH state |
| `CIRCUIT_BREAKER_MAX_ORDERS` | 10 | Halt after this many daily order attempts |
| `CIRCUIT_BREAKER_DRAWDOWN_PCT` | 0.03 | Halt after 3% intraday drawdown |

---

## DRY_RUN mode

`DRY_RUN=true` is the **default**. In this mode:
- The entire scan loop runs and logs decisions normally.
- No orders are sent to Alpaca.
- Order responses are mocked with `id="dry-run-{uuid}"`.
- All DB records (decisions, positions, events) are written as if orders were placed.

To enable real paper order placement:
```bash
# In .env:
DRY_RUN=false
```

---

## Earnings data (Check 8)

Check 8 ("Event clear") uses **yfinance** to retrieve earnings calendar data, since Alpaca does not provide this. If yfinance fails for a symbol, Check 8 defaults to **PASS** with a warning logged — it does not block scanning.

---

## Circuit breaker

The daily circuit breaker halts all new order placement if:
1. **Order attempts ≥ 10** in a single trading day, OR
2. **Intraday drawdown ≥ 3%** of starting equity

The halt is logged as an event and recorded in the `circuit_breaker` DB table. It resets automatically the next trading day (a new row is inserted for each date).

---

## Project structure

```
options-alpha-agent/
├── config/settings.py          # Single source of truth for all parameters
├── storage/
│   ├── schema.sql              # SQLite schema
│   └── db.py                   # Async DB wrapper (aiosqlite)
├── agent/
│   ├── perception/             # Alpaca client, account, market data
│   ├── signals/                # IV + trend signal computation
│   ├── strategy/               # Selection matrix + structure builder
│   ├── evaluation/             # 9-check scored checklist + scoring
│   ├── risk/                   # Independent risk gate
│   ├── execution/              # Order placement, monitor, circuit breaker
│   ├── watch/                  # WATCH state persistence + lifecycle
│   ├── baselines/              # Unfiltered + passive baseline recorders
│   ├── logging/                # Event emission + decision card builder
│   └── main.py                 # Main agent loop
├── api/server.py               # FastAPI REST server
├── cli/
│   ├── scan.py                 # Single cycle CLI
│   ├── report.py               # Score distribution report
│   ├── flatten.py              # Close all positions
│   └── main.py                 # Click group entry point
├── dashboard/                  # React + Vite + TypeScript frontend
├── mcp/README.md               # Alpaca MCP server user-level setup
├── .env.example                # Template (fill in, rename to .env)
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Dashboard screenshots

_To be added after go-live on Day 3._

---

## Submission checklist

- [ ] Public GitHub repository
- [ ] Alpaca paper trading account ID
- [ ] Hosted demo URL
- [ ] Video walkthrough (agent operating live)
- [ ] Slide presentation
