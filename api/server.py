"""FastAPI REST server — read-only views into SQLite for the dashboard."""

import json
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from agent.logging.cards import build_card, card_to_dict
from agent.main import run_position_monitor, run_scan_cycle
from agent.perception.alpaca_client import AlpacaClient
from config import settings
from storage import db as storage
from storage.db import close_db, get_db, init_db
from datetime import date

app = FastAPI(title="Options Alpha Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_client: Optional[AlpacaClient] = None


@app.on_event("startup")
async def startup() -> None:
    global _client
    await init_db()
    _client = AlpacaClient()


@app.on_event("shutdown")
async def shutdown() -> None:
    if _client:
        await _client.close()
    await close_db()


@app.get("/api/health")
async def health():
    return {"status": "ok", "dry_run": settings.DRY_RUN, "watchlist": settings.WATCHLIST}


@app.post("/api/scan")
async def trigger_scan(x_scan_token: Optional[str] = Header(None)):
    """Manually trigger one scan cycle — for demo deployments with no scheduler.
    Requires X-Scan-Token header to match SCAN_TRIGGER_TOKEN when that env var is set."""
    if settings.SCAN_TRIGGER_TOKEN and x_scan_token != settings.SCAN_TRIGGER_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid or missing X-Scan-Token")
    db = await get_db()
    await run_scan_cycle(db, _client, verbose=False)
    return {"status": "cycle complete"}


@app.post("/api/monitor")
async def trigger_monitor(x_scan_token: Optional[str] = Header(None)):
    """Check open positions against exit rules without scanning for entries.

    Separate from /api/scan (strategy doc §14) so exits can be checked on a
    faster cadence than opportunity scanning.
    """
    if settings.SCAN_TRIGGER_TOKEN and x_scan_token != settings.SCAN_TRIGGER_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid or missing X-Scan-Token")
    db = await get_db()
    closed = await run_position_monitor(db, _client, verbose=False)
    return {
        "status": "monitor complete",
        "closed": [
            {
                "underlying": p.get("underlying"),
                "reason": p.get("close_reason"),
                "pnl": p.get("close_pnl"),
            }
            for p in closed
        ],
    }


@app.get("/api/events")
async def get_events(
    limit: int = Query(50, le=500),
    cycle_id: Optional[str] = Query(None),
):
    events = await storage.get_events(cycle_id=cycle_id, limit=limit)
    for e in events:
        if isinstance(e.get("payload"), str):
            try:
                e["payload"] = json.loads(e["payload"])
            except Exception:
                pass
    return events


@app.get("/api/decisions")
async def get_decisions(
    limit: int = Query(50, le=500),
    outcome: Optional[str] = Query(None),
):
    decisions = await storage.get_decisions(limit=limit, outcome=outcome)
    cards = []
    for d in decisions:
        card = build_card(d)
        cards.append(card_to_dict(card))
    return cards


@app.get("/api/positions")
async def get_positions():
    return await storage.get_open_positions_db()


@app.get("/api/watch_items")
async def get_watch_items(state: Optional[str] = Query(None)):
    items = await storage.get_watch_items(state=state)
    for item in items:
        if isinstance(item.get("failing_checks"), str):
            try:
                item["failing_checks"] = json.loads(item["failing_checks"])
            except Exception:
                pass
    return items


@app.get("/api/account")
async def get_account():
    try:
        return await _client.get_account()
    except Exception as exc:
        return JSONResponse(status_code=503, content={"error": str(exc)})


@app.get("/api/pipeline/latest")
async def get_pipeline_latest(cycles: int = Query(1, le=10)):
    all_events = await storage.get_events(limit=200)
    # Group by cycle_id, take most recent N cycles
    cycle_map: dict[str, list] = {}
    for e in all_events:
        cid = e["cycle_id"]
        if cid not in cycle_map:
            cycle_map[cid] = []
        if isinstance(e.get("payload"), str):
            try:
                e["payload"] = json.loads(e["payload"])
            except Exception:
                pass
        cycle_map[cid].append(e)

    recent_cycles = list(cycle_map.keys())[:cycles]
    return {cid: cycle_map[cid] for cid in recent_cycles}


@app.get("/api/baselines")
async def get_baselines(
    type: Optional[str] = Query(None),
    underlying: Optional[str] = Query(None),
):
    records = await storage.get_baseline_records(baseline_type=type, underlying=underlying)
    for r in records:
        if isinstance(r.get("details"), str):
            try:
                r["details"] = json.loads(r["details"])
            except Exception:
                pass
    return records


@app.get("/api/circuit_breaker/today")
async def get_circuit_breaker():
    today = date.today().isoformat()
    record = await storage.get_circuit_breaker(today)
    return record or {"date": today, "order_attempts": 0, "halted": 0}


# Serve React dashboard static files if built
_dashboard_dist = Path(__file__).parent.parent / "dashboard" / "dist"
if _dashboard_dist.exists():
    app.mount("/", StaticFiles(directory=str(_dashboard_dist), html=True), name="dashboard")
