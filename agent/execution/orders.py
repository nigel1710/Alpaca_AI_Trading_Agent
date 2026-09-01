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

    if strategy in ("BULL_CALL_DEBIT", "BEAR_PUT_DEBIT"):
        # Debit spread: buy the near-the-money leg, sell the further-out leg.
        legs.append({
            "symbol": structure["long_symbol"],
            "side": "buy",
            "ratio_qty": "1",
            "position_intent": "buy_to_open",
        })
        legs.append({
            "symbol": structure["short_symbol"],
            "side": "sell",
            "ratio_qty": "1",
            "position_intent": "sell_to_open",
        })
    elif strategy in ("BULL_PUT", "BEAR_CALL"):
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

    stype = structure.get("strategy_type", "CREDIT")
    is_debit = stype == "DEBIT"
    credit = structure.get("credit", 0.0)
    debit = structure.get("debit", 0.0)
    spread_width = structure.get("spread_width", 0.0)

    legs = _build_legs(structure, strategy)

    # Alpaca takes a positive net limit price; the leg sides determine whether
    # it is paid or received.
    limit_price = debit if is_debit else credit

    result = await client.place_mleg_order(
        legs=legs,
        limit_price=round(limit_price, 2),
        qty=qty,
        client_order_id=client_order_id,
    )

    # Increment circuit breaker counter
    await increment_attempts(db)

    alpaca_order_id = result.get("id")
    max_loss = structure.get("max_loss", 0.0)
    dte = structure.get("dte", 0)

    if is_debit:
        # For a debit spread these levels are the value the spread must reach
        # (profit) or fall to (stop) when sold back — see monitor.py.
        max_gain_per_share = max(spread_width - debit, 0.0)
        profit_target = debit + settings.DEBIT_PROFIT_CAPTURE * max_gain_per_share
        stop_loss_level = debit * (1 - settings.DEBIT_STOP_LOSS_PCT)
    else:
        profit_target = credit * (1 - settings.PROFIT_TARGET)
        stop_loss_level = credit * settings.STOP_LOSS_MULTIPLE

    await storage.insert_position(
        underlying=underlying,
        strategy=strategy,
        short_symbol=structure.get("short_symbol", ""),
        long_symbol=structure.get("long_symbol", ""),
        qty=qty,
        credit_received=credit,
        spread_width=spread_width,
        max_loss=max_loss,
        profit_target=profit_target,
        stop_loss_level=stop_loss_level,
        expiry=expiry,
        dte_at_entry=dte,
        client_order_id=client_order_id,
        alpaca_order_id=alpaca_order_id,
        strategy_type=stype,
        debit_paid=debit if is_debit else None,
        max_reward=structure.get("max_reward"),
    )

    logger.info(
        "Placed %s order for %s | %s=%.4f | client_id=%s | alpaca_id=%s",
        strategy, underlying, "debit" if is_debit else "credit",
        limit_price, client_order_id, alpaca_order_id,
    )
    return result


async def close_spread_order(
    client: AlpacaClient,
    db,
    position: dict,
    reason: str,
    pnl: Optional[float] = None,
) -> dict:
    """Close an open position by trading out of the spread."""
    client_order_id = position.get("client_order_id", "")
    short_symbol = position.get("short_symbol", "")

    # Build closing legs (reverse of entry)
    strategy = position.get("strategy", "")
    legs = []
    if strategy in ("BULL_CALL_DEBIT", "BEAR_PUT_DEBIT"):
        # Entry bought the long leg and sold the short leg — reverse both.
        legs.append({
            "symbol": position["long_symbol"],
            "side": "sell",
            "ratio_qty": "1",
            "position_intent": "sell_to_close",
        })
        legs.append({
            "symbol": position["short_symbol"],
            "side": "buy",
            "ratio_qty": "1",
            "position_intent": "buy_to_close",
        })
    elif strategy in ("BULL_PUT", "BEAR_CALL"):
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
        pnl=pnl,
        reason=reason,
    )

    logger.info("Closed position %s | reason=%s", client_order_id, reason)
    return result
