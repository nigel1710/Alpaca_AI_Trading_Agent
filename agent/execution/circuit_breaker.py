"""Daily circuit breaker: halt after N order attempts or P% drawdown."""

import logging
from datetime import date

from config import settings
from storage import db as storage

logger = logging.getLogger(__name__)


async def init_daily_circuit_breaker(database, account_equity: float) -> None:
    today = date.today().isoformat()
    await storage.init_circuit_breaker(today, account_equity)


async def check_circuit_breaker(database, account_equity: float) -> tuple[bool, str]:
    """Returns (halted, reason). Checks halted flag, order attempts, and drawdown."""
    today = date.today().isoformat()
    record = await storage.get_circuit_breaker(today)

    if record is None:
        return False, ""

    # Already manually halted
    if record["halted"]:
        return True, record["halt_reason"] or "Circuit breaker halted"

    # Order attempt limit
    if record["order_attempts"] >= settings.CIRCUIT_BREAKER_MAX_ORDERS:
        reason = f"Order attempt limit reached ({record['order_attempts']}/{settings.CIRCUIT_BREAKER_MAX_ORDERS})"
        await storage.halt_circuit_breaker(today, reason)
        return True, reason

    # Drawdown check
    starting = record.get("starting_equity")
    if starting and starting > 0:
        drawdown = (starting - account_equity) / starting
        if drawdown >= settings.CIRCUIT_BREAKER_DRAWDOWN_PCT:
            reason = (
                f"Daily drawdown {drawdown:.2%} exceeds limit "
                f"({settings.CIRCUIT_BREAKER_DRAWDOWN_PCT:.0%})"
            )
            await storage.halt_circuit_breaker(today, reason)
            return True, reason

    return False, ""


async def increment_attempts(database) -> int:
    """Increment attempt counter; halts automatically if limit reached."""
    today = date.today().isoformat()
    count = await storage.increment_order_attempts(today)
    if count >= settings.CIRCUIT_BREAKER_MAX_ORDERS:
        reason = f"Order attempt limit reached ({count}/{settings.CIRCUIT_BREAKER_MAX_ORDERS})"
        await storage.halt_circuit_breaker(today, reason)
        logger.warning("CIRCUIT BREAKER: %s", reason)
    return count
