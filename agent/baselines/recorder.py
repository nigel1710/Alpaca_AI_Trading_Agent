"""Unfiltered and passive baseline recorders."""

import logging
from typing import Optional

from storage import db as storage

logger = logging.getLogger(__name__)


async def record_unfiltered_baseline(
    db,
    cycle_id: str,
    underlying: str,
    strategy: str,
    structure: Optional[dict],
) -> None:
    """Record what the strategy matrix selected, ignoring opportunity score."""
    if strategy != "STAND_ASIDE" and structure is not None:
        action = "WOULD_TRADE"
        details = {
            "strategy": strategy,
            "credit": structure.get("credit"),
            "spread_width": structure.get("spread_width"),
            "expiry": structure.get("expiry"),
            "short_strike": structure.get("short_strike"),
            "long_strike": structure.get("long_strike"),
        }
    else:
        action = "STAND_ASIDE"
        details = {"strategy": strategy}

    await storage.insert_baseline_record(
        cycle_id=cycle_id,
        baseline_type="UNFILTERED",
        underlying=underlying,
        action=action,
        details=details,
    )


async def record_passive_baseline(
    db,
    cycle_id: str,
    underlying: str,
    current_price: float,
    starting_price: float,
) -> None:
    """Record a buy-and-hold data point."""
    if starting_price > 0:
        pnl_pct = (current_price - starting_price) / starting_price
    else:
        pnl_pct = 0.0

    await storage.insert_baseline_record(
        cycle_id=cycle_id,
        baseline_type="PASSIVE",
        underlying=underlying,
        action="HOLD",
        details={
            "current_price": current_price,
            "starting_price": starting_price,
            "pnl_pct": round(pnl_pct, 6),
        },
    )
