"""Volatility signal: realized vol, IV classification, IV stability."""

import math
from typing import Optional

import numpy as np
import pandas as pd

from config import settings


def compute_realized_vol(bars: pd.DataFrame, window: int = 20) -> float:
    """Annualized realized volatility from daily log returns (last `window` bars)."""
    if len(bars) < window + 1:
        return 0.0
    closes = bars["close"].values[-(window + 1):]
    log_returns = np.diff(np.log(closes))
    daily_vol = float(np.std(log_returns, ddof=1))
    return daily_vol * math.sqrt(252)


def classify_volatility(atm_iv: float, realized_vol: float) -> tuple[str, float]:
    """Returns (condition, ratio). ELEVATED if atm_iv >= IV_RICH_MULTIPLIER * realized_vol."""
    if realized_vol <= 0:
        return "DEPRESSED", 0.0
    ratio = atm_iv / realized_vol
    condition = "ELEVATED" if ratio >= settings.IV_RICH_MULTIPLIER else "DEPRESSED"
    return condition, round(ratio, 4)


def is_iv_stable(current_iv: float, recent_ivs: list[float]) -> tuple[bool, float]:
    """True if current_iv <= IV_STABLE_MULTIPLIER * mean(recent_ivs)."""
    if not recent_ivs:
        return True, 1.0
    avg = float(np.mean(recent_ivs))
    if avg <= 0:
        return True, 1.0
    ratio = current_iv / avg
    stable = ratio <= settings.IV_STABLE_MULTIPLIER
    return stable, round(ratio, 4)
