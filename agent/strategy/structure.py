"""Strike, expiry, and structure selection for each strategy type."""

from datetime import date, datetime
from typing import Optional

from agent.strategy.matrix import strategy_type
from config import settings


def _parse_expiry(expiry_str: str) -> date:
    return datetime.strptime(expiry_str, "%Y-%m-%d").date()


def _compute_dte(expiry_str: str) -> int:
    return (_parse_expiry(expiry_str) - date.today()).days


def _mid(bid: float, ask: float) -> float:
    """Mid price, falling back to whichever side is quoted."""
    bid = bid or 0.0
    ask = ask or 0.0
    if bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    return max(bid, ask)


def select_expiry(chain: list[dict], strategy: str = "") -> Optional[str]:
    """Pick the expiry closest to the target DTE for this strategy type.

    Credit spreads sell short-dated premium (DTE_MIN..DTE_MAX) and honour
    EXPIRY_CUTOFF. Debit spreads need time for the directional thesis to play
    out (DEBIT_DTE_MIN..DEBIT_DTE_MAX, doc §9) and deliberately do NOT apply
    EXPIRY_CUTOFF — a 21-45 DTE window cannot coexist with a cutoff days away.
    """
    if strategy_type(strategy) == "DEBIT":
        dte_min, dte_max = settings.DEBIT_DTE_MIN, settings.DEBIT_DTE_MAX
        target_dte: float = settings.DEBIT_DTE_TARGET
        cutoff = None
    else:
        dte_min, dte_max = settings.DTE_MIN, settings.DTE_MAX
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
        if cutoff is not None and exp_date >= cutoff:
            continue
        dte = (exp_date - today).days
        if dte_min <= dte <= dte_max:
            valid_expiries[exp_str] = dte

    if not valid_expiries:
        return None

    return min(valid_expiries, key=lambda e: abs(valid_expiries[e] - target_dte))


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
        "strategy_type": "CREDIT",
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
        "strategy_type": "CREDIT",
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
        "strategy_type": "CREDIT",
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


def build_debit_candidates(
    strategy: str,
    chain: list[dict],
    current_price: float,
    expiry: str,
) -> list[dict]:
    """Generate every viable debit-spread candidate for this expiry (doc §17).

    Rather than committing to a single strike pair, this enumerates the
    long/short combinations inside the configured delta bands so the caller
    can score and rank them.

    BULL_CALL_DEBIT: buy the lower-strike call, sell the higher-strike call.
    BEAR_PUT_DEBIT:  buy the higher-strike put, sell the lower-strike put.
    """
    is_call = strategy == "BULL_CALL_DEBIT"
    opt_type = "call" if is_call else "put"

    legs = [
        c for c in chain
        if c.get("option_type") == opt_type
        and c.get("expiry") == expiry
        and c.get("delta") is not None
    ]
    if not legs:
        return []

    longs = [
        c for c in legs
        if settings.DEBIT_LONG_DELTA_MIN
        <= abs(c.get("delta", 0.0))
        <= settings.DEBIT_LONG_DELTA_MAX
    ]
    shorts = [
        c for c in legs
        if settings.DEBIT_SHORT_DELTA_MIN
        <= abs(c.get("delta", 0.0))
        <= settings.DEBIT_SHORT_DELTA_MAX
    ]
    if not longs or not shorts:
        return []

    candidates: list[dict] = []
    for long_leg in longs:
        for short_leg in shorts:
            long_strike = long_leg["strike"]
            short_strike = short_leg["strike"]

            # The short leg must sit further out-of-the-money than the long.
            if is_call and short_strike <= long_strike:
                continue
            if not is_call and short_strike >= long_strike:
                continue

            width = abs(short_strike - long_strike)
            if width <= 0:
                continue

            long_bid = long_leg.get("bid", 0.0) or 0.0
            long_ask = long_leg.get("ask", 0.0) or 0.0
            short_bid = short_leg.get("bid", 0.0) or 0.0
            short_ask = short_leg.get("ask", 0.0) or 0.0

            debit = _mid(long_bid, long_ask) - _mid(short_bid, short_ask)
            # A non-positive debit is not a debit spread — skip rather than
            # silently clamping, which would fabricate a free option.
            if debit <= 0:
                continue
            # Paying at or above the width guarantees a loss at expiry.
            if debit >= width:
                continue

            max_loss = debit * 100.0
            max_reward = (width - debit) * 100.0
            reward_risk = max_reward / max_loss if max_loss > 0 else 0.0

            if is_call:
                breakeven = long_strike + debit
                required_move = (breakeven - current_price) / current_price
            else:
                breakeven = long_strike - debit
                required_move = (current_price - breakeven) / current_price

            candidates.append({
                "strategy": strategy,
                "strategy_type": "DEBIT",
                "long_strike": long_strike,
                "short_strike": short_strike,
                "long_symbol": long_leg["symbol"],
                "short_symbol": short_leg["symbol"],
                "long_delta": abs(long_leg.get("delta", 0.0)),
                "short_delta": abs(short_leg.get("delta", 0.0)),
                "long_bid": long_bid,
                "long_ask": long_ask,
                "short_bid": short_bid,
                "short_ask": short_ask,
                "long_oi": long_leg.get("open_interest", 0),
                "short_oi": short_leg.get("open_interest", 0),
                "debit": round(debit, 4),
                "credit": 0.0,
                "spread_width": round(width, 2),
                "max_loss": round(max_loss, 2),
                "max_reward": round(max_reward, 2),
                "reward_risk": round(reward_risk, 4),
                "breakeven": round(breakeven, 4),
                "required_move_pct": round(required_move, 6),
                "expiry": expiry,
                "dte": _compute_dte(expiry),
            })

    return candidates


def build_structure(
    strategy: str, chain: list[dict], current_price: float
) -> Optional[dict]:
    """Dispatch to the correct selector. Returns None for STAND_ASIDE or failures.

    For debit spreads this returns the single best candidate by reward/risk;
    callers wanting the full ranked set should use build_debit_candidates().
    """
    expiry = select_expiry(chain, strategy)
    if expiry is None:
        return None

    if strategy == "BULL_PUT":
        return select_bull_put_spread(chain, current_price, expiry)
    elif strategy == "BEAR_CALL":
        return select_bear_call_spread(chain, current_price, expiry)
    elif strategy == "IRON_CONDOR":
        return select_iron_condor(chain, current_price, expiry)
    elif strategy in ("BULL_CALL_DEBIT", "BEAR_PUT_DEBIT"):
        candidates = build_debit_candidates(strategy, chain, current_price, expiry)
        if not candidates:
            return None
        return max(candidates, key=lambda c: c["reward_risk"])
    return None
