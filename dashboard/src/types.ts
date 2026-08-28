export interface CheckResult {
  check_num: number
  name: string
  passed: boolean
  value: number | string | boolean
  threshold: number | string | boolean | null
  points_possible: number
  points_earned: number
  note: string
}

export interface Decision {
  id: number
  ts: string
  cycle_id: string
  underlying: string
  volatility_condition: string | null
  trend_condition: string | null
  selected_strategy: string | null
  opportunity_score: number | null
  checks: CheckResult[]
  outcome: 'TRADE' | 'WATCH' | 'REJECT' | 'EXPIRED'
  reject_reason: string | null
  risk_gate_result: string | null
  risk_gate_reason: string | null
  credit_received: number | null
  spread_width: number | null
  breakeven: number | null
  max_loss: number | null
  dte: number | null
  short_strike: number | null
  long_strike: number | null
  expiry: string | null
  short_symbol: string | null
  long_symbol: string | null
  order_id: string | null
}

export interface Position {
  id: number
  opened_ts: string
  underlying: string
  strategy: string
  short_symbol: string
  long_symbol: string
  qty: number
  credit_received: number
  spread_width: number
  max_loss: number
  profit_target: number
  stop_loss_level: number
  expiry: string
  dte_at_entry: number
  alpaca_order_id: string | null
  client_order_id: string
  state: string
  closed_ts: string | null
  close_pnl: number | null
  close_reason: string | null
}

export interface WatchItem {
  id: number
  created_ts: string
  underlying: string
  strategy: string
  score: number
  failing_checks: string[]
  promoting_condition: string
  expiry_after_cycles: number
  cycles_remaining: number
  state: 'WATCHING' | 'PROMOTED' | 'EXPIRED'
  resolved_ts: string | null
  cycle_id: string
}

export interface Event {
  id: number
  ts: string
  cycle_id: string
  underlying: string | null
  stage: string
  payload: Record<string, unknown>
}

export interface Account {
  equity: number
  buying_power: number
  cash: number
  portfolio_value: number
  currency?: string
}

export interface BaselineRecord {
  id: number
  ts: string
  cycle_id: string
  baseline_type: 'UNFILTERED' | 'PASSIVE'
  underlying: string
  action: string
  details: Record<string, unknown>
}

export interface CircuitBreaker {
  date: string
  order_attempts: number
  starting_equity: number | null
  halted: number
  halt_reason: string | null
}
