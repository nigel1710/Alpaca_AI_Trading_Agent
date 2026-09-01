"""9-check scored opportunity checklist with hard gates."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, Union

from config import settings

HARD_GATES = {7, 8, 9}

# Debit-spread checklist hard gates (doc §10): event risk, required move,
# liquidity, and portfolio fit. Required move is a gate rather than a scored
# item because a spread that cannot realistically reach breakeven is not a
# trade at any score (doc §6).
DEBIT_HARD_GATES = {4, 7, 9, 10}


@dataclass
class CheckResult:
    check_num: int
    name: str
    passed: bool
    value: Union[float, str, bool]
    threshold: Union[float, str, bool, None]
    points_possible: int
    points_earned: int
    note: str


def _strategy_agrees_with_trend(strategy: str, trend_condition: str) -> bool:
    """True if the selected structure's directional bias matches the trend."""
    if strategy == "BULL_PUT" and trend_condition == "UP":
        return True
    if strategy == "BEAR_CALL" and trend_condition == "DOWN":
        return True
    if strategy == "IRON_CONDOR" and trend_condition == "RANGE":
        return True
    if strategy == "BULL_CALL_DEBIT" and trend_condition == "UP":
        return True
    if strategy == "BEAR_PUT_DEBIT" and trend_condition == "DOWN":
        return True
    return False


def _has_event_before_expiry(earnings_dates: list[str], expiry: str) -> bool:
    """True if any earnings date falls before or on the option expiry."""
    try:
        exp_date = date.fromisoformat(expiry)
    except ValueError:
        return False
    for d_str in earnings_dates:
        try:
            d = date.fromisoformat(d_str)
            if d <= exp_date:
                return True
        except ValueError:
            pass
    return False


