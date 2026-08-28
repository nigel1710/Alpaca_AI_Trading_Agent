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
    """Get current mark value of spread (short leg mark - long leg mark).

    For a credit spread: current cost to close = short ask - long bid.
    Returns None if data unavailable.
    """
    try:
        short_sym = position.get("short_symbol", "")
        long_sym = position.get("long_symbol", "")

        short_quote = await client.get_latest_quote(short_sym)
        long_quote = await client.get_latest_quote(long_sym)

        # Cost to buy back: pay ask on short, receive bid on long
        short_ask = short_quote.get("ask", 0.0) or 0.0
        long_bid = long_quote.get("bid", 0.0) or 0.0

        current_value = short_ask - long_bid
        return max(current_value, 0.0)
    except Exception as exc:
        logger.warning("Could not get spread value for %s: %s", position.get("short_symbol"), exc)
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

            dte = compute_spread_dte(expiry)

            # Time-based exit: close at 1 DTE
            if dte <= settings.TIME_EXIT_DTE:
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

            # Profit target: current cost <= credit * (1 - PROFIT_TARGET)
            profit_threshold = credit_received * (1.0 - settings.PROFIT_TARGET)
            if current_value <= profit_threshold:
                logger.info(
                    "PROFIT TARGET: position %s current=%.4f target=%.4f",
                    client_order_id, current_value, profit_threshold,
                )
                pnl = (credit_received - current_value) * 100 * pos.get("qty", 1)
                result = await close_spread_order(client, db, pos, "PROFIT")
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
                result = await close_spread_order(client, db, pos, "STOP")
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
