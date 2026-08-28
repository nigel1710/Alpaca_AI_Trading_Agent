"""CLI: score distribution report."""

import asyncio
import json
from collections import Counter
from datetime import datetime, timedelta

import click

from config import settings
from storage.db import init_db, get_db, get_decisions


@click.command("score-report")
@click.option("--days", default=1, help="Look back N days (default 1)")
def score_report(days: int) -> None:
    """Print score distribution report. Sample-size discipline enforced."""
    asyncio.run(_report(days))


def _bucket(score: int) -> str:
    if score < 20:
        return "0-19"
    elif score < 40:
        return "20-39"
    elif score < 60:
        return "40-59"
    elif score < 80:
        return "60-79"
    else:
        return "80-100"


async def _report(days: int) -> None:
    await init_db()
    db = await get_db()
    decisions = await get_decisions(limit=10000)

    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    decisions = [d for d in decisions if d.get("ts", "") >= cutoff]

    print(f"\n{'='*60}")
    print(f"  OPTIONS ALPHA AGENT — SCORE DISTRIBUTION REPORT")
    print(f"  Period: last {days} day(s) | Decisions: {len(decisions)}")
    print(f"  Sample size discipline: rates shown only when N>=5")
    print(f"{'='*60}\n")

    if not decisions:
        print("  No decisions in this period.")
        return

    # Outcome counts
    outcome_counts = Counter(d["outcome"] for d in decisions)
    print("OUTCOME COUNTS")
    print("-" * 30)
    for outcome in ["TRADE", "WATCH", "REJECT", "EXPIRED"]:
        n = outcome_counts.get(outcome, 0)
        print(f"  {outcome:<10} {n:>4}")
    print()

    # Score histogram (exclude decisions with no score)
    scored = [d for d in decisions if d.get("opportunity_score") is not None]
    buckets: Counter = Counter()
    for d in scored:
        buckets[_bucket(d["opportunity_score"])] += 1

    print("SCORE HISTOGRAM (scored decisions)")
    print("-" * 30)
    for bucket in ["0-19", "20-39", "40-59", "60-79", "80-100"]:
        n = buckets.get(bucket, 0)
        bar = "█" * min(n, 40)
        print(f"  {bucket}  {bar} ({n})")
    print()

    # Check failure frequency
    fail_counts: Counter = Counter()
    for d in decisions:
        checks_raw = d.get("checks_json")
        if not checks_raw:
            continue
        try:
            checks = json.loads(checks_raw)
        except Exception:
            continue
        for c in checks:
            if not c.get("passed", True):
                fail_counts[c.get("name", "unknown")] += 1

    print("MOST FREQUENTLY FAILING CHECKS")
    print("-" * 30)
    if fail_counts:
        for name, count in fail_counts.most_common(10):
            n = count
            rate_str = f" ({n/len(decisions):.0%})" if len(decisions) >= 5 else f" (raw: {n})"
            print(f"  {name:<25} {n:>4}{rate_str}")
    else:
        print("  No check data available.")
    print()

    # Rejection reasons
    reject_reasons: Counter = Counter()
    for d in decisions:
        if d["outcome"] == "REJECT" and d.get("reject_reason"):
            # Truncate to first meaningful clause
            reason = d["reject_reason"].split(";")[0][:50]
            reject_reasons[reason] += 1

    print("MOST COMMON REJECTION REASONS")
    print("-" * 30)
    if reject_reasons:
        for reason, count in reject_reasons.most_common(8):
            print(f"  {reason:<50} {count:>4}")
    else:
        print("  No rejections in this period.")
    print()

    # Per-underlying breakdown
    print("DECISIONS BY UNDERLYING")
    print("-" * 30)
    for sym in settings.WATCHLIST:
        sym_decisions = [d for d in decisions if d.get("underlying") == sym]
        n = len(sym_decisions)
        if n == 0:
            continue
        sym_outcomes = Counter(d["outcome"] for d in sym_decisions)
        print(f"  {sym}: n={n} | " + " | ".join(f"{k}={v}" for k, v in sym_outcomes.items()))
    print()
