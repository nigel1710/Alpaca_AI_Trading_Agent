"""Rebuild position records from the broker when local state is lost.

The hosted deployment runs on an ephemeral filesystem: a restart or spin-down
wipes the SQLite database while the real positions live on at Alpaca. Without
reconciliation those positions become orphans — the monitor only manages what
is in its own table, so an orphaned spread would run to expiry with no stop
loss, no profit target and no time exit.

This rebuilds the missing rows from what the broker reports. Alpaca gives the
per-leg average entry price, so the net credit/debit is recovered from actual
fills rather than from the limit we originally asked for.
"""

import logging
from datetime import date
from typing import Optional

from agent.perception.alpaca_client import AlpacaClient, _parse_option_symbol
from config import settings
from storage import db as storage

logger = logging.getLogger(__name__)


def _classify(
    option_type: str,
    long_strike: float,
    short_strike: float,
    net: float,
) -> Optional[str]:
    """Name the structure from its legs. `net` > 0 means a credit was taken."""
    is_credit = net > 0
    if option_type == "put":
        if is_credit and short_strike > long_strike:
            return "BULL_PUT"
        if not is_credit and long_strike > short_strike:
            return "BEAR_PUT_DEBIT"
    elif option_type == "call":
        if is_credit and short_strike < long_strike:
            return "BEAR_CALL"
        if not is_credit and long_strike < short_strike:
            return "BULL_CALL_DEBIT"
    return None


async def reconcile_positions(client: AlpacaClient, db) -> list[dict]:
    """Recreate DB rows for broker positions we have no open record of.

    Returns the list of reconciled positions (empty when already in sync).
    """
    try:
        broker_positions = await client.get_positions()
    except Exception as exc:
        logger.error("Reconcile: could not fetch broker positions: %s", exc)
        return []

    option_legs = [
        p for p in broker_positions
        if "OPTION" in str(p.get("asset_class", "")).upper()
    ]
    if not option_legs:
        return []

    known = await storage.get_open_positions_db()
    known_symbols: set[str] = set()
    for row in known:
        known_symbols.add(row.get("short_symbol") or "")
        known_symbols.add(row.get("long_symbol") or "")

    orphans = [p for p in option_legs if p["symbol"] not in known_symbols]
    if not orphans:
        return []

    logger.warning(
        "Reconcile: %d broker option leg(s) have no local record — rebuilding",
        len(orphans),
    )

    # Group into spreads by underlying + expiry + option type.
    groups: dict[tuple, list[dict]] = {}
    for leg in orphans:
        parsed = _parse_option_symbol(leg["symbol"])
        if not parsed:
            logger.warning("Reconcile: could not parse %s — skipping", leg["symbol"])
            continue
        leg = {**leg, **parsed}
        key = (parsed["underlying"], parsed["expiry"], parsed["option_type"])
        groups.setdefault(key, []).append(leg)

    reconciled: list[dict] = []
    for (underlying, expiry, option_type), legs in groups.items():
        longs = [l for l in legs if l["qty"] > 0]
        shorts = [l for l in legs if l["qty"] < 0]
        if not longs or not shorts:
            logger.warning(
                "Reconcile: %s %s %s is not a two-sided spread (%d long, %d short) "
                "— left unmanaged, close it manually",
                underlying, expiry, option_type, len(longs), len(shorts),
            )
            continue

        # Pair one long against one short at a time.
        for long_leg, short_leg in zip(
            sorted(longs, key=lambda x: x["strike"]),
            sorted(shorts, key=lambda x: x["strike"]),
        ):
            long_entry = float(long_leg.get("avg_entry_price") or 0.0)
            short_entry = float(short_leg.get("avg_entry_price") or 0.0)
            net = short_entry - long_entry  # >0 credit taken, <0 debit paid

            strategy = _classify(
                option_type, long_leg["strike"], short_leg["strike"], net
            )
            if strategy is None:
                logger.warning(
                    "Reconcile: could not classify %s %s %s/%s — left unmanaged",
                    underlying, option_type, short_leg["strike"], long_leg["strike"],
                )
                continue

            width = abs(short_leg["strike"] - long_leg["strike"])
            qty = int(min(abs(long_leg["qty"]), abs(short_leg["qty"])))
            is_debit = net < 0
            credit = max(net, 0.0)
            debit = abs(net) if is_debit else 0.0

            if is_debit:
                max_gain = max(width - debit, 0.0)
                profit_target = debit + settings.DEBIT_PROFIT_CAPTURE * max_gain
                stop_level = debit * (1 - settings.DEBIT_STOP_LOSS_PCT)
                max_loss = debit * 100
                max_reward = max_gain * 100
            else:
                profit_target = credit * (1 - settings.PROFIT_TARGET)
                stop_level = credit * settings.STOP_LOSS_MULTIPLE
                max_loss = (width - credit) * 100
                max_reward = credit * 100

            try:
                dte = (date.fromisoformat(expiry) - date.today()).days
            except ValueError:
                dte = 0

            # Deterministic id so repeated reconciliation cannot duplicate rows.
            client_order_id = f"recon-{short_leg['symbol']}"
            if await storage.get_position_by_client_order_id(client_order_id):
                continue

            await storage.insert_position(
                underlying=underlying,
                strategy=strategy,
                short_symbol=short_leg["symbol"],
                long_symbol=long_leg["symbol"],
                qty=qty,
                credit_received=credit,
                spread_width=width,
                max_loss=max_loss,
                profit_target=profit_target,
                stop_loss_level=stop_level,
                expiry=expiry,
                dte_at_entry=dte,
                client_order_id=client_order_id,
                alpaca_order_id=None,
                strategy_type="DEBIT" if is_debit else "CREDIT",
                debit_paid=debit if is_debit else None,
                max_reward=max_reward,
            )

            logger.warning(
                "Reconcile: adopted %s %s %s (%s $%.2f, width $%.2f, %d DTE) — "
                "exit rules now apply again",
                underlying, strategy, expiry,
                "debit" if is_debit else "credit", debit if is_debit else credit,
                width, dte,
            )
            reconciled.append({
                "underlying": underlying,
                "strategy": strategy,
                "expiry": expiry,
                "qty": qty,
            })

    return reconciled
