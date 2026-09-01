"""Monitor open positions against exit rules: profit target, stop, time."""

import logging
from datetime import date, datetime
from typing import Optional

from agent.execution.orders import close_spread_order
from agent.perception.alpaca_client import AlpacaClient
from config import settings

logger = logging.getLogger(__name__)


def compute_spread_dte(expiry: str) -> int:
    """Calendar days to expiry from today."""
    try:
        exp_date = date.fromisoformat(expiry)
        return (exp_date - date.today()).days
    except ValueError:
        return 999


async def get_spread_current_value(
    client: AlpacaClient,
    position: dict,
) -> Optional[float]:
    """Current value of the spread, priced the way it would actually be closed.

    CREDIT spread — closed by BUYING it back, so the relevant number is the
    cost to close: pay the ask on the short leg, receive the bid on the long.
    Lower is better.

    DEBIT spread — closed by SELLING it, so the relevant number is the
    proceeds: receive the bid on the long leg, pay the ask on the short.
    Higher is better.

    Returns None if data is unavailable.
    """
    try:
        short_sym = position.get("short_symbol", "")
        long_sym = position.get("long_symbol", "")

        short_quote = await client.get_latest_quote(short_sym)
        long_quote = await client.get_latest_quote(long_sym)

        short_ask = short_quote.get("ask", 0.0) or 0.0
        short_bid = short_quote.get("bid", 0.0) or 0.0
        long_bid = long_quote.get("bid", 0.0) or 0.0
        long_ask = long_quote.get("ask", 0.0) or 0.0

        if position.get("strategy_type") == "DEBIT":
            # Proceeds from selling the spread back.
            return max(long_bid - short_ask, 0.0)

        # Cost to buy the credit spread back.
        return max(short_ask - long_bid, 0.0)
    except Exception as exc:
        logger.warning("Could not get spread value for %s: %s", position.get("short_symbol"), exc)
        return None


def _evaluate_debit_exit(position: dict, current_value: float) -> Optional[tuple[str, float]]:
    """Exit rules for a debit spread. Returns (reason, pnl) or None to hold.

    Profit: the spread has gained enough of its maximum achievable move.
    Stop:   the spread has lost DEBIT_STOP_LOSS_PCT of the premium paid.
    """
    debit_paid = position.get("debit_paid") or 0.0
    if debit_paid <= 0:
        return None

    qty = position.get("qty", 1)
    spread_width = position.get("spread_width") or 0.0

    # Max the spread can ever be worth is the width; profit target captures a
    # fraction of the distance from what we paid up to that ceiling.
    max_gain_per_share = max(spread_width - debit_paid, 0.0)
    profit_threshold = debit_paid + settings.DEBIT_PROFIT_CAPTURE * max_gain_per_share
    stop_threshold = debit_paid * (1.0 - settings.DEBIT_STOP_LOSS_PCT)

    pnl = (current_value - debit_paid) * 100 * qty

    if max_gain_per_share > 0 and current_value >= profit_threshold:
        return "PROFIT", pnl
    if current_value <= stop_threshold:
        return "STOP", pnl
    return None


async def monitor_open_positions(
    client: AlpacaClient,
    db,
    open_positions: list[dict],
) -> list[dict]:
    """Check each open position against exit rules and close if triggered."""
    closed = []

    for pos in open_positions:
        try:
            client_order_id = pos.get("client_order_id", "")
            credit_received = pos.get("credit_received", 0.0)
            expiry = pos.get("expiry", "")

            is_debit = pos.get("strategy_type") == "DEBIT"
            dte = compute_spread_dte(expiry)

            # Time-based exit. Debit spreads exit earlier: theta works against
            # a long premium position, so holding to 1 DTE bleeds value.
            time_exit_dte = (
                settings.DEBIT_TIME_EXIT_DTE if is_debit else settings.TIME_EXIT_DTE
            )
            if dte <= time_exit_dte:
                logger.info(
                    "TIME EXIT: position %s at %d DTE", client_order_id, dte
                )
                result = await close_spread_order(client, db, pos, "TIME")
                pos["close_reason"] = "TIME"
                pos["close_result"] = result
                closed.append(pos)
                continue

            current_value = await get_spread_current_value(client, pos)
            if current_value is None:
                continue

            if is_debit:
                decision = _evaluate_debit_exit(pos, current_value)
                if decision is not None:
                    reason, pnl = decision
                    logger.info(
                        "%s (DEBIT): position %s current=%.4f paid=%.4f",
                        reason, client_order_id, current_value,
                        pos.get("debit_paid") or 0.0,
                    )
                    result = await close_spread_order(client, db, pos, reason, pnl=pnl)
                    pos["close_reason"] = reason
                    pos["close_pnl"] = pnl
                    pos["close_result"] = result
                    closed.append(pos)
                continue

            # Profit target: current cost <= credit * (1 - PROFIT_TARGET)
            profit_threshold = credit_received * (1.0 - settings.PROFIT_TARGET)
            if current_value <= profit_threshold:
                logger.info(
                    "PROFIT TARGET: position %s current=%.4f target=%.4f",
                    client_order_id, current_value, profit_threshold,
                )
                pnl = (credit_received - current_value) * 100 * pos.get("qty", 1)
                result = await close_spread_order(client, db, pos, "PROFIT", pnl=pnl)
                pos["close_reason"] = "PROFIT"
                pos["close_pnl"] = pnl
                pos["close_result"] = result
                closed.append(pos)
                continue

            # Stop loss: current cost >= credit * STOP_LOSS_MULTIPLE
            stop_threshold = credit_received * settings.STOP_LOSS_MULTIPLE
            if current_value >= stop_threshold:
                logger.info(
                    "STOP LOSS: position %s current=%.4f stop=%.4f",
                    client_order_id, current_value, stop_threshold,
                )
                pnl = (credit_received - current_value) * 100 * pos.get("qty", 1)
                result = await close_spread_order(client, db, pos, "STOP", pnl=pnl)
                pos["close_reason"] = "STOP"
                pos["close_pnl"] = pnl
                pos["close_result"] = result
                closed.append(pos)

        except Exception as exc:
            logger.error(
                "Error monitoring position %s: %s",
                pos.get("client_order_id", "?"), exc,
            )

    return closed
