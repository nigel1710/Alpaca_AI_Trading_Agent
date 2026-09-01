"""CLI: run one full scan cycle."""

import asyncio

import click

from agent.main import run_one_cycle
from storage.db import close_db, get_db, init_db
from agent.perception.alpaca_client import AlpacaClient


@click.command("scan")
@click.option("--verbose/--no-verbose", default=True, help="Print each pipeline stage")
def scan(verbose: bool) -> None:
    """Run one full scan cycle end to end, printing each pipeline stage."""
    asyncio.run(_scan(verbose))


async def _scan(verbose: bool) -> None:
    await init_db()
    db = await get_db()
    client = AlpacaClient()
    try:
        await run_one_cycle(db=db, client=client, verbose=verbose)
    finally:
        await client.close()
        await close_db()