def run_checklist(
    volatility_condition: str,
    volatility_ratio: float,
    iv_stable: bool,
    iv_stable_ratio: float,
    trend_condition: str,
    trend_separation_pct: float,
    strategy: str,
    structure: dict,
    earnings_dates: list[str],
    expiry: str,
    open_position_count: int,
    bid_ask_spread_pct: float,
    open_interest_short: int,
    open_interest_long: int,
) -> tuple[int, list[CheckResult], bool]:
    """Returns (total_score, check_results, all_hard_gates_passed)."""
    results: list[CheckResult] = []

    credit = structure.get("credit", 0.0)
    spread_width = structure.get("spread_width", 1.0)
    credit_width_ratio = credit / spread_width if spread_width > 0 else 0.0
    short_delta = structure.get("short_delta", 1.0)

    # Check 1: Premium rich (15 pts)
    c1_passed = volatility_condition == "ELEVATED"
    results.append(CheckResult(
        check_num=1,
        name="Premium rich",
        passed=c1_passed,
        value=round(volatility_ratio, 3),
        threshold=settings.IV_RICH_MULTIPLIER,
        points_possible=15,
        points_earned=15 if c1_passed else 0,
        note=f"IV/RVol={volatility_ratio:.3f}; need >={settings.IV_RICH_MULTIPLIER}",
    ))

    # Check 2: Volatility stable (10 pts)
    c2_passed = iv_stable
    results.append(CheckResult(
        check_num=2,
        name="Volatility stable",
        passed=c2_passed,
        value=round(iv_stable_ratio, 3),
        threshold=settings.IV_STABLE_MULTIPLIER,
        points_possible=10,
        points_earned=10 if c2_passed else 0,
        note=f"IV/3dAvg={iv_stable_ratio:.3f}; need <={settings.IV_STABLE_MULTIPLIER}",
    ))

    # Check 3: Trend clarity (15 pts)
    c3_passed = trend_condition != "RANGE" and trend_separation_pct > settings.TREND_CLARITY_THRESHOLD
    results.append(CheckResult(
        check_num=3,
        name="Trend clarity",
        passed=c3_passed,
        value=round(trend_separation_pct, 5),
        threshold=settings.TREND_CLARITY_THRESHOLD,
        points_possible=15,
        points_earned=15 if c3_passed else 0,
        note=f"MA sep={trend_separation_pct:.4%}; need >{settings.TREND_CLARITY_THRESHOLD:.4%}",
    ))

    # Check 4: Directional agreement (10 pts)
    c4_passed = _strategy_agrees_with_trend(strategy, trend_condition)
    results.append(CheckResult(
        check_num=4,
        name="Directional agreement",
        passed=c4_passed,
        value=f"{strategy} vs {trend_condition}",
        threshold=None,
        points_possible=10,
        points_earned=10 if c4_passed else 0,
        note=f"Strategy {strategy} {'agrees' if c4_passed else 'disagrees'} with trend {trend_condition}",
    ))

    # Check 5: Credit quality (15 pts)
    c5_passed = credit_width_ratio >= settings.CREDIT_WIDTH_FLOOR
    results.append(CheckResult(
        check_num=5,
        name="Credit quality",
        passed=c5_passed,
        value=round(credit_width_ratio, 4),
        threshold=settings.CREDIT_WIDTH_FLOOR,
        points_possible=15,
        points_earned=15 if c5_passed else 0,
        note=f"Credit/Width={credit_width_ratio:.2%}; need >={settings.CREDIT_WIDTH_FLOOR:.0%}",
    ))

    # Check 6: Probability profile (10 pts)
    c6_passed = short_delta <= settings.DELTA_CEILING
    results.append(CheckResult(
        check_num=6,
        name="Probability profile",
        passed=c6_passed,
        value=round(short_delta, 4),
        threshold=settings.DELTA_CEILING,
        points_possible=10,
        points_earned=10 if c6_passed else 0,
        note=f"ShortDelta={short_delta:.4f}; need <={settings.DELTA_CEILING}",
    ))

    # Check 7: Liquidity — HARD GATE (10 pts)
    liquidity_spread_ok = bid_ask_spread_pct <= settings.LIQUIDITY_SPREAD_MAX
    liquidity_oi_ok = (
        open_interest_short >= settings.LIQUIDITY_OI_MIN
        and open_interest_long >= settings.LIQUIDITY_OI_MIN
    )
    c7_passed = liquidity_spread_ok and liquidity_oi_ok
    results.append(CheckResult(
        check_num=7,
        name="Liquidity",
        passed=c7_passed,
        value=f"spread={bid_ask_spread_pct:.2%}, OI_s={open_interest_short}, OI_l={open_interest_long}",
        threshold=f"spread<={settings.LIQUIDITY_SPREAD_MAX:.0%}, OI>={settings.LIQUIDITY_OI_MIN}",
        points_possible=10,
        points_earned=10 if c7_passed else 0,
        note=f"[HARD GATE] Spread {'OK' if liquidity_spread_ok else 'FAIL'}, OI {'OK' if liquidity_oi_ok else 'FAIL'}",
    ))

    # Check 8: Event clear — HARD GATE (10 pts)
    event_conflict = _has_event_before_expiry(earnings_dates, expiry)
    c8_passed = not event_conflict
    results.append(CheckResult(
        check_num=8,
        name="Event clear",
        passed=c8_passed,
        value=f"earnings_dates={earnings_dates}",
        threshold=f"expiry={expiry}",
        points_possible=10,
        points_earned=10 if c8_passed else 0,
        note=f"[HARD GATE] {'Earnings conflict before expiry' if event_conflict else 'No events before expiry'}",
    ))

    # Check 9: Portfolio fit — HARD GATE (5 pts)
    c9_passed = open_position_count < settings.MAX_CONCURRENT_POSITIONS
    results.append(CheckResult(
        check_num=9,
        name="Portfolio fit",
        passed=c9_passed,
        value=open_position_count,
        threshold=settings.MAX_CONCURRENT_POSITIONS,
        points_possible=5,
        points_earned=5 if c9_passed else 0,
        note=f"[HARD GATE] {open_position_count}/{settings.MAX_CONCURRENT_POSITIONS} positions open",
    ))

    # Hard gate check: ALL of 7, 8, 9 must pass
    all_hard_gates_passed = c7_passed and c8_passed and c9_passed

    total_score = sum(r.points_earned for r in results)

    return total_score, results, all_hard_gates_passed


