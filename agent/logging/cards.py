"""Decision card dataclass and builder."""

import json
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class DecisionCard:
    underlying: str
    ts: str
    cycle_id: str
    volatility_condition: str
    trend_condition: str
    selected_strategy: str
    opportunity_score: int
    checks: list
    outcome: str
    reject_reason: Optional[str]
    risk_gate_result: Optional[str]
    risk_gate_reason: Optional[str]
    credit_received: Optional[float]
    spread_width: Optional[float]
    breakeven: Optional[float]
    max_loss: Optional[float]
    dte: Optional[int]
    short_strike: Optional[float]
    long_strike: Optional[float]
    expiry: Optional[str]
    short_symbol: Optional[str]
    long_symbol: Optional[str]
    order_id: Optional[str]


def build_card(decision_row: dict) -> DecisionCard:
    """Construct a DecisionCard from a DB decisions row."""
    checks_raw = decision_row.get("checks_json")
    checks = json.loads(checks_raw) if checks_raw else []

    return DecisionCard(
        underlying=decision_row.get("underlying", ""),
        ts=decision_row.get("ts", ""),
        cycle_id=decision_row.get("cycle_id", ""),
        volatility_condition=decision_row.get("volatility_condition") or "",
        trend_condition=decision_row.get("trend_condition") or "",
        selected_strategy=decision_row.get("selected_strategy") or "",
        opportunity_score=decision_row.get("opportunity_score") or 0,
        checks=checks,
        outcome=decision_row.get("outcome", "REJECT"),
        reject_reason=decision_row.get("reject_reason"),
        risk_gate_result=decision_row.get("risk_gate_result"),
        risk_gate_reason=decision_row.get("risk_gate_reason"),
        credit_received=decision_row.get("credit_received"),
        spread_width=decision_row.get("spread_width"),
        breakeven=decision_row.get("breakeven"),
        max_loss=decision_row.get("max_loss"),
        dte=decision_row.get("dte"),
        short_strike=decision_row.get("short_strike"),
        long_strike=decision_row.get("long_strike"),
        expiry=decision_row.get("expiry"),
        short_symbol=decision_row.get("short_symbol"),
        long_symbol=decision_row.get("long_symbol"),
        order_id=decision_row.get("order_id"),
    )


def card_to_dict(card: DecisionCard) -> dict:
    return asdict(card)
