import React from 'react'
import type { Decision, CheckResult } from '../types'

const OUTCOME_COLORS: Record<string, string> = {
  TRADE: '#22c55e',
  WATCH: '#f59e0b',
  REJECT: '#ef4444',
  EXPIRED: '#64748b',
  STAND_ASIDE: '#64748b',
}

const CONFIDENCE_COLORS: Record<string, string> = {
  HIGH: '#22c55e',
  MEDIUM: '#f59e0b',
  LOW: '#64748b',
}

const s: Record<string, any> = {
  card: (outcome: string): React.CSSProperties => ({
    background: '#12121a',
    border: `1px solid ${OUTCOME_COLORS[outcome] || '#1e1e2e'}`,
    borderRadius: 6,
    padding: 14,
    marginBottom: 10,
    fontSize: 11,
  }),
  header: { display: 'flex', justifyContent: 'space-between', marginBottom: 8 },
  underlying: { fontSize: 14, fontWeight: 'bold', color: '#f59e0b' },
  outcome: (o: string): React.CSSProperties => ({
    fontSize: 12,
    fontWeight: 'bold',
    color: OUTCOME_COLORS[o] || '#e2e8f0',
    padding: '2px 8px',
    border: `1px solid ${OUTCOME_COLORS[o] || '#1e1e2e'}`,
    borderRadius: 3,
  }),
  meta: { color: '#64748b', fontSize: 10, marginBottom: 8 },
  section: { marginBottom: 8 },
  sectionTitle: { color: '#64748b', fontSize: 9, letterSpacing: 1, marginBottom: 4 },
  score: (s: number): React.CSSProperties => ({
    color: s >= 80 ? '#22c55e' : s >= 60 ? '#f59e0b' : '#ef4444',
    fontWeight: 'bold',
    fontSize: 16,
  }),
  checkRow: (passed: boolean): React.CSSProperties => ({
    display: 'flex',
    justifyContent: 'space-between',
    padding: '2px 0',
    color: passed ? '#94a3b8' : '#ef4444',
  }),
  checkName: { flex: 1 },
  checkPts: { color: '#64748b', marginLeft: 8 },
  detail: { color: '#94a3b8', marginRight: 12 },
  reject: { color: '#ef4444', fontSize: 10, marginTop: 4 },
  riskGate: (approved: boolean): React.CSSProperties => ({
    color: approved ? '#22c55e' : '#ef4444',
    fontSize: 10,
    marginTop: 4,
  }),
  rationale: {
    color: '#94a3b8',
    fontSize: 10,
    fontStyle: 'italic',
    marginBottom: 8,
    lineHeight: 1.4,
  },
  confidence: (level: string): React.CSSProperties => ({
    marginLeft: 10,
    fontSize: 9,
    fontWeight: 'bold',
    letterSpacing: 1,
    color: CONFIDENCE_COLORS[level] || '#64748b',
    border: `1px solid ${CONFIDENCE_COLORS[level] || '#64748b'}`,
    borderRadius: 3,
    padding: '1px 6px',
  }),
  rr: {
    color: '#22c55e',
    fontWeight: 'bold',
    fontSize: 12,
  },
  whyNot: {
    color: '#94a3b8',
    fontSize: 10,
    lineHeight: 1.4,
  },
}

function formatTs(ts: string): string {
  try {
    return new Date(ts).toLocaleString()
  } catch {
    return ts
  }
}

interface Props {
  decision: Decision
}