def run_debit_checklist(
    volatility_regime: str,
    volatility_ratio: float,
    iv_stable: bool,
    iv_stable_ratio: float,
    trend_condition: str,
    trend_separation_pct: float,
    strategy: str,
    structure: dict,
    earnings_dates: list[str],
    expiry: str,
    open_position_count: int,
    bid_ask_spread_pct: float,
    open_interest_short: int,
    open_interest_long: int,
    expected_move: float,
) -> tuple[int, list[CheckResult], bool]:
    """Strategy-aware checklist for debit spreads (doc §10).

    Points total 100. Hard gates are event risk (4), required move (7),
    liquidity (9), and portfolio fit (10).

    Returns (total_score, check_results, all_hard_gates_passed).
    """
    results: list[CheckResult] = []

    reward_risk = structure.get("reward_risk", 0.0)
    required_move = abs(structure.get("required_move_pct", 1.0))
    long_delta = structure.get("long_delta", 0.0)
    short_delta = structure.get("short_delta", 0.0)

    # --- Market checks ---

    # Check 1: Trend clarity (15 pts)
    c1_passed = (
        trend_condition != "RANGE"
        and trend_separation_pct > settings.TREND_CLARITY_THRESHOLD
    )
    results.append(CheckResult(
        check_num=1,
        name="Trend clarity",
        passed=c1_passed,
        value=round(trend_separation_pct, 5),
        threshold=settings.TREND_CLARITY_THRESHOLD,
        points_possible=15,
        points_earned=15 if c1_passed else 0,
        note=f"MA sep={trend_separation_pct:.4%}; need >{settings.TREND_CLARITY_THRESHOLD:.4%}",
    ))

    # Check 2: Directional agreement (10 pts)
    c2_passed = _strategy_agrees_with_trend(strategy, trend_condition)
    results.append(CheckResult(
        check_num=2,
        name="Directional agreement",
        passed=c2_passed,
        value=f"{strategy} vs {trend_condition}",
        threshold=None,
        points_possible=10,
        points_earned=10 if c2_passed else 0,
        note=f"Strategy {strategy} {'agrees' if c2_passed else 'disagrees'} with trend {trend_condition}",
    ))

    # Check 3: Volatility stable (5 pts)
    c3_passed = iv_stable
    results.append(CheckResult(
        check_num=3,
        name="Volatility stable",
        passed=c3_passed,
        value=round(iv_stable_ratio, 3),
        threshold=settings.IV_STABLE_MULTIPLIER,
        points_possible=5,
        points_earned=5 if c3_passed else 0,
        note=f"IV/3dAvg={iv_stable_ratio:.3f}; need <={settings.IV_STABLE_MULTIPLIER}",
    ))

    # Check 4: Event clear — HARD GATE (10 pts)
    event_conflict = _has_event_before_expiry(earnings_dates, expiry)
    c4_passed = not event_conflict
    results.append(CheckResult(
        check_num=4,
        name="Event clear",
        passed=c4_passed,
        value=f"earnings_dates={earnings_dates}",
        threshold=f"expiry={expiry}",
        points_possible=10,
        points_earned=10 if c4_passed else 0,
        note=f"[HARD GATE] {'Earnings conflict before expiry' if event_conflict else 'No events before expiry'}",
    ))

    # --- Debit-specific checks ---

    # Check 5: Volatility cheap or reasonably priced (15 pts)
    # Buying premium wants CHEAP; FAIR is acceptable but not rewarded fully.
    if volatility_regime == "CHEAP":
        c5_points, c5_passed = 15, True
        c5_note = f"IV/RVol={volatility_ratio:.3f} — CHEAP, good for buying premium"
    elif volatility_regime == "FAIR":
        c5_points, c5_passed = 8, True
        c5_note = f"IV/RVol={volatility_ratio:.3f} — FAIR, acceptable but not a discount"
    else:
        c5_points, c5_passed = 0, False
        c5_note = f"IV/RVol={volatility_ratio:.3f} — RICH, overpaying to buy premium"
    results.append(CheckResult(
        check_num=5,
        name="Volatility priced for buying",
        passed=c5_passed,
        value=round(volatility_ratio, 3),
        threshold=settings.IV_CHEAP_MAX,
        points_possible=15,
        points_earned=c5_points,
        note=c5_note,
    ))

    # Check 6: Reward/Risk (20 pts) — scaled between MIN and PREFERRED
    if reward_risk >= settings.DEBIT_RR_PREFERRED:
        c6_points, c6_passed = 20, True
    elif reward_risk >= settings.DEBIT_RR_MIN:
        span = settings.DEBIT_RR_PREFERRED - settings.DEBIT_RR_MIN
        frac = (reward_risk - settings.DEBIT_RR_MIN) / span if span > 0 else 0.0
        c6_points, c6_passed = int(round(10 + 10 * frac)), True
    else:
        c6_points, c6_passed = 0, False
    results.append(CheckResult(
        check_num=6,
        name="Reward/Risk",
        passed=c6_passed,
        value=round(reward_risk, 2),
        threshold=settings.DEBIT_RR_MIN,
        points_possible=20,
        points_earned=c6_points,
        note=f"R:R={reward_risk:.2f}:1; need >={settings.DEBIT_RR_MIN} (prefer >={settings.DEBIT_RR_PREFERRED})",
    ))

    # Check 7: Required move realistic — HARD GATE (10 pts)
    # The move needed to break even must fit inside the expected move with
    # headroom; otherwise the reward/risk is an illusion (doc §6, §7).
    move_budget = expected_move * settings.REQUIRED_MOVE_HEADROOM
    c7_passed = expected_move > 0 and required_move <= move_budget
    results.append(CheckResult(
        check_num=7,
        name="Required move realistic",
        passed=c7_passed,
        value=round(required_move, 5),
        threshold=round(move_budget, 5),
        points_possible=10,
        points_earned=10 if c7_passed else 0,
        note=(
            f"[HARD GATE] Required {required_move:.2%} vs expected "
            f"{expected_move:.2%} (budget {move_budget:.2%})"
        ),
    ))

    # Check 8: Strike selection appropriate (5 pts)
    long_ok = (
        settings.DEBIT_LONG_DELTA_MIN <= long_delta <= settings.DEBIT_LONG_DELTA_MAX
    )
    short_ok = (
        settings.DEBIT_SHORT_DELTA_MIN <= short_delta <= settings.DEBIT_SHORT_DELTA_MAX
    )
    c8_passed = long_ok and short_ok
    results.append(CheckResult(
        check_num=8,
        name="Strike selection",
        passed=c8_passed,
        value=f"long={long_delta:.3f}, short={short_delta:.3f}",
        threshold=(
            f"long {settings.DEBIT_LONG_DELTA_MIN}-{settings.DEBIT_LONG_DELTA_MAX}, "
            f"short {settings.DEBIT_SHORT_DELTA_MIN}-{settings.DEBIT_SHORT_DELTA_MAX}"
        ),
        points_possible=5,
        points_earned=5 if c8_passed else 0,
        note=f"Long delta {'OK' if long_ok else 'FAIL'}, short delta {'OK' if short_ok else 'FAIL'}",
    ))

    # Check 9: Liquidity — HARD GATE (5 pts)
    liquidity_spread_ok = bid_ask_spread_pct <= settings.LIQUIDITY_SPREAD_MAX
    liquidity_oi_ok = (
        open_interest_short >= settings.LIQUIDITY_OI_MIN
        and open_interest_long >= settings.LIQUIDITY_OI_MIN
    )
    c9_passed = liquidity_spread_ok and liquidity_oi_ok
    results.append(CheckResult(
        check_num=9,
        name="Liquidity",
        passed=c9_passed,
        value=f"spread={bid_ask_spread_pct:.2%}, OI_s={open_interest_short}, OI_l={open_interest_long}",
        threshold=f"spread<={settings.LIQUIDITY_SPREAD_MAX:.0%}, OI>={settings.LIQUIDITY_OI_MIN}",
        points_possible=5,
        points_earned=5 if c9_passed else 0,
        note=f"[HARD GATE] Spread {'OK' if liquidity_spread_ok else 'FAIL'}, OI {'OK' if liquidity_oi_ok else 'FAIL'}",
    ))

    # --- Portfolio check ---

    # Check 10: Portfolio fit — HARD GATE (5 pts)
    c10_passed = open_position_count < settings.MAX_CONCURRENT_POSITIONS
    results.append(CheckResult(
        check_num=10,
        name="Portfolio fit",
        passed=c10_passed,
        value=open_position_count,
        threshold=settings.MAX_CONCURRENT_POSITIONS,
        points_possible=5,
        points_earned=5 if c10_passed else 0,
        note=f"[HARD GATE] {open_position_count}/{settings.MAX_CONCURRENT_POSITIONS} positions open",
    ))

    all_hard_gates_passed = c4_passed and c7_passed and c9_passed and c10_passed
    total_score = sum(r.points_earned for r in results)

    return total_score, results, all_hard_gates_passed
