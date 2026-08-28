"""Trend signal: moving average computation and classification."""

import pandas as pd

from config import settings


def compute_mas(bars: pd.DataFrame) -> tuple[float, float]:
    """Returns (short_ma, long_ma) from close price series."""
    closes = bars["close"]
    short_ma = float(closes.tail(settings.MA_SHORT).mean())
    long_ma = float(closes.tail(settings.MA_LONG).mean())
    return short_ma, long_ma


def classify_trend(
    bars: pd.DataFrame, current_price: float
) -> tuple[str, float, float, float]:
    """Returns (condition, short_ma, long_ma, separation_pct).

    condition: UP, DOWN, or RANGE.
    separation_pct = abs(short_ma - long_ma) / current_price.
    """
    if len(bars) < settings.MA_LONG:
        return "RANGE", 0.0, 0.0, 0.0

    short_ma, long_ma = compute_mas(bars)
    separation_pct = abs(short_ma - long_ma) / current_price if current_price > 0 else 0.0

    if separation_pct <= settings.TREND_CLARITY_THRESHOLD:
        condition = "RANGE"
    elif short_ma > long_ma:
        condition = "UP"
    else:
        condition = "DOWN"

    return condition, round(short_ma, 4), round(long_ma, 4), round(separation_pct, 6)
