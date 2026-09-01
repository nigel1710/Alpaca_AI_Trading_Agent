#!/usr/bin/env python3
"""Main agent loop — perception → decision → action, every 15 minutes during market hours."""

import asyncio
import json
import logging
import signal
import sys
from dataclasses import asdict
from datetime import date, datetime
from typing import Optional

import pytz

from agent.baselines.recorder import record_passive_baseline, record_unfiltered_baseline
from agent.evaluation.checklist import (
    DEBIT_HARD_GATES,
    HARD_GATES,
    run_checklist,
    run_debit_checklist,
)
from agent.evaluation.scoring import build_why_not, confidence_label, resolve_outcome
from agent.execution.circuit_breaker import check_circuit_breaker, init_daily_circuit_breaker
from agent.execution.monitor import monitor_open_positions
from agent.execution.orders import make_client_order_id, place_spread_order
from agent.execution.reconcile import reconcile_positions
from agent.logging.events import (
    emit_final_decision,
    emit_market_analysis,
    emit_market_scan,
    emit_opportunity_evaluation,
    emit_risk_review,
    emit_strategy_selection,
    new_cycle_id,
)
from agent.perception.account import get_account_state
from agent.perception.alpaca_client import AlpacaClient
from agent.perception.market_data import get_atm_option_chain, get_earnings_dates, get_price_bars
from agent.risk.gate import run_risk_gate
from agent.signals.trend import classify_trend
from agent.signals.volatility import (
    classify_volatility,
    classify_volatility_regime,
    compute_realized_vol,
    expected_move_pct,
    is_iv_stable,
)
from agent.strategy.matrix import rejected_alternative, select_strategy, strategy_type
from agent.strategy.structure import (
    build_debit_candidates,
    build_structure,
    select_expiry,
)
from agent.watch.manager import add_watch_item, expire_stale_watches, process_watch_items
from config import settings
from storage import db as storage
from storage.db import get_db, init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("agent.main")

ET = pytz.timezone("America/New_York")

_passive_starting_prices: dict[str, float] = {}
_shutdown_event = asyncio.Event()


def _is_market_open() -> bool:
    now_et = datetime.now(ET)
    if now_et.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now_et < market_close


def _verbose_print(verbose: bool, msg: str) -> None:
    if verbose:
        print(msg)


async def run_position_monitor(
    db,
    client: AlpacaClient,
    cycle_id: Optional[str] = None,
    verbose: bool = False,
) -> list[dict]:
    """Check open positions against their exit rules and close what triggers.

    Deliberately independent of the entry scanner (strategy doc §14) so risk
    on open positions can be checked on its own cadence — the scanner not
    running must never mean a stop-loss goes unchecked.
    """
    cycle_id = cycle_id or new_cycle_id()

    # Adopt any broker positions we have no local record of before evaluating
    # exits — on an ephemeral filesystem the DB can be wiped while positions
    # live on, and an unknown position is an unmanaged one.
    try:
        adopted = await reconcile_positions(client, db)
        for item in adopted:
            await storage.insert_event(
                cycle_id=cycle_id,
                stage="POSITION_RECONCILED",
                payload=item,
                underlying=item.get("underlying"),
            )
            _verbose_print(
                verbose,
                f"[RECONCILED]  {item.get('underlying')} {item.get('strategy')} "
                f"{item.get('expiry')} — adopted from broker",
            )
    except Exception:
        logger.exception("Position reconciliation failed")

    open_positions_db = await storage.get_open_positions_db()
    if not open_positions_db:
        return []

    closed = await monitor_open_positions(client, db, open_positions_db)
    for pos in closed:
        _verbose_print(
            verbose,
            f"[EXIT]  {pos.get('underlying')} | reason={pos.get('close_reason')} "
            f"| pnl={pos.get('close_pnl')}",
        )
        await storage.insert_event(
            cycle_id=cycle_id,
            stage="POSITION_EXIT",
            payload={
                "underlying": pos.get("underlying"),
                "strategy": pos.get("strategy"),
                "strategy_type": pos.get("strategy_type"),
                "reason": pos.get("close_reason"),
                "pnl": pos.get("close_pnl"),
            },
            underlying=pos.get("underlying"),
        )
    return closed


