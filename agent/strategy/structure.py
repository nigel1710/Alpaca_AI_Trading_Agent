"""Strike, expiry, and structure selection for each strategy type."""

from datetime import date, datetime
from typing import Optional

from config import settings


def _parse_expiry(expiry_str: str) -> date:
    return datetime.strptime(expiry_str, "%Y-%m-%d").date()


def _compute_dte(expiry_str: str) -> int:
    return (_parse_expiry(expiry_str) - date.today()).days


def select_expiry(chain: list[dict]) -> Optional[str]:
    """Pick expiry closest to midpoint of DTE_MIN..DTE_MAX, subject to EXPIRY_CUTOFF."""
    target_dte = (settings.DTE_MIN + settings.DTE_MAX) / 2
    cutoff = date.fromisoformat(settings.EXPIRY_CUTOFF)
    today = date.today()

    valid_expiries: dict[str, int] = {}
    for contract in chain:
        exp_str = contract.get("expiry")
        if not exp_str:
            continue
        try:
            exp_date = _parse_expiry(exp_str)
        except ValueError:
            continue
        if exp_date >= cutoff:
            continue
        dte = (exp_date - today).days
        if settings.DTE_MIN <= dte <= settings.DTE_MAX:
            valid_expiries[exp_str] = dte

    if not valid_expiries:
        return None

    best = min(valid_expiries, key=lambda e: abs(valid_expiries[e] - target_dte))
    return best


def select_bull_put_spread(
    chain: list[dict], current_price: float, expiry: str
) -> Optional[dict]:
    """Select short put (delta <= DELTA_CEILING) + long put 5 pts below."""
    puts = [
        c for c in chain
        if c.get("option_type") == "put"
        and c.get("expiry") == expiry
        and c.get("delta") is not None
    ]
    if not puts:
        return None

    # Short put: highest strike with abs(delta) <= DELTA_CEILING
    eligible = [p for p in puts if abs(p.get("delta", 1.0)) <= settings.DELTA_CEILING]
    if not eligible:
        return None
    short_put = max(eligible, key=lambda p: p["strike"])

    short_strike = short_put["strike"]
    target_long = short_strike - 5.0

    # Long put: closest available strike below short
    long_candidates = [p for p in puts if p["strike"] < short_strike]
    if not long_candidates:
        return None
    long_put = min(long_candidates, key=lambda p: abs(p["strike"] - target_long))

    spread_width = short_strike - long_put["strike"]
    if spread_width <= 0:
        return None

    short_bid = short_put.get("bid", 0.0) or 0.0
    short_ask = short_put.get("ask", 0.0) or 0.0
    long_bid = long_put.get("bid", 0.0) or 0.0
    long_ask = long_put.get("ask", 0.0) or 0.0

    credit = ((short_bid + short_ask) / 2) - ((long_bid + long_ask) / 2)
    if credit <= 0:
        credit = 0.0

    breakeven = short_strike - credit
    max_loss = (spread_width - credit) * 100

    return {
        "strategy": "BULL_PUT",
        "short_strike": short_strike,
        "long_strike": long_put["strike"],
        "short_symbol": short_put["symbol"],
        "long_symbol": long_put["symbol"],
        "short_delta": abs(short_put.get("delta", 0.0)),
        "long_delta": abs(long_put.get("delta", 0.0)),
        "short_bid": short_bid,
        "short_ask": short_ask,
        "long_bid": long_bid,
        "long_ask": long_ask,
        "short_oi": short_put.get("open_interest", 0),
        "long_oi": long_put.get("open_interest", 0),
        "credit": round(credit, 4),
        "spread_width": round(spread_width, 2),
        "breakeven": round(breakeven, 4),
        "max_loss": round(max_loss, 2),
        "expiry": expiry,
        "dte": _compute_dte(expiry),
    }


