"""Async SQLite persistence layer using aiosqlite."""

import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import aiosqlite

from config import settings

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"
_db_conn: Optional[aiosqlite.Connection] = None


# Columns added after the initial schema shipped. CREATE TABLE IF NOT EXISTS
# will not add them to a database that already exists, so they are applied
# individually and idempotently on every startup.
_MIGRATIONS: dict[str, list[tuple[str, str]]] = {
    "decisions": [
        ("strategy_type", "TEXT"),
        ("debit_paid", "REAL"),
        ("max_reward", "REAL"),
        ("reward_risk", "REAL"),
        ("required_move_pct", "REAL"),
        ("expected_move_pct", "REAL"),
        ("confidence", "TEXT"),
        ("why_not_json", "TEXT"),
        ("strategy_rationale", "TEXT"),
    ],
    "positions": [
        ("strategy_type", "TEXT NOT NULL DEFAULT 'CREDIT'"),
        ("debit_paid", "REAL"),
        ("max_reward", "REAL"),
    ],
}


async def _apply_migrations(conn: aiosqlite.Connection) -> None:
    for table, columns in _MIGRATIONS.items():
        cur = await conn.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in await cur.fetchall()}
        for name, coltype in columns:
            if name in existing:
                continue
            await conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {coltype}")
            logger.info("Migrated: added %s.%s", table, name)
    await conn.commit()


async def init_db() -> None:
    """Create tables from schema.sql if they don't exist, then migrate."""
    global _db_conn
    _db_conn = await aiosqlite.connect(settings.DB_PATH)
    _db_conn.row_factory = aiosqlite.Row
    schema = _SCHEMA_PATH.read_text()
    await _db_conn.executescript(schema)
    await _db_conn.commit()
    await _apply_migrations(_db_conn)
    logger.info("Database initialized at %s", settings.DB_PATH)


async def get_db() -> aiosqlite.Connection:
    global _db_conn
    if _db_conn is None:
        await init_db()
    return _db_conn


async def close_db() -> None:
    """Close the connection and stop aiosqlite's worker thread.

    That worker is a non-daemon thread, so leaving the connection open makes
    the interpreter hang at shutdown waiting for it to join. Short-lived
    entry points (the CLI) must call this before exiting.
    """
    global _db_conn
    if _db_conn is not None:
        await _db_conn.close()
        _db_conn = None


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


# --- Events ---

async def insert_event(
    cycle_id: str,
    stage: str,
    payload: dict,
    underlying: Optional[str] = None,
) -> int:
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO events (ts, cycle_id, underlying, stage, payload) VALUES (?, ?, ?, ?, ?)",
        (_now(), cycle_id, underlying, stage, json.dumps(payload)),
    )
    await db.commit()
    return cur.lastrowid


async def get_events(cycle_id: Optional[str] = None, limit: int = 100) -> list[dict]:
    db = await get_db()
    if cycle_id:
        cur = await db.execute(
            "SELECT * FROM events WHERE cycle_id = ? ORDER BY id DESC LIMIT ?",
            (cycle_id, limit),
        )
    else:
        cur = await db.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
        )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


# --- Decisions ---

