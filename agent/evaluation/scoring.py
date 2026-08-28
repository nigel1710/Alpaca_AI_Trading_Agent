"""Score band resolution: TRADE / WATCH / REJECT."""

from agent.evaluation.checklist import CheckResult
from config import settings


def resolve_outcome(
    score: int,
    hard_gates_passed: bool,
    check_results: list[CheckResult],
) -> tuple[str, str]:
    """Returns (outcome, reject_reason)."""
    if not hard_gates_passed:
        failed_gates = [r for r in check_results if r.check_num in {7, 8, 9} and not r.passed]
        gate_names = ", ".join(r.name for r in failed_gates)
        return "REJECT", f"Failed hard gate: {gate_names}"

    if score >= settings.SCORE_TRADE_MIN:
        return "TRADE", ""

    failing = [r for r in check_results if not r.passed]
    failing_names = ", ".join(r.name for r in failing)

    if score >= settings.SCORE_WATCH_MIN:
        return "WATCH", f"Score {score} below execution threshold ({settings.SCORE_TRADE_MIN}); failing: {failing_names}"

    return "REJECT", f"Score {score} below minimum ({settings.SCORE_WATCH_MIN}); failing: {failing_names}"
