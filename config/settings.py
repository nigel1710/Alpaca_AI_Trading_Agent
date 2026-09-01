"""Single source of truth for all configurable parameters."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

# --- Alpaca credentials (from env) ---
ALPACA_API_KEY: str = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY: str = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL: str = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

# DRY_RUN defaults to True — must explicitly set DRY_RUN=false to place live orders
_dry_run_env = os.getenv("DRY_RUN", "true").strip().lower()
DRY_RUN: bool = _dry_run_env not in ("false", "0", "no")

# Optional shared-secret token required to call POST /api/scan when set.
# Leave unset for local dev; set on public deployments to prevent anyone
# with the URL from triggering scans (and, if DRY_RUN=false, real orders).
SCAN_TRIGGER_TOKEN: str = os.getenv("SCAN_TRIGGER_TOKEN", "")

# --- Watchlist ---
WATCHLIST: list[str] = ["SPY", "QQQ", "IWM"]

# --- Expiry selection (credit spreads: short-dated premium selling) ---
DTE_MIN: int = 2
DTE_MAX: int = 9
EXPIRY_CUTOFF: str = "2026-09-04"  # credit spreads only: no expiries on/after this date

# --- Expiry selection (debit spreads: directional theses need time to develop) ---
# NOTE: EXPIRY_CUTOFF above is deliberately NOT applied to debit spreads — a
# 21-45 DTE window cannot coexist with a cutoff a few days out. See README.
DEBIT_DTE_MIN: int = 21
DEBIT_DTE_MAX: int = 45
DEBIT_DTE_TARGET: int = 32  # midpoint of the preferred 30-35 range

# --- Trend signal ---
MA_SHORT: int = 10
MA_LONG: int = 30
TREND_CLARITY_THRESHOLD: float = 0.005  # 0.5% of price
# FAIR-volatility regimes require stronger directional confirmation before
# a debit spread is considered at all (strategy doc §5).
TREND_STRONG_MULTIPLIER: float = 1.5  # need 1.5x TREND_CLARITY_THRESHOLD

# --- Volatility regime (three-band: CHEAP / FAIR / RICH) ---
IV_CHEAP_MAX: float = 0.90    # IV/RVol <  0.90        → CHEAP  (buy premium)
IV_RICH_MIN: float = 1.20     # IV/RVol >  1.20        → RICH   (sell premium)
                              # between the two        → FAIR   (needs confirmation)
IV_RICH_MULTIPLIER: float = IV_RICH_MIN  # back-compat alias
IV_STABLE_MULTIPLIER: float = 1.15  # today ATM IV <= 1.15x 3-day avg → stable

# --- Credit spread checklist thresholds ---
CREDIT_WIDTH_FLOOR: float = 0.30  # credit >= 30% of spread width
DELTA_CEILING: float = 0.30       # short strike delta <= 0.30
LIQUIDITY_SPREAD_MAX: float = 0.10  # bid-ask spread <= 10% of credit/debit
LIQUIDITY_OI_MIN: int = 100         # open interest >= 100 per leg

# --- Debit spread checklist thresholds ---
DEBIT_LONG_DELTA_MIN: float = 0.45   # long leg near-the-money
DEBIT_LONG_DELTA_MAX: float = 0.65
DEBIT_SHORT_DELTA_MIN: float = 0.20  # short leg further out
DEBIT_SHORT_DELTA_MAX: float = 0.40
DEBIT_RR_MIN: float = 1.5            # minimum reward/risk to be considered
DEBIT_RR_PREFERRED: float = 2.0      # full points at or above this
# Required move must leave headroom inside the expected move; a spread needing
# the full expected move to break even is not a realistic trade.
REQUIRED_MOVE_HEADROOM: float = 0.80  # required_move <= 0.80 * expected_move

# --- Risk management ---
MAX_LOSS_PCT: float = 0.02          # 2% of account equity per trade
MAX_CONCURRENT_POSITIONS: int = 4

# --- Exit rules (credit spreads) ---
PROFIT_TARGET: float = 0.50         # close at 50% of credit collected
STOP_LOSS_MULTIPLE: float = 2.0     # close at 2x credit collected
TIME_EXIT_DTE: int = 1              # close at 1 DTE

# --- Exit rules (debit spreads) ---
# A debit spread is closed by SELLING it back, so value moves the other way:
# profit when it is worth more than paid, stop when it has lost value.
DEBIT_PROFIT_CAPTURE: float = 0.50  # take 50% of max achievable profit
DEBIT_STOP_LOSS_PCT: float = 0.50   # stop after losing 50% of premium paid
DEBIT_TIME_EXIT_DTE: int = 7        # close at 7 DTE — theta decay accelerates

# How far to cross the market when closing, so exit orders actually fill.
# An exit that rests unfilled is the same as having no stop at all.
CLOSE_SLIPPAGE_BUFFER: float = 0.05  # 5% through the current spread value

# --- WATCH lifecycle ---
WATCH_EXPIRY_CYCLES: int = 2        # WATCH items expire after 2 scan cycles

# --- Scheduling ---
SCAN_INTERVAL_MINUTES: int = 15
# Open positions are checked far more often than we look for new entries —
# a stop that is only evaluated every 15 minutes is a slow stop.
MONITOR_INTERVAL_MINUTES: int = 5
# Run the in-process scheduler alongside the API server. Off by default so
# local CLI use and tests never start a background trader; the hosted
# deployment opts in via ENABLE_SCHEDULER=true.
ENABLE_SCHEDULER: bool = os.getenv("ENABLE_SCHEDULER", "false").strip().lower() in (
    "true", "1", "yes",
)

# --- Score bands / confidence (strategy doc §11) ---
#   80-100 → HIGH   conviction → TRADE
#   65-79  → MEDIUM          → WATCH / CONDITIONAL
#   < 65   → LOW             → STAND ASIDE
SCORE_TRADE_MIN: int = 80
SCORE_WATCH_MIN: int = 65

# --- Circuit breaker ---
CIRCUIT_BREAKER_MAX_ORDERS: int = 10
CIRCUIT_BREAKER_DRAWDOWN_PCT: float = 0.03  # 3% daily drawdown halt

# --- DB path ---
DB_PATH: str = str(Path(__file__).parent.parent / "agent.db")

# --- Validate credentials at import time ---
if not ALPACA_API_KEY:
    logger.warning("ALPACA_API_KEY is not set. Agent will not be able to connect to Alpaca.")
if not ALPACA_SECRET_KEY:
    logger.warning("ALPACA_SECRET_KEY is not set. Agent will not be able to connect to Alpaca.")

if DRY_RUN:
    logger.info("DRY_RUN=True — no real orders will be placed.")
else:
    logger.warning("DRY_RUN=False — LIVE ORDER PLACEMENT IS ENABLED on paper account.")
