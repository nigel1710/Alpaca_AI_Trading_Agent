"""Account and position state from Alpaca."""

from agent.perception.alpaca_client import AlpacaClient


async def get_account_state(client: AlpacaClient) -> dict:
    """Return equity, buying_power, cash, portfolio_value."""
    return await client.get_account()


async def get_open_positions(client: AlpacaClient) -> list[dict]:
    """Return current open positions (all asset classes) from Alpaca."""
    positions = await client.get_positions()
    return positions