def select_bear_call_spread(
    chain: list[dict], current_price: float, expiry: str
) -> Optional[dict]:
    """Select short call (delta <= DELTA_CEILING) + long call 5 pts above."""
    calls = [
        c for c in chain
        if c.get("option_type") == "call"
        and c.get("expiry") == expiry
        and c.get("delta") is not None
    ]
    if not calls:
        return None

    eligible = [c for c in calls if abs(c.get("delta", 1.0)) <= settings.DELTA_CEILING]
    if not eligible:
        return None
    short_call = min(eligible, key=lambda c: c["strike"])

    short_strike = short_call["strike"]
    target_long = short_strike + 5.0

    long_candidates = [c for c in calls if c["strike"] > short_strike]
    if not long_candidates:
        return None
    long_call = min(long_candidates, key=lambda c: abs(c["strike"] - target_long))

    spread_width = long_call["strike"] - short_strike
    if spread_width <= 0:
        return None

    short_bid = short_call.get("bid", 0.0) or 0.0
    short_ask = short_call.get("ask", 0.0) or 0.0
    long_bid = long_call.get("bid", 0.0) or 0.0
    long_ask = long_call.get("ask", 0.0) or 0.0

    credit = ((short_bid + short_ask) / 2) - ((long_bid + long_ask) / 2)
    if credit <= 0:
        credit = 0.0

    breakeven = short_strike + credit
    max_loss = (spread_width - credit) * 100

    return {
        "strategy": "BEAR_CALL",
        "short_strike": short_strike,
        "long_strike": long_call["strike"],
        "short_symbol": short_call["symbol"],
        "long_symbol": long_call["symbol"],
        "short_delta": abs(short_call.get("delta", 0.0)),
        "long_delta": abs(long_call.get("delta", 0.0)),
        "short_bid": short_bid,
        "short_ask": short_ask,
        "long_bid": long_bid,
        "long_ask": long_ask,
        "short_oi": short_call.get("open_interest", 0),
        "long_oi": long_call.get("open_interest", 0),
        "credit": round(credit, 4),
        "spread_width": round(spread_width, 2),
        "breakeven": round(breakeven, 4),
        "max_loss": round(max_loss, 2),
        "expiry": expiry,
        "dte": _compute_dte(expiry),
    }


def select_iron_condor(
    chain: list[dict], current_price: float, expiry: str
) -> Optional[dict]:
    """Combine bull put + bear call into iron condor."""
    put_spread = select_bull_put_spread(chain, current_price, expiry)
    call_spread = select_bear_call_spread(chain, current_price, expiry)

    if put_spread is None or call_spread is None:
        return None

    net_credit = put_spread["credit"] + call_spread["credit"]
    max_loss = max(put_spread["max_loss"], call_spread["max_loss"])  # wider wing dominates

    return {
        "strategy": "IRON_CONDOR",
        # Use put short/long as primary for DB tracking
        "short_strike": put_spread["short_strike"],
        "long_strike": put_spread["long_strike"],
        "short_symbol": put_spread["short_symbol"],
        "long_symbol": put_spread["long_symbol"],
        "call_short_symbol": call_spread["short_symbol"],
        "call_long_symbol": call_spread["long_symbol"],
        "put_short_strike": put_spread["short_strike"],
        "put_long_strike": put_spread["long_strike"],
        "call_short_strike": call_spread["short_strike"],
        "call_long_strike": call_spread["long_strike"],
        "short_delta": put_spread["short_delta"],
        "long_delta": put_spread["long_delta"],
        "short_bid": put_spread["short_bid"],
        "short_ask": put_spread["short_ask"],
        "long_bid": put_spread["long_bid"],
        "long_ask": put_spread["long_ask"],
        "short_oi": min(put_spread["short_oi"], call_spread["short_oi"]),
        "long_oi": min(put_spread["long_oi"], call_spread["long_oi"]),
        "credit": round(net_credit, 4),
        "put_credit": put_spread["credit"],
        "call_credit": call_spread["credit"],
        "spread_width": max(put_spread["spread_width"], call_spread["spread_width"]),
        "breakeven": put_spread["breakeven"],  # lower breakeven
        "breakeven_upper": call_spread["breakeven"],
        "max_loss": round(max_loss, 2),
        "expiry": expiry,
        "dte": _compute_dte(expiry),
    }


def build_structure(
    strategy: str, chain: list[dict], current_price: float
) -> Optional[dict]:
    """Dispatch to the correct selector. Returns None for STAND_ASIDE or failures."""
    expiry = select_expiry(chain)
    if expiry is None:
        return None

    if strategy == "BULL_PUT":
        return select_bull_put_spread(chain, current_price, expiry)
    elif strategy == "BEAR_CALL":
        return select_bear_call_spread(chain, current_price, expiry)
    elif strategy == "IRON_CONDOR":
        return select_iron_condor(chain, current_price, expiry)
    return None
