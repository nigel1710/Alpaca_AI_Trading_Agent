"""WATCH state persistence, promotion, and expiry logic."""

import logging
from typing import Optional

from config import settings
from storage import db as storage

logger = logging.getLogger(__name__)


async def add_watch_item(
    db,
    underlying: str,
    strategy: str,
    score: int,
    failing_checks: list[str],
    promoting_condition: str,
    cycle_id: str,
) -> int:
    """Upsert: if underlying already has WATCHING entry, update score and reset cycles."""
    item_id = await storage.upsert_watch_item(
        underlying=underlying,
        strategy=strategy,
        score=score,
        failing_checks=failing_checks,
        promoting_condition=promoting_condition,
        cycle_id=cycle_id,
    )
    logger.info(
        "WATCH: %s (score=%d, promoting=%s)", underlying, score, promoting_condition
    )
    return item_id


async def process_watch_items(
    db,
    current_scores: dict[str, int],
    current_cycle_id: str,
) -> list[dict]:
    """Re-evaluate WATCHING items; promote or mark EXPIRED. Returns promoted items."""
    watching = await storage.get_watch_items(state="WATCHING")
    promoted = []

    for item in watching:
        underlying = item["underlying"]
        current_score = current_scores.get(underlying)

        if current_score is not None and current_score >= settings.SCORE_TRADE_MIN:
            await storage.promote_watch_item(item["id"], current_cycle_id)
            logger.info(
                "PROMOTED WATCH→TRADE: %s (new score=%d)", underlying, current_score
            )
            promoted.append(item)

    return promoted


async def expire_stale_watches(db, cycle_id: str) -> list[dict]:
    """Decrement cycles and expire watches with 0 cycles remaining."""
    await storage.decrement_watch_cycles(cycle_id)
    expired = await storage.expire_watch_items(cycle_id)
    for item in expired:
        logger.info("EXPIRED WATCH: %s (strategy=%s)", item["underlying"], item["strategy"])
    return expired
