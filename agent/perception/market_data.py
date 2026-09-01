"""Market data retrieval: price bars, option chains, earnings."""

import logging
from datetime import datetime, date, timedelta
from typing import Optional

import pandas as pd

from agent.perception.alpaca_client import AlpacaClient
from config import settings

logger = logging.getLogger(__name__)


async def get_price_bars(
    client: AlpacaClient, symbol: str, days: int = 60
) -> pd.DataFrame:
    """Return DataFrame with columns: date, open, high, low, close, volume."""
    bars = await client.get_bars(symbol, timeframe="1Day", limit=days)
    if not bars:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    df = pd.DataFrame(bars)
    df = df.rename(columns={"t": "date", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


async def get_atm_option_chain(
    client: AlpacaClient,
    underlying: str,
    current_price: float,
    expiry_gte: str,
    expiry_lte: str,
) -> list[dict]:
    """Fetch option chain filtered to ATM +/- 15% strikes, with real open interest."""
    chain = await client.get_option_chain(underlying, expiry_gte, expiry_lte)
    filtered = []
    for contract in chain:
        strike = contract.get("strike")
        if strike is None:
            continue
        moneyness = abs(strike - current_price) / current_price
        if moneyness <= 0.15:
            contract["moneyness"] = round(moneyness, 4)
            filtered.append(contract)

    # Open interest is fetched only for the surviving strike band — pulling it
    # for the whole chain across a 45-day window would be thousands of pages.
    if filtered:
        await client.enrich_open_interest(
            filtered,
            underlying,
            expiry_gte,
            expiry_lte,
            strike_gte=current_price * 0.85,
            strike_lte=current_price * 1.15,
        )
    return filtered


async def get_earnings_dates(symbol: str) -> list[str]:
    """Return upcoming earnings dates using yfinance. Returns [] on failure."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        cal = ticker.calendar
        if cal is None or cal.empty:
            return []
        # calendar may be a DataFrame with 'Earnings Date' in columns or index
        dates = []
        today = date.today()
        cutoff = today + timedelta(days=60)
        if hasattr(cal, "columns") and "Earnings Date" in cal.columns:
            for val in cal["Earnings Date"]:
                try:
                    d = pd.Timestamp(val).date()
                    if today <= d <= cutoff:
                        dates.append(d.isoformat())
                except Exception:
                    pass
        elif hasattr(cal, "index") and "Earnings Date" in cal.index:
            for val in cal.loc["Earnings Date"]:
                try:
                    d = pd.Timestamp(val).date()
                    if today <= d <= cutoff:
                        dates.append(d.isoformat())
                except Exception:
                    pass
        return dates
    except Exception as exc:
        logger.warning(
            "Could not fetch earnings for %s (Check 8 defaults PASS): %s", symbol, exc
        )
        return []
