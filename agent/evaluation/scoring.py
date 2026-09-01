"""Score band resolution, confidence levels, and rejection intelligence."""

from agent.evaluation.checklist import CheckResult
from config import settings


def confidence_label(score: int) -> str:
    """HIGH / MEDIUM / LOW conviction from the score (doc §11)."""
    if score >= settings.SCORE_TRADE_MIN:
        return "HIGH"
    if score >= settings.SCORE_WATCH_MIN:
        return "MEDIUM"
    return "LOW"


def resolve_outcome(
    score: int,
    hard_gates_passed: bool,
    check_results: list[CheckResult],
    hard_gate_nums: set[int] | None = None,
) -> tuple[str, str]:
    """Returns (outcome, reject_reason).

    `hard_gate_nums` identifies which checks are hard gates for the strategy
    being scored — credit and debit checklists number them differently, so
    the caller passes the right set rather than this assuming {7, 8, 9}.
    """
    gates = hard_gate_nums or {7, 8, 9}

    if not hard_gates_passed:
        failed_gates = [r for r in check_results if r.check_num in gates and not r.passed]
        gate_names = ", ".join(r.name for r in failed_gates)
        return "REJECT", f"Failed hard gate: {gate_names}"

    if score >= settings.SCORE_TRADE_MIN:
        return "TRADE", ""

    failing = [r for r in check_results if not r.passed]
    failing_names = ", ".join(r.name for r in failing)

    if score >= settings.SCORE_WATCH_MIN:
        return "WATCH", (
            f"Score {score} below execution threshold "
            f"({settings.SCORE_TRADE_MIN}); failing: {failing_names}"
        )

    return "REJECT", (
        f"Score {score} below minimum ({settings.SCORE_WATCH_MIN}); "
        f"failing: {failing_names}"
    )


def build_why_not(
    check_results: list[CheckResult],
    outcome: str,
    rejected_alternative: str = "",
) -> dict:
    """Structured 'why / why not' explanation for a decision (doc §12, §13).

    Standing aside is an active decision, so every rejected candidate carries
    the same per-check detail a taken trade would, plus the reason the other
    premium side was not chosen.
    """
    passed = [
        {"check": r.name, "detail": r.note}
        for r in check_results if r.passed
    ]
    failed = [
        {"check": r.name, "detail": r.note}
        for r in check_results if not r.passed
    ]

    return {
        "outcome": outcome,
        "passed": passed,
        "failed": failed,
        "rejected_alternative": rejected_alternative,
    }
