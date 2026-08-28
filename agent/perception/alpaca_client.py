"""Thin async wrapper around alpaca-py mirroring MCP tool semantics."""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

import httpx
from alpaca.data import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading import TradingClient
from alpaca.trading.requests import GetOrdersRequest, MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus

try:
    from alpaca.data import OptionHistoricalDataClient
    from alpaca.data.requests import OptionChainRequest, OptionSnapshotRequest
    _HAS_OPTION_CLIENT = True
except ImportError:
    _HAS_OPTION_CLIENT = False

from config import settings

logger = logging.getLogger(__name__)


class AlpacaClient:
    def __init__(self) -> None:
        self._trading = TradingClient(
            api_key=settings.ALPACA_API_KEY,
            secret_key=settings.ALPACA_SECRET_KEY,
            paper=True,
        )
        self._stock_data = StockHistoricalDataClient(
            api_key=settings.ALPACA_API_KEY,
            secret_key=settings.ALPACA_SECRET_KEY,
        )
        if _HAS_OPTION_CLIENT:
            self._option_data = OptionHistoricalDataClient(
                api_key=settings.ALPACA_API_KEY,
                secret_key=settings.ALPACA_SECRET_KEY,
            )
        else:
            self._option_data = None
            logger.warning("OptionHistoricalDataClient not available — options chain will be empty.")

        self._http = httpx.AsyncClient(
            base_url=settings.ALPACA_BASE_URL,
            headers={
                "APCA-API-KEY-ID": settings.ALPACA_API_KEY,
                "APCA-API-SECRET-KEY": settings.ALPACA_SECRET_KEY,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def get_account(self) -> dict:
        acct = await asyncio.to_thread(self._trading.get_account)
        return {
            "equity": float(acct.equity),
            "buying_power": float(acct.buying_power),
            "cash": float(acct.cash),
            "portfolio_value": float(acct.portfolio_value),
            "currency": acct.currency,
        }

    async def get_positions(self) -> list[dict]:
        positions = await asyncio.to_thread(self._trading.get_all_positions)
        result = []
        for p in positions:
            result.append({
                "symbol": p.symbol,
                "qty": float(p.qty),
                "avg_entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price) if p.current_price else None,
                "market_value": float(p.market_value) if p.market_value else None,
                "unrealized_pl": float(p.unrealized_pl) if p.unrealized_pl else None,
                "side": p.side.value if hasattr(p.side, "value") else str(p.side),
                "asset_class": str(p.asset_class),
            })
        return result

    async def get_bars(self, symbol: str, timeframe: str = "1Day", limit: int = 60) -> list[dict]:
        tf = TimeFrame.Day if timeframe == "1Day" else TimeFrame.Hour
        end = datetime.utcnow()
        start = end - timedelta(days=limit + 30)  # extra buffer for weekends/holidays
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=tf,
            start=start,
            end=end,
            limit=limit,
        )
        bars = await asyncio.to_thread(self._stock_data.get_stock_bars, req)
        result = []
        if symbol in bars:
            for b in bars[symbol]:
                result.append({
                    "t": b.timestamp.isoformat(),
                    "o": float(b.open),
                    "h": float(b.high),
                    "l": float(b.low),
                    "c": float(b.close),
                    "v": float(b.volume),
                })
        return result

    async def get_option_chain(
        self,
        underlying: str,
        expiry_date_gte: str,
        expiry_date_lte: str,
    ) -> list[dict]:
        if self._option_data is None:
            return []
        try:
            req = OptionChainRequest(
                underlying_symbol=underlying,
                expiration_date_gte=expiry_date_gte,
                expiration_date_lte=expiry_date_lte,
            )
            chain = await asyncio.to_thread(self._option_data.get_option_chain, req)
            result = []
            for symbol, snap in chain.items():
                contract = {
                    "symbol": symbol,
                    "underlying": underlying,
                }
                if hasattr(snap, "greeks") and snap.greeks:
                    contract["delta"] = snap.greeks.delta
                    contract["gamma"] = snap.greeks.gamma
                    contract["theta"] = snap.greeks.theta
                    contract["vega"] = snap.greeks.vega
                if hasattr(snap, "implied_volatility"):
                    contract["implied_volatility"] = snap.implied_volatility
                if hasattr(snap, "latest_quote") and snap.latest_quote:
                    contract["bid"] = snap.latest_quote.bid_price
                    contract["ask"] = snap.latest_quote.ask_price
                if hasattr(snap, "latest_trade") and snap.latest_trade:
                    contract["last"] = snap.latest_trade.price
                # Parse details from symbol (e.g. SPY240815P00550000)
                parsed = _parse_option_symbol(symbol)
                if parsed:
                    contract.update(parsed)
                # open interest via details endpoint — use 0 as default (fetched in snapshots)
                contract["open_interest"] = 0
                result.append(contract)
            return result
        except Exception as exc:
            logger.warning("get_option_chain failed for %s: %s", underlying, exc)
            return []

    async def get_option_snapshots(self, symbols: list[str]) -> dict[str, dict]:
        if self._option_data is None or not symbols:
            return {}
        try:
            req = OptionSnapshotRequest(symbol_or_symbols=symbols)
            snaps = await asyncio.to_thread(self._option_data.get_option_snapshot, req)
            result = {}
            for sym, snap in snaps.items():
                d: dict = {}
                if hasattr(snap, "greeks") and snap.greeks:
                    d["delta"] = snap.greeks.delta
                    d["gamma"] = snap.greeks.gamma
                    d["theta"] = snap.greeks.theta
                    d["vega"] = snap.greeks.vega
                if hasattr(snap, "implied_volatility"):
                    d["implied_volatility"] = snap.implied_volatility
                if hasattr(snap, "latest_quote") and snap.latest_quote:
                    d["bid"] = snap.latest_quote.bid_price
                    d["ask"] = snap.latest_quote.ask_price
                result[sym] = d
            return result
        except Exception as exc:
            logger.warning("get_option_snapshots failed: %s", exc)
            return {}

    async def place_mleg_order(
        self,
        legs: list[dict],
        limit_price: float,
        qty: int,
        client_order_id: str,
    ) -> dict:
        payload = {
            "type": "limit",
            "time_in_force": "day",
            "order_class": "mleg",
            "limit_price": str(round(limit_price, 2)),
            "qty": str(qty),
            "client_order_id": client_order_id,
            "legs": legs,
        }
        if settings.DRY_RUN:
            fake_id = f"dry-run-{uuid.uuid4().hex[:8]}"
            logger.info("[DRY RUN] Would place mleg order: %s", payload)
            return {"id": fake_id, "status": "pending_new", "client_order_id": client_order_id}

        resp = await self._http.post("/v2/orders", json=payload)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Order placement failed {resp.status_code}: {resp.text}")
        return resp.json()

    async def get_orders(self, status: str = "open") -> list[dict]:
        status_enum = QueryOrderStatus.OPEN if status == "open" else QueryOrderStatus.CLOSED
        req = GetOrdersRequest(status=status_enum)
        orders = await asyncio.to_thread(self._trading.get_orders, req)
        return [
            {
                "id": str(o.id),
                "client_order_id": o.client_order_id,
                "symbol": o.symbol,
                "status": str(o.status),
                "qty": float(o.qty) if o.qty else None,
                "filled_qty": float(o.filled_qty) if o.filled_qty else None,
                "limit_price": float(o.limit_price) if o.limit_price else None,
            }
            for o in orders
        ]

    async def close_position(self, symbol: str, client_order_id: str) -> dict:
        if settings.DRY_RUN:
            fake_id = f"dry-run-close-{uuid.uuid4().hex[:8]}"
            logger.info("[DRY RUN] Would close position %s", symbol)
            return {"id": fake_id, "status": "pending_new", "client_order_id": client_order_id}
        resp = await self._http.delete(f"/v2/positions/{symbol}")
        if resp.status_code not in (200, 204):
            raise RuntimeError(f"Close position failed {resp.status_code}: {resp.text}")
        return resp.json() if resp.text else {}

    async def get_latest_quote(self, symbol: str) -> dict:
        try:
            from alpaca.data.requests import OptionLatestQuoteRequest
            req = OptionLatestQuoteRequest(symbol_or_symbols=symbol)
            quotes = await asyncio.to_thread(self._option_data.get_option_latest_quote, req)
            if symbol in quotes:
                q = quotes[symbol]
                return {"bid": float(q.bid_price), "ask": float(q.ask_price), "symbol": symbol}
        except Exception as exc:
            logger.debug("get_latest_quote fallback for %s: %s", symbol, exc)
        return {"bid": 0.0, "ask": 0.0, "symbol": symbol}

    async def close(self) -> None:
        await self._http.aclose()


def _parse_option_symbol(symbol: str) -> Optional[dict]:
    """Parse OCC option symbol: UNDERLYING + YYMMDD + C/P + STRIKE*1000"""
    import re
    m = re.match(r"^([A-Z]+)(\d{6})([CP])(\d{8})$", symbol)
    if not m:
        return None
    underlying, date_str, opt_type, strike_str = m.groups()
    expiry = f"20{date_str[:2]}-{date_str[2:4]}-{date_str[4:]}"
    strike = int(strike_str) / 1000.0
    return {
        "underlying": underlying,
        "expiry": expiry,
        "option_type": "put" if opt_type == "P" else "call",
        "strike": strike,
    }