async def run_scan_cycle(db, client: AlpacaClient, verbose: bool = False) -> None:
    """Run one full scan cycle for all underlyings."""
    cycle_id = new_cycle_id()

    # --- Account & circuit breaker ---
    try:
        account = await get_account_state(client)
        equity = account["equity"]
    except Exception as exc:
        logger.error("Failed to get account state: %s", exc)
        return

    today = date.today().isoformat()
    await init_daily_circuit_breaker(db, equity)

    # --- Monitor existing positions FIRST (strategy doc §14) ---
    # Protecting open risk takes priority over finding new trades, and it runs
    # before the circuit-breaker gate: a halt must never prevent an exit.
    await run_position_monitor(db, client, cycle_id=cycle_id, verbose=verbose)

    halted, halt_reason = await check_circuit_breaker(db, equity)
    if halted:
        logger.warning("Scan skipped — circuit breaker active: %s", halt_reason)
        await storage.insert_event(
            cycle_id=cycle_id,
            stage="CIRCUIT_BREAKER_HALT",
            payload={"reason": halt_reason, "equity": equity},
        )
        return

    # --- Market scan ---
    await emit_market_scan(db, cycle_id, settings.WATCHLIST)
    _verbose_print(verbose, f"\n[MARKET SCAN]   Scanning: {', '.join(settings.WATCHLIST)} | cycle={cycle_id}")

    # Track scores for WATCH promotion
    current_scores: dict[str, int] = {}

    # Expiry window for the chain fetch must span BOTH strategy families:
    # credit spreads want DTE_MIN..DTE_MAX (short-dated) while debit spreads
    # want DEBIT_DTE_MIN..DEBIT_DTE_MAX. Per-strategy narrowing (and the
    # credit-only EXPIRY_CUTOFF) happens later in select_expiry().
    today_ord = date.today().toordinal()
    dte_low = min(settings.DTE_MIN, settings.DEBIT_DTE_MIN)
    dte_high = max(settings.DTE_MAX, settings.DEBIT_DTE_MAX)
    expiry_gte = date.fromordinal(today_ord + dte_low).isoformat()
    expiry_lte = date.fromordinal(today_ord + dte_high).isoformat()

    # --- Per-underlying scan ---
    for underlying in settings.WATCHLIST:
        try:
            await _process_underlying(
                db=db,
                client=client,
                underlying=underlying,
                cycle_id=cycle_id,
                equity=equity,
                expiry_gte=expiry_gte,
                expiry_lte=expiry_lte,
                current_scores=current_scores,
                verbose=verbose,
            )
        except Exception as exc:
            logger.error("Error processing %s: %s", underlying, exc, exc_info=True)
            await storage.insert_event(
                cycle_id=cycle_id,
                stage="ERROR",
                payload={"underlying": underlying, "error": str(exc)},
                underlying=underlying,
            )

    # --- WATCH lifecycle ---
    promoted = await process_watch_items(db, current_scores, cycle_id)
    for item in promoted:
        _verbose_print(verbose, f"[WATCH→TRADE]  {item['underlying']} promoted to TRADE candidate")

    expired = await expire_stale_watches(db, cycle_id)
    for item in expired:
        _verbose_print(verbose, f"[WATCH→EXPIRED]  {item['underlying']} expired")
        await storage.insert_decision(
            cycle_id=cycle_id,
            underlying=item["underlying"],
            outcome="EXPIRED",
            selected_strategy=item.get("strategy"),
            reject_reason=f"WATCH expired after {settings.WATCH_EXPIRY_CYCLES} cycles",
        )

    logger.info("Cycle %s complete.", cycle_id)