async def insert_decision(
    cycle_id: str,
    underlying: str,
    outcome: str,
    volatility_condition: Optional[str] = None,
    trend_condition: Optional[str] = None,
    selected_strategy: Optional[str] = None,
    opportunity_score: Optional[int] = None,
    checks_json: Optional[str] = None,
    reject_reason: Optional[str] = None,
    risk_gate_result: Optional[str] = None,
    risk_gate_reason: Optional[str] = None,
    order_id: Optional[str] = None,
    credit_received: Optional[float] = None,
    spread_width: Optional[float] = None,
    breakeven: Optional[float] = None,
    max_loss: Optional[float] = None,
    dte: Optional[int] = None,
    short_strike: Optional[float] = None,
    long_strike: Optional[float] = None,
    expiry: Optional[str] = None,
    short_symbol: Optional[str] = None,
    long_symbol: Optional[str] = None,
    strategy_type: Optional[str] = None,
    debit_paid: Optional[float] = None,
    max_reward: Optional[float] = None,
    reward_risk: Optional[float] = None,
    required_move_pct: Optional[float] = None,
    expected_move_pct: Optional[float] = None,
    confidence: Optional[str] = None,
    why_not_json: Optional[str] = None,
    strategy_rationale: Optional[str] = None,
) -> int:
    db = await get_db()
    cur = await db.execute(
        """INSERT INTO decisions (
            ts, cycle_id, underlying, volatility_condition, trend_condition,
            selected_strategy, opportunity_score, checks_json, outcome,
            reject_reason, risk_gate_result, risk_gate_reason, order_id,
            credit_received, spread_width, breakeven, max_loss, dte,
            short_strike, long_strike, expiry, short_symbol, long_symbol,
            strategy_type, debit_paid, max_reward, reward_risk,
            required_move_pct, expected_move_pct, confidence, why_not_json,
            strategy_rationale
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            _now(), cycle_id, underlying, volatility_condition, trend_condition,
            selected_strategy, opportunity_score, checks_json, outcome,
            reject_reason, risk_gate_result, risk_gate_reason, order_id,
            credit_received, spread_width, breakeven, max_loss, dte,
            short_strike, long_strike, expiry, short_symbol, long_symbol,
            strategy_type, debit_paid, max_reward, reward_risk,
            required_move_pct, expected_move_pct, confidence, why_not_json,
            strategy_rationale,
        ),
    )
    await db.commit()
    return cur.lastrowid


async def get_decisions(limit: int = 100, outcome: Optional[str] = None) -> list[dict]:
    db = await get_db()
    if outcome:
        cur = await db.execute(
            "SELECT * FROM decisions WHERE outcome = ? ORDER BY id DESC LIMIT ?",
            (outcome, limit),
        )
    else:
        cur = await db.execute(
            "SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (limit,)
        )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


# --- Watch Items ---

async def upsert_watch_item(
    underlying: str,
    strategy: str,
    score: int,
    failing_checks: list[str],
    promoting_condition: str,
    cycle_id: str,
) -> int:
    db = await get_db()
    existing = await db.execute(
        "SELECT id FROM watch_items WHERE underlying = ? AND state = 'WATCHING'",
        (underlying,),
    )
    row = await existing.fetchone()
    if row:
        await db.execute(
            """UPDATE watch_items SET score = ?, failing_checks = ?,
               promoting_condition = ?, cycles_remaining = ?, cycle_id = ?
               WHERE id = ?""",
            (
                score, json.dumps(failing_checks), promoting_condition,
                settings.WATCH_EXPIRY_CYCLES, cycle_id, row["id"],
            ),
        )
        await db.commit()
        return row["id"]
    else:
        cur = await db.execute(
            """INSERT INTO watch_items (
                created_ts, underlying, strategy, score, failing_checks,
                promoting_condition, expiry_after_cycles, cycles_remaining,
                state, cycle_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'WATCHING', ?)""",
            (
                _now(), underlying, strategy, score, json.dumps(failing_checks),
                promoting_condition, settings.WATCH_EXPIRY_CYCLES,
                settings.WATCH_EXPIRY_CYCLES, cycle_id,
            ),
        )
        await db.commit()
        return cur.lastrowid


async def expire_watch_items(cycle_id: str) -> list[dict]:
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM watch_items WHERE state = 'WATCHING' AND cycles_remaining <= 0"
    )
    to_expire = [dict(r) for r in await cur.fetchall()]
    if to_expire:
        ids = [r["id"] for r in to_expire]
        placeholders = ",".join("?" * len(ids))
        await db.execute(
            f"UPDATE watch_items SET state = 'EXPIRED', resolved_ts = ? WHERE id IN ({placeholders})",
            [_now()] + ids,
        )
        await db.commit()
    return to_expire


async def promote_watch_item(item_id: int, cycle_id: str) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE watch_items SET state = 'PROMOTED', resolved_ts = ?, cycle_id = ? WHERE id = ?",
        (_now(), cycle_id, item_id),
    )
    await db.commit()


async def decrement_watch_cycles(cycle_id: str) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE watch_items SET cycles_remaining = cycles_remaining - 1 WHERE state = 'WATCHING'"
    )
    await db.commit()


async def get_watch_items(state: Optional[str] = None) -> list[dict]:
    db = await get_db()
    if state:
        cur = await db.execute(
            "SELECT * FROM watch_items WHERE state = ? ORDER BY id DESC", (state,)
        )
    else:
        cur = await db.execute("SELECT * FROM watch_items ORDER BY id DESC")
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


# --- Positions ---

async def insert_position(
    underlying: str,
    strategy: str,
    short_symbol: str,
    long_symbol: str,
    qty: int,
    credit_received: float,
    spread_width: float,
    max_loss: float,
    profit_target: float,
    stop_loss_level: float,
    expiry: str,
    dte_at_entry: int,
    client_order_id: str,
    alpaca_order_id: Optional[str] = None,
    strategy_type: str = "CREDIT",
    debit_paid: Optional[float] = None,
    max_reward: Optional[float] = None,
) -> int:
    db = await get_db()
    cur = await db.execute(
        """INSERT INTO positions (
            opened_ts, underlying, strategy, short_symbol, long_symbol,
            qty, credit_received, spread_width, max_loss, profit_target,
            stop_loss_level, expiry, dte_at_entry, alpaca_order_id,
            client_order_id, state, strategy_type, debit_paid, max_reward
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?)""",
        (
            _now(), underlying, strategy, short_symbol, long_symbol,
            qty, credit_received, spread_width, max_loss, profit_target,
            stop_loss_level, expiry, dte_at_entry, alpaca_order_id,
            client_order_id, strategy_type, debit_paid, max_reward,
        ),
    )
    await db.commit()
    return cur.lastrowid


async def update_position_state(
    client_order_id: str,
    state: str,
    pnl: Optional[float] = None,
    reason: Optional[str] = None,
) -> None:
    db = await get_db()
    await db.execute(
        """UPDATE positions SET state = ?, closed_ts = ?, close_pnl = ?, close_reason = ?
           WHERE client_order_id = ?""",
        (state, _now(), pnl, reason, client_order_id),
    )
    await db.commit()


async def get_open_positions_db() -> list[dict]:
    db = await get_db()
    cur = await db.execute("SELECT * FROM positions WHERE state = 'OPEN' ORDER BY id DESC")
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_position_by_client_order_id(client_order_id: str) -> Optional[dict]:
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM positions WHERE client_order_id = ?", (client_order_id,)
    )
    row = await cur.fetchone()
    return dict(row) if row else None


# --- IV History ---

async def insert_iv_history(
    underlying: str, atm_iv: float, realized_vol_20d: Optional[float] = None
) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO iv_history (ts, underlying, atm_iv, realized_vol_20d) VALUES (?, ?, ?, ?)",
        (_now(), underlying, atm_iv, realized_vol_20d),
    )
    await db.commit()


async def get_iv_history(underlying: str, days: int = 3) -> list[dict]:
    db = await get_db()
    cur = await db.execute(
        """SELECT * FROM iv_history WHERE underlying = ?
           ORDER BY id DESC LIMIT ?""",
        (underlying, days),
    )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


# --- Baselines ---

async def insert_baseline_record(
    cycle_id: str,
    baseline_type: str,
    underlying: str,
    action: str,
    details: dict,
) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO baseline_records (ts, cycle_id, baseline_type, underlying, action, details) VALUES (?, ?, ?, ?, ?, ?)",
        (_now(), cycle_id, baseline_type, underlying, action, json.dumps(details)),
    )
    await db.commit()


async def get_baseline_records(
    baseline_type: Optional[str] = None, underlying: Optional[str] = None
) -> list[dict]:
    db = await get_db()
    conditions = []
    params = []
    if baseline_type:
        conditions.append("baseline_type = ?")
        params.append(baseline_type)
    if underlying:
        conditions.append("underlying = ?")
        params.append(underlying)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    cur = await db.execute(
        f"SELECT * FROM baseline_records {where} ORDER BY id DESC", params
    )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


# --- Circuit Breaker ---

async def init_circuit_breaker(today: str, starting_equity: float) -> None:
    db = await get_db()
    await db.execute(
        """INSERT OR IGNORE INTO circuit_breaker (date, order_attempts, starting_equity, halted)
           VALUES (?, 0, ?, 0)""",
        (today, starting_equity),
    )
    await db.commit()


async def get_circuit_breaker(today: str) -> Optional[dict]:
    db = await get_db()
    cur = await db.execute("SELECT * FROM circuit_breaker WHERE date = ?", (today,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def increment_order_attempts(today: str) -> int:
    db = await get_db()
    await db.execute(
        "UPDATE circuit_breaker SET order_attempts = order_attempts + 1 WHERE date = ?",
        (today,),
    )
    await db.commit()
    cur = await db.execute(
        "SELECT order_attempts FROM circuit_breaker WHERE date = ?", (today,)
    )
    row = await cur.fetchone()
    return row["order_attempts"] if row else 0


async def halt_circuit_breaker(today: str, reason: str) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE circuit_breaker SET halted = 1, halt_reason = ? WHERE date = ?",
        (reason, today),
    )
    await db.commit()
    logger.warning("CIRCUIT BREAKER HALTED: %s", reason)
