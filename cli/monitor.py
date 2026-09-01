"""CLI: check open positions against exit rules, without scanning for entries.

Kept separate from `scan` on purpose (strategy doc §14) so open risk can be
monitored on a faster or more reliable cadence than opportunity scanning.
"""

import asyncio

import click

from agent.main import run_position_monitor
from agent.perception.alpaca_client import AlpacaClient
from storage.db import close_db, get_db, init_db


@click.command("monitor")
@click.option("--verbose/--no-verbose", default=True, help="Print each exit taken")
def monitor(verbose: bool) -> None:
    """Monitor open positions and close any that hit an exit rule."""
    asyncio.run(_monitor(verbose))


async def _monitor(verbose: bool) -> None:
    await init_db()
    db = await get_db()
    client = AlpacaClient()
    try:
        closed = await run_position_monitor(db, client, verbose=verbose)
        if not closed:
            click.echo("No positions closed — all open positions within exit rules.")
        else:
            click.echo(f"Closed {len(closed)} position(s).")
    finally:
        await client.close()
        await close_db()
