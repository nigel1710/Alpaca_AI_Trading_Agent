"""In-process scheduler for the hosted deployment.

External cron proved unreliable (GitHub Actions' scheduler never fired for
this repo, and Render's cron jobs are a paid feature), so the schedule lives
in the app itself: a background task started with the API server.

Position monitoring runs on a faster cadence than entry scanning (strategy
doc §14) — an open position's stop must be checked far more often than we
look for new opportunities.

The one thing this cannot do by itself is stay awake: a free Render web
service spins down after ~15 minutes without inbound HTTP traffic, which
kills this task too. Point an uptime pinger at GET /api/health to keep the
instance alive; see README.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

import pytz

from agent.main import run_position_monitor, run_scan_cycle
from agent.perception.alpaca_client import AlpacaClient
from config import settings
from storage.db import get_db

logger = logging.getLogger(__name__)

ET = pytz.timezone("America/New_York")


def is_market_hours(now: Optional[datetime] = None) -> bool:
    """True during regular US equity market hours, in real Eastern time.

    Uses a proper timezone rather than a UTC offset so this follows DST on
    its own. Does not account for market holidays — on a holiday the loop
    simply finds nothing tradeable.
    """
    now_et = (now or datetime.now(ET)).astimezone(ET)
    if now_et.weekday() >= 5:  # Saturday / Sunday
        return False
    open_t = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    close_t = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return open_t <= now_et < close_t


async def _run_once(client: AlpacaClient, do_scan: bool) -> None:
    """One tick: always monitor open risk, scan for entries only when due."""
    db = await get_db()

    # Monitoring comes first and is never skipped — protecting an open
    # position matters more than finding a new one.
    try:
        closed = await run_position_monitor(db, client, verbose=False)
        if closed:
            logger.info("Scheduler: closed %d position(s)", len(closed))
    except Exception:
        logger.exception("Scheduler: position monitor failed")

    if not do_scan:
        return

    try:
        await run_scan_cycle(db, client, verbose=False)
    except Exception:
        logger.exception("Scheduler: scan cycle failed")


async def scheduler_loop(stop_event: asyncio.Event) -> None:
    """Monitor every MONITOR_INTERVAL, scan every SCAN_INTERVAL, market hours only."""
    client = AlpacaClient()
    monitor_interval = max(settings.MONITOR_INTERVAL_MINUTES, 1) * 60
    scan_interval = max(settings.SCAN_INTERVAL_MINUTES, 1) * 60
    seconds_since_scan = scan_interval  # scan on the first in-hours tick

    logger.info(
        "Scheduler started: monitor every %dm, scan every %dm, market hours only "
        "(DRY_RUN=%s)",
        settings.MONITOR_INTERVAL_MINUTES,
        settings.SCAN_INTERVAL_MINUTES,
        settings.DRY_RUN,
    )

    try:
        while not stop_event.is_set():
            if is_market_hours():
                due = seconds_since_scan >= scan_interval
                await _run_once(client, do_scan=due)
                seconds_since_scan = 0 if due else seconds_since_scan + monitor_interval
            else:
                # Reset so the first tick after the open always scans.
                seconds_since_scan = scan_interval

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=monitor_interval)
            except asyncio.TimeoutError:
                pass
    finally:
        await client.close()
        logger.info("Scheduler stopped.")
