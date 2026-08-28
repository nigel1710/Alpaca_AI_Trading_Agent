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

# --- Watchlist ---
WATCHLIST: list[str] = ["SPY", "QQQ", "IWM"]

# --- Expiry selection ---
DTE_MIN: int = 2
DTE_MAX: int = 9
EXPIRY_CUTOFF: str = "2026-09-04"  # only consider expiries before this date

# --- Trend signal ---
MA_SHORT: int = 10
MA_LONG: int = 30
TREND_CLARITY_THRESHOLD: float = 0.005  # 0.5% of price

# --- Volatility signal ---
IV_RICH_MULTIPLIER: float = 1.2    # ATM IV >= 1.2x 20-day realized vol → ELEVATED
IV_STABLE_MULTIPLIER: float = 1.15  # today ATM IV <= 1.15x 3-day avg → stable

# --- Scored checklist thresholds ---
CREDIT_WIDTH_FLOOR: float = 0.30  # credit >= 30% of spread width
DELTA_CEILING: float = 0.20       # short strike delta <= 0.20
LIQUIDITY_SPREAD_MAX: float = 0.10  # bid-ask spread <= 10% of credit
LIQUIDITY_OI_MIN: int = 100         # open interest >= 100 per leg

# --- Risk management ---
MAX_LOSS_PCT: float = 0.02          # 2% of account equity per trade
MAX_CONCURRENT_POSITIONS: int = 4

# --- Exit rules ---
PROFIT_TARGET: float = 0.50         # close at 50% of credit collected
STOP_LOSS_MULTIPLE: float = 2.0     # close at 2x credit collected
TIME_EXIT_DTE: int = 1              # close at 1 DTE

# --- WATCH lifecycle ---
WATCH_EXPIRY_CYCLES: int = 2        # WATCH items expire after 2 scan cycles

# --- Scheduling ---
SCAN_INTERVAL_MINUTES: int = 15

# --- Score bands ---
SCORE_TRADE_MIN: int = 80
SCORE_WATCH_MIN: int = 60

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
