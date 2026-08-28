"""Independent risk gate — cannot be bypassed by any score."""

from datetime import date

from config import settings


async def run_risk_gate(
    structure: dict,
    strategy: str,
    account_equity: float,
    open_positions: list[dict],
    earnings_dates: list[str],
    expiry: str,
) -> tuple[bool, str]:
    """Returns (approved, reason). All three checks must pass."""

    # Check 1: Max loss per trade <= MAX_LOSS_PCT of account equity
    max_loss = structure.get("max_loss", float("inf"))
    max_allowed_loss = settings.MAX_LOSS_PCT * account_equity
    if max_loss > max_allowed_loss:
        return (
            False,
            f"Max loss ${max_loss:.2f} exceeds {settings.MAX_LOSS_PCT:.0%} of equity "
            f"(${max_allowed_loss:.2f})",
        )

    # Check 2: Concurrent position limit
    if len(open_positions) >= settings.MAX_CONCURRENT_POSITIONS:
        return (
            False,
            f"At position limit ({len(open_positions)}/{settings.MAX_CONCURRENT_POSITIONS})",
        )

    # Check 3: No earnings before expiry (event avoidance)
    try:
        exp_date = date.fromisoformat(expiry)
    except ValueError:
        return False, f"Invalid expiry date: {expiry}"

    for d_str in earnings_dates:
        try:
            d = date.fromisoformat(d_str)
            if d <= exp_date:
                return (
                    False,
                    f"Earnings on {d_str} falls before or on expiry {expiry}",
                )
        except ValueError:
            pass

    return True, "All risk checks passed"