async def _process_underlying(
    db,
    client: AlpacaClient,
    underlying: str,
    cycle_id: str,
    equity: float,
    expiry_gte: str,
    expiry_lte: str,
    current_scores: dict[str, int],
    verbose: bool,
) -> None:
    # --- Price bars & trend ---
    bars = await get_price_bars(client, underlying, days=60)
    if bars.empty or len(bars) < settings.MA_LONG:
        logger.warning("%s: insufficient bars (%d)", underlying, len(bars))
        return

    current_price = float(bars["close"].iloc[-1])
    trend_condition, short_ma, long_ma, separation_pct = classify_trend(bars, current_price)

    # --- IV from option chain ---
    chain = await get_atm_option_chain(client, underlying, current_price, expiry_gte, expiry_lte)

    atm_iv = _extract_atm_iv(chain, current_price)
    realized_vol = compute_realized_vol(bars, window=20)
    # Three-band regime drives strategy selection; the legacy two-band label
    # is kept alongside it for continuity in reporting.
    vol_regime, vol_ratio = classify_volatility_regime(atm_iv, realized_vol)
    vol_condition, _ = classify_volatility(atm_iv, realized_vol)

    # IV stability
    iv_history = await storage.get_iv_history(underlying, days=3)
    recent_ivs = [r["atm_iv"] for r in iv_history]
    iv_stable, iv_stable_ratio = is_iv_stable(atm_iv, recent_ivs)

    # Store IV reading
    await storage.insert_iv_history(underlying, atm_iv, realized_vol)

    await emit_market_analysis(
        db, cycle_id, underlying, vol_regime, trend_condition,
        {
            "atm_iv": atm_iv,
            "realized_vol": realized_vol,
            "vol_ratio": vol_ratio,
            "vol_regime": vol_regime,
            "vol_condition_legacy": vol_condition,
            "iv_stable": iv_stable,
            "iv_stable_ratio": iv_stable_ratio,
            "short_ma": short_ma,
            "long_ma": long_ma,
            "separation_pct": separation_pct,
            "current_price": current_price,
        },
    )
    _verbose_print(
        verbose,
        f"[MARKET ANALYSIS {underlying}]  Trend: {trend_condition} (sep={separation_pct:.4%}), "
        f"Vol: {vol_regime} (IV/RVol={vol_ratio:.3f}), IV={atm_iv:.4f}, RVol={realized_vol:.4f}",
    )

    # --- Strategy selection (regime-adaptive) ---
    strategy, strategy_rationale = select_strategy(
        vol_regime, trend_condition, separation_pct
    )
    await emit_strategy_selection(
        db, cycle_id, underlying, strategy,
        {
            "vol_regime": vol_regime,
            "trend_condition": trend_condition,
            "rationale": strategy_rationale,
        },
    )
    _verbose_print(verbose, f"[STRATEGY {underlying}]  Selected: {strategy}")
    _verbose_print(verbose, f"                 Why: {strategy_rationale}")

    if strategy == "STAND_ASIDE":
        await record_unfiltered_baseline(db, cycle_id, underlying, strategy, None)
        _record_passive(db, cycle_id, underlying, current_price)
        # Standing aside is an active decision — record it with its reasoning
        # rather than silently dropping the symbol (doc §12).
        await storage.insert_decision(
            cycle_id=cycle_id,
            underlying=underlying,
            outcome="STAND_ASIDE",
            selected_strategy=strategy,
            volatility_condition=vol_regime,
            trend_condition=trend_condition,
            reject_reason=strategy_rationale,
            strategy_rationale=strategy_rationale,
            confidence="LOW",
            why_not_json=json.dumps({
                "outcome": "STAND_ASIDE",
                "passed": [],
                "failed": [],
                "rejected_alternative": strategy_rationale,
            }),
        )
        await emit_final_decision(db, cycle_id, underlying, "STAND_ASIDE")
        return

    is_debit = strategy_type(strategy) == "DEBIT"

    # --- Earnings ---
    earnings_dates = await get_earnings_dates(underlying)

    # --- Open positions count ---
    open_positions_db = await storage.get_open_positions_db()
    open_count = len(open_positions_db)
    open_positions_list = list(open_positions_db)

    # --- Structure selection ---
    # Debit spreads enumerate every viable strike pair and keep the one that
    # scores best; credit spreads use their single deterministic construction.
    structure: Optional[dict] = None
    score = 0
    check_results: list = []
    hard_gates_passed = False
    expected_move = 0.0

    if is_debit:
        expiry_choice = select_expiry(chain, strategy)
        candidates = (
            build_debit_candidates(strategy, chain, current_price, expiry_choice)
            if expiry_choice else []
        )
        best = None
        for cand in candidates:
            cand_expected_move = expected_move_pct(atm_iv, cand.get("dte", 0))
            cand_score, cand_checks, cand_gates = run_debit_checklist(
                volatility_regime=vol_regime,
                volatility_ratio=vol_ratio,
                iv_stable=iv_stable,
                iv_stable_ratio=iv_stable_ratio,
                trend_condition=trend_condition,
                trend_separation_pct=separation_pct,
                strategy=strategy,
                structure=cand,
                earnings_dates=earnings_dates,
                expiry=cand.get("expiry", ""),
                open_position_count=open_count,
                bid_ask_spread_pct=_bid_ask_pct(cand, cand.get("debit", 0.0)),
                open_interest_short=cand.get("short_oi", 0),
                open_interest_long=cand.get("long_oi", 0),
                expected_move=cand_expected_move,
            )
            # Rank by (gates passed, score) so a clean candidate always beats
            # a higher-scoring one that fails a hard gate.
            key = (cand_gates, cand_score)
            if best is None or key > best[0]:
                best = (key, cand, cand_score, cand_checks, cand_gates, cand_expected_move)

        if best is not None:
            _, structure, score, check_results, hard_gates_passed, expected_move = best
            _verbose_print(
                verbose,
                f"[CANDIDATES {underlying}]  Evaluated {len(candidates)} debit "
                f"spreads; best R:R={structure.get('reward_risk'):.2f} "
                f"score={score}",
            )
    else:
        structure = build_structure(strategy, chain, current_price)

    if structure is None:
        _verbose_print(verbose, f"[STRATEGY {underlying}]  No valid structure found — REJECT")
        await record_unfiltered_baseline(db, cycle_id, underlying, strategy, None)
        _record_passive(db, cycle_id, underlying, current_price)
        await storage.insert_decision(
            cycle_id=cycle_id,
            underlying=underlying,
            outcome="REJECT",
            selected_strategy=strategy,
            strategy_type=strategy_type(strategy),
            volatility_condition=vol_regime,
            trend_condition=trend_condition,
            reject_reason="No valid structure found in chain",
            strategy_rationale=strategy_rationale,
            confidence="LOW",
        )
        await emit_final_decision(db, cycle_id, underlying, "REJECT")
        return

    # --- Liquidity inputs ---
    credit = structure.get("credit", 0.0)
    debit = structure.get("debit", 0.0)
    net_premium = debit if is_debit else credit
    bid_ask_spread_pct = _bid_ask_pct(structure, net_premium)

    oi_short = structure.get("short_oi", 0)
    oi_long = structure.get("long_oi", 0)

    # --- Scored checklist (strategy-aware) ---
    # Debit candidates were already scored during ranking above; credit
    # spreads are scored here against the credit checklist.
    if not is_debit:
        score, check_results, hard_gates_passed = run_checklist(
            volatility_condition=vol_condition,
            volatility_ratio=vol_ratio,
            iv_stable=iv_stable,
            iv_stable_ratio=iv_stable_ratio,
            trend_condition=trend_condition,
            trend_separation_pct=separation_pct,
            strategy=strategy,
            structure=structure,
            earnings_dates=earnings_dates,
            expiry=structure.get("expiry", ""),
            open_position_count=open_count,
            bid_ask_spread_pct=bid_ask_spread_pct,
            open_interest_short=oi_short,
            open_interest_long=oi_long,
        )

    gate_nums = DEBIT_HARD_GATES if is_debit else HARD_GATES
    outcome, reject_reason = resolve_outcome(
        score, hard_gates_passed, check_results, gate_nums
    )
    confidence = confidence_label(score)
    current_scores[underlying] = score

    why_not = build_why_not(
        check_results, outcome, rejected_alternative(vol_regime, strategy)
    )

    await emit_opportunity_evaluation(db, cycle_id, underlying, score, outcome, check_results)
    _verbose_print(
        verbose,
        f"[EVALUATION {underlying}]  Score: {score}/100  Confidence: {confidence}  "
        f"Outcome: {outcome}" + (f"  ({reject_reason})" if reject_reason else ""),
    )
    if is_debit:
        _verbose_print(
            verbose,
            f"                 R:R={structure.get('reward_risk', 0):.2f}:1  "
            f"debit=${structure.get('debit', 0):.2f}  "
            f"maxReward=${structure.get('max_reward', 0):.0f}  "
            f"required={structure.get('required_move_pct', 0):.2%} vs "
            f"expected={expected_move:.2%}",
        )

    # Baseline recording
    await record_unfiltered_baseline(db, cycle_id, underlying, strategy, structure)
    _record_passive(db, cycle_id, underlying, current_price)

    checks_json = json.dumps([asdict(c) for c in check_results])
    why_not_json = json.dumps(why_not)
    expiry = structure.get("expiry", "")

    # Fields shared by every decision row written below.
    common_fields = dict(
        strategy_type=structure.get("strategy_type", strategy_type(strategy)),
        debit_paid=structure.get("debit") if is_debit else None,
        max_reward=structure.get("max_reward"),
        reward_risk=structure.get("reward_risk"),
        required_move_pct=structure.get("required_move_pct"),
        expected_move_pct=expected_move if is_debit else None,
        confidence=confidence,
        why_not_json=why_not_json,
        strategy_rationale=strategy_rationale,
    )

    if outcome == "WATCH":
        failing = [c.name for c in check_results if not c.passed]
        promoting = reject_reason
        await add_watch_item(db, underlying, strategy, score, failing, promoting, cycle_id)
        await storage.insert_decision(
            cycle_id=cycle_id,
            underlying=underlying,
            outcome="WATCH",
            volatility_condition=vol_regime,
            trend_condition=trend_condition,
            selected_strategy=strategy,
            opportunity_score=score,
            checks_json=checks_json,
            reject_reason=reject_reason,
            expiry=expiry,
            short_strike=structure.get("short_strike"),
            long_strike=structure.get("long_strike"),
            short_symbol=structure.get("short_symbol"),
            long_symbol=structure.get("long_symbol"),
            dte=structure.get("dte"),
            credit_received=structure.get("credit"),
            spread_width=structure.get("spread_width"),
            max_loss=structure.get("max_loss"),
            **common_fields,
        )
        await emit_final_decision(db, cycle_id, underlying, "WATCH")

    elif outcome == "REJECT":
        await storage.insert_decision(
            cycle_id=cycle_id,
            underlying=underlying,
            outcome="REJECT",
            volatility_condition=vol_regime,
            trend_condition=trend_condition,
            selected_strategy=strategy,
            opportunity_score=score,
            checks_json=checks_json,
            reject_reason=reject_reason,
            expiry=expiry,
            **common_fields,
        )
        await emit_final_decision(db, cycle_id, underlying, "REJECT")

    elif outcome == "TRADE":
        # Risk gate (independent — cannot be bypassed)
        approved, risk_reason = await run_risk_gate(
            structure=structure,
            strategy=strategy,
            account_equity=equity,
            open_positions=open_positions_list,
            earnings_dates=earnings_dates,
            expiry=expiry,
        )
        await emit_risk_review(db, cycle_id, underlying, approved, risk_reason)
        _verbose_print(
            verbose,
            f"[RISK GATE {underlying}]  {'APPROVED' if approved else 'REJECTED'}: {risk_reason}",
        )

        if approved:
            qty = 1
            order_result = await place_spread_order(
                client=client,
                db=db,
                structure=structure,
                strategy=strategy,
                underlying=underlying,
                qty=qty,
                decision_id=0,
            )
            order_id = order_result.get("id")
            await storage.insert_decision(
                cycle_id=cycle_id,
                underlying=underlying,
                outcome="TRADE",
                volatility_condition=vol_regime,
                trend_condition=trend_condition,
                selected_strategy=strategy,
                opportunity_score=score,
                checks_json=checks_json,
                risk_gate_result="APPROVED",
                risk_gate_reason=risk_reason,
                order_id=order_id,
                credit_received=structure.get("credit"),
                spread_width=structure.get("spread_width"),
                breakeven=structure.get("breakeven"),
                max_loss=structure.get("max_loss"),
                dte=structure.get("dte"),
                short_strike=structure.get("short_strike"),
                long_strike=structure.get("long_strike"),
                expiry=expiry,
                short_symbol=structure.get("short_symbol"),
                long_symbol=structure.get("long_symbol"),
                **common_fields,
            )
            await emit_final_decision(db, cycle_id, underlying, "TRADE", order_id)
            _verbose_print(verbose, f"[TRADE {underlying}]  Order placed: {order_id}")
        else:
            await storage.insert_decision(
                cycle_id=cycle_id,
                underlying=underlying,
                outcome="REJECT",
                volatility_condition=vol_regime,
                trend_condition=trend_condition,
                selected_strategy=strategy,
                opportunity_score=score,
                checks_json=checks_json,
                reject_reason=risk_reason,
                risk_gate_result="REJECTED",
                risk_gate_reason=risk_reason,
                expiry=expiry,
                **common_fields,
            )
            await emit_final_decision(db, cycle_id, underlying, "REJECT")


