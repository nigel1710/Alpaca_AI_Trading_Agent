"""Regime-adaptive strategy selection (strategy doc §4, §5).

Maps (volatility regime, trend) → structure type, and explains what was
*not* chosen so the agent can justify standing aside.
"""

from config import settings

# (volatility_regime, trend_condition) → strategy
STRATEGY_MATRIX: dict[tuple[str, str], str] = {
    # Cheap volatility + direction → buy premium (asymmetric reward)
    ("CHEAP", "UP"): "BULL_CALL_DEBIT",
    ("CHEAP", "DOWN"): "BEAR_PUT_DEBIT",
    ("CHEAP", "RANGE"): "STAND_ASIDE",  # no direction to express, premium is cheap
    # Rich volatility + direction → sell premium (high win rate)
    ("RICH", "UP"): "BULL_PUT",
    ("RICH", "DOWN"): "BEAR_CALL",
    ("RICH", "RANGE"): "IRON_CONDOR",
    # FAIR is resolved dynamically in select_strategy() — it requires stronger
    # directional confirmation than the matrix alone can express.
}

DEBIT_STRATEGIES = {"BULL_CALL_DEBIT", "BEAR_PUT_DEBIT"}
CREDIT_STRATEGIES = {"BULL_PUT", "BEAR_CALL", "IRON_CONDOR"}


def strategy_type(strategy: str) -> str:
    """DEBIT, CREDIT, or NONE."""
    if strategy in DEBIT_STRATEGIES:
        return "DEBIT"
    if strategy in CREDIT_STRATEGIES:
        return "CREDIT"
    return "NONE"


def select_strategy(
    volatility_regime: str,
    trend_condition: str,
    trend_separation_pct: float = 0.0,
) -> tuple[str, str]:
    """Select the structure that fits the current regime.

    Returns (strategy, rationale). `rationale` explains the choice — and for
    STAND_ASIDE, why no structure fit — so the agent can surface it.

    FAIR volatility is neither clearly cheap nor clearly rich, so neither
    buying nor selling premium has an edge from volatility alone. Per §5 it
    requires stronger directional confirmation: only a trend meaningfully
    beyond the normal clarity threshold justifies a (directional) debit
    spread; otherwise stand aside.
    """
    if volatility_regime == "FAIR":
        if trend_condition == "RANGE":
            return (
                "STAND_ASIDE",
                "Volatility is FAIR (neither cheap enough to buy nor rich "
                "enough to sell) and the trend is range-bound — no edge in "
                "either direction or in premium.",
            )
        strong_threshold = (
            settings.TREND_CLARITY_THRESHOLD * settings.TREND_STRONG_MULTIPLIER
        )
        if trend_separation_pct >= strong_threshold:
            strategy = (
                "BULL_CALL_DEBIT" if trend_condition == "UP" else "BEAR_PUT_DEBIT"
            )
            return (
                strategy,
                f"Volatility is FAIR, but the {trend_condition} trend is strong "
                f"({trend_separation_pct:.2%} MA separation, above the "
                f"{strong_threshold:.2%} confirmation bar) — taking the "
                f"directional structure with defined risk.",
            )
        return (
            "STAND_ASIDE",
            f"Volatility is FAIR, so premium is fairly priced in both "
            f"directions, and the {trend_condition} trend "
            f"({trend_separation_pct:.2%}) is below the "
            f"{strong_threshold:.2%} confirmation bar required to trade it.",
        )

    strategy = STRATEGY_MATRIX.get((volatility_regime, trend_condition), "STAND_ASIDE")

    if strategy == "STAND_ASIDE":
        if volatility_regime == "CHEAP" and trend_condition == "RANGE":
            return (
                strategy,
                "Volatility is CHEAP (good for buying premium) but there is no "
                "clear direction to express — debit spreads are directional by "
                "construction, so there is nothing to buy.",
            )
        return (
            strategy,
            f"No structure fits volatility={volatility_regime}, "
            f"trend={trend_condition}.",
        )

    if strategy_type(strategy) == "DEBIT":
        rationale = (
            f"Volatility is CHEAP (options inexpensive relative to realized "
            f"movement) and the trend is {trend_condition} — buying a defined-risk "
            f"debit spread gives asymmetric upside."
        )
    else:
        rationale = (
            f"Volatility is RICH (options expensive relative to realized "
            f"movement) and the trend is {trend_condition} — selling premium "
            f"with defined risk is the better-priced side."
        )
    return strategy, rationale


def rejected_alternative(volatility_regime: str, strategy: str) -> str:
    """Explain why the *other* premium side was not chosen (doc §13 'WHY NOT').

    Returns an empty string when no meaningful alternative existed.
    """
    stype = strategy_type(strategy)
    if stype == "DEBIT":
        return (
            f"Volatility is not sufficiently rich (IV/RVol regime "
            f"{volatility_regime}) to justify selling premium via a credit spread."
        )
    if stype == "CREDIT":
        return (
            f"Volatility is not cheap (IV/RVol regime {volatility_regime}); "
            f"buying a debit spread would mean overpaying for the options."
        )
    return ""
