"""CLI: close all open positions (end-of-window flatten)."""

import asyncio

import click

from agent.execution.orders import close_spread_order
from agent.logging.events import emit_event, new_cycle_id
from agent.perception.alpaca_client import AlpacaClient
from storage.db import init_db, get_db, get_open_positions_db


@click.command("flatten")
@click.option("--confirm", is_flag=True, required=True, help="Confirm you want to close ALL positions")
def flatten(confirm: bool) -> None:
    """Close all open positions (end-of-window flatten). Requires --confirm."""
    asyncio.run(_flatten())


async def _flatten() -> None:
    await init_db()
    db = await get_db()
    client = AlpacaClient()
    cycle_id = new_cycle_id()

    positions = await get_open_positions_db()
    if not positions:
        print("No open positions to close.")
        await client.close()
        return

    print(f"Closing {len(positions)} open position(s)...")

    closed = 0
    errors = 0
    for pos in positions:
        try:
            result = await close_spread_order(client, db, pos, "FLATTEN")
            print(f"  CLOSED: {pos.get('underlying')} {pos.get('strategy')} | {result.get('status')}")
            await emit_event(
                db=db,
                cycle_id=cycle_id,
                stage="FLATTEN",
                payload={
                    "underlying": pos.get("underlying"),
                    "strategy": pos.get("strategy"),
                    "client_order_id": pos.get("client_order_id"),
                    "result": result,
                },
                underlying=pos.get("underlying"),
            )
            closed += 1
        except Exception as exc:
            print(f"  ERROR closing {pos.get('client_order_id')}: {exc}")
            errors += 1

    print(f"\nFlatten complete: {closed} closed, {errors} errors.")
    await client.close()