def _record_passive(db, cycle_id: str, underlying: str, current_price: float) -> None:
    """Fire-and-forget passive baseline record."""
    global _passive_starting_prices
    if underlying not in _passive_starting_prices:
        _passive_starting_prices[underlying] = current_price

    asyncio.create_task(
        record_passive_baseline(
            db=db,
            cycle_id=cycle_id,
            underlying=underlying,
            current_price=current_price,
            starting_price=_passive_starting_prices[underlying],
        )
    )


def _bid_ask_pct(structure: dict, net_premium: float) -> float:
    """Combined bid-ask width as a fraction of the net premium.

    Returns 1.0 (i.e. fails any liquidity check) when there is no premium to
    measure against, rather than dividing by zero.
    """
    if net_premium <= 0:
        return 1.0
    ba_width = (
        (structure.get("short_ask", 0.0) - structure.get("short_bid", 0.0))
        + (structure.get("long_ask", 0.0) - structure.get("long_bid", 0.0))
    )
    return ba_width / net_premium


def _extract_atm_iv(chain: list[dict], current_price: float) -> float:
    """Find ATM option IV — closest strike to current price."""
    if not chain:
        return 0.0
    atm = min(chain, key=lambda c: abs(c.get("strike", float("inf")) - current_price))
    return atm.get("implied_volatility") or 0.0


