-- events: every pipeline stage event
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    cycle_id TEXT NOT NULL,
    underlying TEXT,
    stage TEXT NOT NULL,
    payload TEXT NOT NULL
);

-- decisions: one row per evaluated opportunity
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    cycle_id TEXT NOT NULL,
    underlying TEXT NOT NULL,
    volatility_condition TEXT,
    trend_condition TEXT,
    selected_strategy TEXT,
    opportunity_score INTEGER,
    checks_json TEXT,
    outcome TEXT NOT NULL,
    reject_reason TEXT,
    risk_gate_result TEXT,
    risk_gate_reason TEXT,
    order_id TEXT,
    credit_received REAL,
    spread_width REAL,
    breakeven REAL,
    max_loss REAL,
    dte INTEGER,
    short_strike REAL,
    long_strike REAL,
    expiry TEXT,
    short_symbol TEXT,
    long_symbol TEXT
);

-- watch_items: stateful WATCH tracking
CREATE TABLE IF NOT EXISTS watch_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_ts TEXT NOT NULL,
    underlying TEXT NOT NULL,
    strategy TEXT NOT NULL,
    score INTEGER NOT NULL,
    failing_checks TEXT NOT NULL,
    promoting_condition TEXT NOT NULL,
    expiry_after_cycles INTEGER NOT NULL,
    cycles_remaining INTEGER NOT NULL,
    state TEXT NOT NULL DEFAULT 'WATCHING',
    resolved_ts TEXT,
    cycle_id TEXT NOT NULL
);

-- positions: tracked open positions
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opened_ts TEXT NOT NULL,
    underlying TEXT NOT NULL,
    strategy TEXT NOT NULL,
    short_symbol TEXT NOT NULL,
    long_symbol TEXT NOT NULL,
    qty INTEGER NOT NULL,
    credit_received REAL NOT NULL,
    spread_width REAL NOT NULL,
    max_loss REAL NOT NULL,
    profit_target REAL NOT NULL,
    stop_loss_level REAL NOT NULL,
    expiry TEXT NOT NULL,
    dte_at_entry INTEGER NOT NULL,
    alpaca_order_id TEXT,
    client_order_id TEXT UNIQUE,
    state TEXT NOT NULL DEFAULT 'OPEN',
    closed_ts TEXT,
    close_pnl REAL,
    close_reason TEXT
);

-- baselines: unfiltered and passive baseline records
CREATE TABLE IF NOT EXISTS baseline_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    cycle_id TEXT NOT NULL,
    baseline_type TEXT NOT NULL,
    underlying TEXT NOT NULL,
    action TEXT,
    details TEXT
);

-- iv_history: store ATM IV readings for 3-day avg calculation
CREATE TABLE IF NOT EXISTS iv_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    underlying TEXT NOT NULL,
    atm_iv REAL NOT NULL,
    realized_vol_20d REAL
);

-- circuit_breaker: daily state
CREATE TABLE IF NOT EXISTS circuit_breaker (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    order_attempts INTEGER NOT NULL DEFAULT 0,
    starting_equity REAL,
    halted INTEGER NOT NULL DEFAULT 0,
    halt_reason TEXT
);
