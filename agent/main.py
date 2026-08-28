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
from agent.evaluation.checklist import run_checklist
from agent.evaluation.scoring import resolve_outcome
from agent.execution.circuit_breaker import check_circuit_breaker, init_daily_circuit_breaker
from agent.execution.monitor import monitor_open_positions
from agent.execution.orders import make_client_order_id, place_spread_order
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
from agent.signals.volatility import classify_volatility, compute_realized_vol, is_iv_stable
from agent.strategy.matrix import select_strategy
from agent.strategy.structure import build_structure, select_expiry
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

    # --- Monitor exits for existing positions ---
    open_positions_db = await storage.get_open_positions_db()
    if open_positions_db:
        closed = await monitor_open_positions(client, db, open_positions_db)
        for pos in closed:
            _verbose_print(verbose, f"[EXIT]  {pos.get('underlying')} | reason={pos.get('close_reason')}")

    # Track scores for WATCH promotion
    current_scores: dict[str, int] = {}

    # Expiry window: DTE_MIN..DTE_MAX, before EXPIRY_CUTOFF
    expiry_gte = (date.today().__class__.fromordinal(date.today().toordinal() + settings.DTE_MIN)).isoformat()
    expiry_lte_raw = min(
        (date.today().__class__.fromordinal(date.today().toordinal() + settings.DTE_MAX)).isoformat(),
        settings.EXPIRY_CUTOFF,
    )
    expiry_lte = expiry_lte_raw

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
    vol_condition, vol_ratio = classify_volatility(atm_iv, realized_vol)

    # IV stability
    iv_history = await storage.get_iv_history(underlying, days=3)
    recent_ivs = [r["atm_iv"] for r in iv_history]
    iv_stable, iv_stable_ratio = is_iv_stable(atm_iv, recent_ivs)

    # Store IV reading
    await storage.insert_iv_history(underlying, atm_iv, realized_vol)

    await emit_market_analysis(
        db, cycle_id, underlying, vol_condition, trend_condition,
        {
            "atm_iv": atm_iv,
            "realized_vol": realized_vol,
            "vol_ratio": vol_ratio,
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
        f"Vol: {vol_condition} (ratio={vol_ratio:.3f}), IV={atm_iv:.4f}, RVol={realized_vol:.4f}",
    )

    # --- Strategy selection ---
    strategy = select_strategy(vol_condition, trend_condition)
    await emit_strategy_selection(db, cycle_id, underlying, strategy, {"vol_condition": vol_condition, "trend_condition": trend_condition})
    _verbose_print(verbose, f"[STRATEGY {underlying}]  Selected: {strategy}")

    if strategy == "STAND_ASIDE":
        await record_unfiltered_baseline(db, cycle_id, underlying, strategy, None)
        _record_passive(db, cycle_id, underlying, current_price)
        return

    # --- Structure selection ---
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
            volatility_condition=vol_condition,
            trend_condition=trend_condition,
            reject_reason="No valid structure found in chain",
        )
        await emit_final_decision(db, cycle_id, underlying, "REJECT")
        return

    # --- Earnings ---
    earnings_dates = await get_earnings_dates(underlying)

    # --- Open positions count ---
    open_positions_db = await storage.get_open_positions_db()
    open_count = len(open_positions_db)
    open_positions_list = list(open_positions_db)

    # --- Liquidity inputs ---
    credit = structure.get("credit", 0.0)
    short_bid = structure.get("short_bid", 0.0)
    short_ask = structure.get("short_ask", 0.0)
    long_bid = structure.get("long_bid", 0.0)
    long_ask = structure.get("long_ask", 0.0)
    # Spread bid-ask as fraction of credit
    spread_bid = credit  # net credit is mid; approximate BA spread
    if credit > 0:
        ba_width = (short_ask - short_bid) + (long_ask - long_bid)
        bid_ask_spread_pct = ba_width / credit if credit > 0 else 1.0
    else:
        bid_ask_spread_pct = 1.0

    oi_short = structure.get("short_oi", 0)
    oi_long = structure.get("long_oi", 0)

    # --- Scored checklist ---
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

    outcome, reject_reason = resolve_outcome(score, hard_gates_passed, check_results)
    current_scores[underlying] = score

    await emit_opportunity_evaluation(db, cycle_id, underlying, score, outcome, check_results)
    _verbose_print(
        verbose,
        f"[EVALUATION {underlying}]  Score: {score}/100  Outcome: {outcome}"
        + (f"  ({reject_reason})" if reject_reason else ""),
    )

    # Baseline recording
    await record_unfiltered_baseline(db, cycle_id, underlying, strategy, structure)
    _record_passive(db, cycle_id, underlying, current_price)

    checks_json = json.dumps([asdict(c) for c in check_results])
    expiry = structure.get("expiry", "")

    if outcome == "WATCH":
        failing = [c.name for c in check_results if not c.passed]
        promoting = reject_reason
        await add_watch_item(db, underlying, strategy, score, failing, promoting, cycle_id)
        await storage.insert_decision(
            cycle_id=cycle_id,
            underlying=underlying,
            outcome="WATCH",
            volatility_condition=vol_condition,
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
        )
        await emit_final_decision(db, cycle_id, underlying, "WATCH")

    elif outcome == "REJECT":
        await storage.insert_decision(
            cycle_id=cycle_id,
            underlying=underlying,
            outcome="REJECT",
            volatility_condition=vol_condition,
            trend_condition=trend_condition,
            selected_strategy=strategy,
            opportunity_score=score,
            checks_json=checks_json,
            reject_reason=reject_reason,
            expiry=expiry,
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
                volatility_condition=vol_condition,
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
            )
            await emit_final_decision(db, cycle_id, underlying, "TRADE", order_id)
            _verbose_print(verbose, f"[TRADE {underlying}]  Order placed: {order_id}")
        else:
            await storage.insert_decision(
                cycle_id=cycle_id,
                underlying=underlying,
                outcome="REJECT",
                volatility_condition=vol_condition,
                trend_condition=trend_condition,
                selected_strategy=strategy,
                opportunity_score=score,
                checks_json=checks_json,
                reject_reason=risk_reason,
                risk_gate_result="REJECTED",
                risk_gate_reason=risk_reason,
                expiry=expiry,
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