export default function DecisionCardComponent({ decision }: Props) {
  return (
    <div style={s.card(decision.outcome)}>
      <div style={s.header}>
        <span style={s.underlying}>{decision.underlying}</span>
        <span style={s.outcome(decision.outcome)}>{decision.outcome}</span>
      </div>

      <div style={s.meta}>
        {formatTs(decision.ts)} | cycle: {decision.cycle_id} |{' '}
        {decision.volatility_condition} / {decision.trend_condition} | {decision.selected_strategy}
        {decision.strategy_type ? ` (${decision.strategy_type})` : ''}
      </div>

      {decision.strategy_rationale && (
        <div style={s.rationale}>{decision.strategy_rationale}</div>
      )}

      {decision.opportunity_score !== null && (
        <div style={s.section}>
          <div style={s.sectionTitle}>OPPORTUNITY SCORE</div>
          <span style={s.score(decision.opportunity_score)}>{decision.opportunity_score}/100</span>
          {decision.confidence && (
            <span style={s.confidence(decision.confidence)}>
              {decision.confidence} CONFIDENCE
            </span>
          )}
        </div>
      )}

      {decision.strategy_type === 'DEBIT' && decision.reward_risk !== null && (
        <div style={s.section}>
          <div style={s.sectionTitle}>ASYMMETRY</div>
          <div>
            <span style={s.detail}>
              Risk: ${decision.debit_paid !== null ? (decision.debit_paid * 100).toFixed(0) : '—'}
            </span>
            <span style={s.detail}>
              Reward: ${decision.max_reward !== null ? decision.max_reward.toFixed(0) : '—'}
            </span>
            <span style={s.rr}>R:R {decision.reward_risk.toFixed(2)} : 1</span>
          </div>
          {decision.required_move_pct !== null && decision.expected_move_pct !== null && (
            <div style={{ marginTop: 3 }}>
              <span style={s.detail}>
                Required move: {(decision.required_move_pct * 100).toFixed(2)}%
              </span>
              <span style={s.detail}>
                Expected move: ±{(decision.expected_move_pct * 100).toFixed(2)}%
              </span>
            </div>
          )}
        </div>
      )}

      {decision.checks && decision.checks.length > 0 && (
        <div style={s.section}>
          <div style={s.sectionTitle}>CHECKS</div>
          {decision.checks.map((c: CheckResult) => (
            <div key={c.check_num} style={s.checkRow(c.passed)}>
              <span style={s.checkName}>
                {c.passed ? '✓' : '✗'} {c.check_num}. {c.name}
              </span>
              <span style={{ color: '#64748b', fontSize: 9 }}>{c.note}</span>
              <span style={s.checkPts}>
                {c.points_earned}/{c.points_possible}
              </span>
            </div>
          ))}
        </div>
      )}

      {decision.outcome === 'TRADE' && (
        <div style={s.section}>
          <div style={s.sectionTitle}>POSITION DETAILS</div>
          <div>
            {decision.strategy_type === 'DEBIT' ? (
              <span style={s.detail}>Debit: ${decision.debit_paid?.toFixed(2)}</span>
            ) : (
              <span style={s.detail}>Credit: ${decision.credit_received?.toFixed(2)}</span>
            )}
            <span style={s.detail}>Width: ${decision.spread_width?.toFixed(2)}</span>
            <span style={s.detail}>MaxLoss: ${decision.max_loss?.toFixed(2)}</span>
            <span style={s.detail}>DTE: {decision.dte}d</span>
            <span style={s.detail}>Expiry: {decision.expiry}</span>
          </div>
          <div>
            <span style={s.detail}>Short: {decision.short_symbol} @{decision.short_strike}</span>
            <span style={s.detail}>Long: {decision.long_symbol} @{decision.long_strike}</span>
          </div>
          {decision.order_id && (
            <div style={{ color: '#64748b', fontSize: 9, marginTop: 2 }}>
              Order: {decision.order_id}
            </div>
          )}
        </div>
      )}

      {decision.risk_gate_result && (
        <div style={s.riskGate(decision.risk_gate_result === 'APPROVED')}>
          Risk Gate: {decision.risk_gate_result} — {decision.risk_gate_reason}
        </div>
      )}

      {decision.reject_reason && (
        <div style={s.reject}>↳ {decision.reject_reason}</div>
      )}

      {decision.why_not?.rejected_alternative && (
        <div style={s.section}>
          <div style={s.sectionTitle}>WHY NOT THE OTHER SIDE?</div>
          <div style={s.whyNot}>{decision.why_not.rejected_alternative}</div>
        </div>
      )}
    </div>
  )
}
