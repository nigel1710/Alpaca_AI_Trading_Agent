"""Strategy selection matrix: maps (volatility, trend) → structure type."""

STRATEGY_MATRIX: dict[tuple[str, str], str] = {
    ("ELEVATED", "UP"): "BULL_PUT",
    ("ELEVATED", "DOWN"): "BEAR_CALL",
    ("ELEVATED", "RANGE"): "IRON_CONDOR",
    ("DEPRESSED", "UP"): "STAND_ASIDE",
    ("DEPRESSED", "DOWN"): "STAND_ASIDE",
    ("DEPRESSED", "RANGE"): "STAND_ASIDE",
}


def select_strategy(volatility_condition: str, trend_condition: str) -> str:
    return STRATEGY_MATRIX.get((volatility_condition, trend_condition), "STAND_ASIDE")