async def run_one_cycle(db=None, client: Optional[AlpacaClient] = None, verbose: bool = True) -> None:
    """Run a single scan cycle — used by the CLI."""
    if db is None:
        await init_db()
        db = await get_db()
    if client is None:
        client = AlpacaClient()
    await run_scan_cycle(db, client, verbose=verbose)
    await client.close()


async def run_agent() -> None:
    """Continuous agent loop — runs every SCAN_INTERVAL_MINUTES during market hours."""
    await init_db()
    db = await get_db()
    client = AlpacaClient()

    def _handle_shutdown(sig, frame):
        logger.info("Received %s — shutting down gracefully.", sig)
        _shutdown_event.set()

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    logger.info(
        "Agent starting. DRY_RUN=%s, Watchlist=%s, Interval=%dm",
        settings.DRY_RUN, settings.WATCHLIST, settings.SCAN_INTERVAL_MINUTES,
    )

    while not _shutdown_event.is_set():
        if _is_market_open():
            try:
                await run_scan_cycle(db, client, verbose=False)
            except Exception as exc:
                logger.error("Cycle error: %s", exc, exc_info=True)
        else:
            logger.info("Market closed — waiting.")

        try:
            await asyncio.wait_for(
                _shutdown_event.wait(),
                timeout=settings.SCAN_INTERVAL_MINUTES * 60,
            )
        except asyncio.TimeoutError:
            pass

    logger.info("Agent shut down.")
    await client.close()


if __name__ == "__main__":
    asyncio.run(run_agent())
