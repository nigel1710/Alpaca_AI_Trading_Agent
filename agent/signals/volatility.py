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
    """Returns (condition, ratio). ELEVATED if atm_iv >= IV_RICH_MULTIPLIER * realized_vol.

    Legacy two-band classifier, kept for the credit-spread path and reporting.
    New code should prefer classify_volatility_regime().
    """
    if realized_vol <= 0:
        return "DEPRESSED", 0.0
    ratio = atm_iv / realized_vol
    condition = "ELEVATED" if ratio >= settings.IV_RICH_MULTIPLIER else "DEPRESSED"
    return condition, round(ratio, 4)


def classify_volatility_regime(atm_iv: float, realized_vol: float) -> tuple[str, float]:
    """Three-band volatility regime (strategy doc §5).

    Returns (regime, ratio) where regime is CHEAP / FAIR / RICH:
        IV/RVol <  IV_CHEAP_MAX  → CHEAP  — options underpriced, buy premium
        IV/RVol >  IV_RICH_MIN   → RICH   — options rich, sell premium
        otherwise                → FAIR   — needs stronger confirmation

    A non-positive realized vol means we cannot form a ratio at all, so the
    regime is unknown rather than cheap — return FAIR so the caller demands
    extra confirmation instead of treating it as a buy signal.
    """
    if realized_vol <= 0 or atm_iv <= 0:
        return "FAIR", 0.0

    ratio = atm_iv / realized_vol
    if ratio < settings.IV_CHEAP_MAX:
        regime = "CHEAP"
    elif ratio > settings.IV_RICH_MIN:
        regime = "RICH"
    else:
        regime = "FAIR"
    return regime, round(ratio, 4)


def expected_move_pct(atm_iv: float, dte: int) -> float:
    """Expected 1-sigma move over `dte` calendar days, as a fraction of spot.

    Standard approximation: sigma_period = IV_annual * sqrt(days / 365).
    Returns 0.0 when inputs are unusable so callers fail closed (an expected
    move of zero cannot clear any required move).
    """
    if atm_iv <= 0 or dte <= 0:
        return 0.0
    return float(atm_iv * math.sqrt(dte / 365.0))


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
