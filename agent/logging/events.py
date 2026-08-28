"""Event emission helpers for each pipeline stage."""

import uuid
from dataclasses import asdict
from typing import Optional

from storage import db as storage


def new_cycle_id() -> str:
    return str(uuid.uuid4())[:8]


async def emit_event(
    db,
    cycle_id: str,
    stage: str,
    payload: dict,
    underlying: Optional[str] = None,
) -> int:
    return await storage.insert_event(
        cycle_id=cycle_id,
        stage=stage,
        payload=payload,
        underlying=underlying,
    )


async def emit_market_scan(db, cycle_id: str, watchlist: list[str]) -> None:
    await emit_event(db, cycle_id, "MARKET_SCAN", {"watchlist": watchlist})


async def emit_market_analysis(
    db,
    cycle_id: str,
    underlying: str,
    vol_cond: str,
    trend_cond: str,
    payload: dict,
) -> None:
    await emit_event(
        db, cycle_id, "MARKET_ANALYSIS",
        {"vol_condition": vol_cond, "trend_condition": trend_cond, **payload},
        underlying=underlying,
    )


async def emit_strategy_selection(
    db, cycle_id: str, underlying: str, strategy: str, payload: dict
) -> None:
    await emit_event(
        db, cycle_id, "STRATEGY_SELECTION",
        {"strategy": strategy, **payload},
        underlying=underlying,
    )


async def emit_opportunity_evaluation(
    db,
    cycle_id: str,
    underlying: str,
    score: int,
    outcome: str,
    checks: list,
) -> None:
    checks_payload = []
    for c in checks:
        if hasattr(c, "__dict__"):
            checks_payload.append(c.__dict__)
        elif hasattr(c, "__dataclass_fields__"):
            checks_payload.append(asdict(c))
        else:
            checks_payload.append(c)
    await emit_event(
        db, cycle_id, "OPPORTUNITY_EVALUATION",
        {"score": score, "outcome": outcome, "checks": checks_payload},
        underlying=underlying,
    )


async def emit_risk_review(
    db, cycle_id: str, underlying: str, approved: bool, reason: str
) -> None:
    await emit_event(
        db, cycle_id, "RISK_REVIEW",
        {"approved": approved, "reason": reason},
        underlying=underlying,
    )


async def emit_final_decision(
    db,
    cycle_id: str,
    underlying: str,
    outcome: str,
    order_id: Optional[str] = None,
) -> None:
    await emit_event(
        db, cycle_id, "FINAL_DECISION",
        {"outcome": outcome, "order_id": order_id},
        underlying=underlying,
    )
