"""Order placement with idempotency and circuit breaker integration."""

import hashlib
import logging
from datetime import date
from typing import Optional

from agent.execution.circuit_breaker import check_circuit_breaker, increment_attempts
from agent.perception.alpaca_client import AlpacaClient
from config import settings
from storage import db as storage

logger = logging.getLogger(__name__)


def make_client_order_id(
    underlying: str, strategy: str, expiry: str, short_strike: float
) -> str:
    """Deterministic client order ID — same inputs on same day produce same ID."""
    key = f"{underlying}:{strategy}:{expiry}:{short_strike}:{date.today().isoformat()}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _build_legs(structure: dict, strategy: str) -> list[dict]:
    """Build the legs list for the mleg order payload."""
    legs = []

    if strategy in ("BULL_PUT", "BEAR_CALL"):
        legs.append({
            "symbol": structure["short_symbol"],
            "side": "sell",
            "ratio_qty": "1",
            "position_intent": "sell_to_open",
        })
        legs.append({
            "symbol": structure["long_symbol"],
            "side": "buy",
            "ratio_qty": "1",
            "position_intent": "buy_to_open",
        })
    elif strategy == "IRON_CONDOR":
        legs.append({
            "symbol": structure["short_symbol"],  # put short
            "side": "sell",
            "ratio_qty": "1",
            "position_intent": "sell_to_open",
        })
        legs.append({
            "symbol": structure["long_symbol"],  # put long
            "side": "buy",
            "ratio_qty": "1",
            "position_intent": "buy_to_open",
        })
        legs.append({
            "symbol": structure["call_short_symbol"],
            "side": "sell",
            "ratio_qty": "1",
            "position_intent": "sell_to_open",
        })
        legs.append({
            "symbol": structure["call_long_symbol"],
            "side": "buy",
            "ratio_qty": "1",
            "position_intent": "buy_to_open",
        })

    return legs


async def place_spread_order(
    client: AlpacaClient,
    db,
    structure: dict,
    strategy: str,
    underlying: str,
    qty: int,
    decision_id: int,
) -> dict:
    """Place a spread order with idempotency and circuit breaker checks."""
    short_strike = structure.get("short_strike", 0.0)
    expiry = structure.get("expiry", "")
    client_order_id = make_client_order_id(underlying, strategy, expiry, short_strike)

    # Idempotency: check if we already placed this order today
    existing = await storage.get_position_by_client_order_id(client_order_id)
    if existing is not None:
        logger.info(
            "Order %s already exists (idempotent) — skipping duplicate submission",
            client_order_id,
        )
        return {"id": existing.get("alpaca_order_id", ""), "status": "already_placed", "client_order_id": client_order_id}

    # Circuit breaker check
    # Equity is checked at cycle level; here we just check attempts
    account = await client.get_account()
    halted, halt_reason = await check_circuit_breaker(db, account["equity"])
    if halted:
        raise RuntimeError(f"Circuit breaker active: {halt_reason}")

    credit = structure.get("credit", 0.0)
    legs = _build_legs(structure, strategy)

    result = await client.place_mleg_order(
        legs=legs,
        limit_price=round(credit, 2),
        qty=qty,
        client_order_id=client_order_id,
    )

    # Increment circuit breaker counter
    await increment_attempts(db)

    alpaca_order_id = result.get("id")
    credit_received = credit
    spread_width = structure.get("spread_width", 0.0)
    max_loss = structure.get("max_loss", 0.0)
    profit_target = credit_received * (1 - settings.PROFIT_TARGET)
    stop_loss_level = credit_received * settings.STOP_LOSS_MULTIPLE
    dte = structure.get("dte", 0)

    await storage.insert_position(
        underlying=underlying,
        strategy=strategy,
        short_symbol=structure.get("short_symbol", ""),
        long_symbol=structure.get("long_symbol", ""),
        qty=qty,
        credit_received=credit_received,
        spread_width=spread_width,
        max_loss=max_loss,
        profit_target=profit_target,
        stop_loss_level=stop_loss_level,
        expiry=expiry,
        dte_at_entry=dte,
        client_order_id=client_order_id,
        alpaca_order_id=alpaca_order_id,
    )

    logger.info(
        "Placed %s order for %s | credit=%.4f | client_id=%s | alpaca_id=%s",
        strategy, underlying, credit_received, client_order_id, alpaca_order_id,
    )
    return result


async def close_spread_order(
    client: AlpacaClient,
    db,
    position: dict,
    reason: str,
) -> dict:
    """Close an open position by buying back the spread."""
    client_order_id = position.get("client_order_id", "")
    short_symbol = position.get("short_symbol", "")

    # Build closing legs (reverse of entry)
    strategy = position.get("strategy", "")
    legs = []
    if strategy in ("BULL_PUT", "BEAR_CALL"):
        legs.append({
            "symbol": position["short_symbol"],
            "side": "buy",
            "ratio_qty": "1",
            "position_intent": "buy_to_close",
        })
        legs.append({
            "symbol": position["long_symbol"],
            "side": "sell",
            "ratio_qty": "1",
            "position_intent": "sell_to_close",
        })
    elif strategy == "IRON_CONDOR":
        legs.append({"symbol": position["short_symbol"], "side": "buy", "ratio_qty": "1", "position_intent": "buy_to_close"})
        legs.append({"symbol": position["long_symbol"], "side": "sell", "ratio_qty": "1", "position_intent": "sell_to_close"})
        # Iron condor second spread if present
        if position.get("call_short_symbol"):
            legs.append({"symbol": position["call_short_symbol"], "side": "buy", "ratio_qty": "1", "position_intent": "buy_to_close"})
            legs.append({"symbol": position["call_long_symbol"], "side": "sell", "ratio_qty": "1", "position_intent": "sell_to_close"})

    close_client_id = f"close-{client_order_id[:12]}"

    try:
        result = await client.place_mleg_order(
            legs=legs,
            limit_price=0.05,  # small debit to close; will be market-ish
            qty=position.get("qty", 1),
            client_order_id=close_client_id,
        )
    except Exception as exc:
        logger.error("Failed to close position %s: %s", client_order_id, exc)
        result = {"id": None, "status": "error", "error": str(exc)}

    # Map reason to state
    state_map = {
        "PROFIT": "CLOSED_PROFIT",
        "STOP": "CLOSED_STOP",
        "TIME": "CLOSED_TIME",
        "FLATTEN": "CLOSED_FLATTEN",
        "MANUAL": "CLOSED_MANUAL",
    }
    state = state_map.get(reason.upper(), "CLOSED_MANUAL")

    await storage.update_position_state(
        client_order_id=client_order_id,
        state=state,
        reason=reason,
    )

    logger.info("Closed position %s | reason=%s", client_order_id, reason)
    return result
