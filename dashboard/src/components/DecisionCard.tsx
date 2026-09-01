import React, { useState } from 'react'
import type { Decision, CheckResult } from '../types'
import {
  Badge, Meter, OUTCOME_TONE, CONFIDENCE_TONE, fmtMoney, fmtPct,
} from './ui'

function formatTs(ts: string): string {
  try {
    return new Date(ts).toLocaleString(undefined, {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return ts
  }
}

/** Risk vs reward as a single proportional bar — the asymmetry the strategy is
 *  built around, readable without doing arithmetic. */
function RiskRewardBar({ risk, reward }: { risk: number; reward: number }) {
  const total = risk + reward
  if (!(total > 0)) return null
  const riskPct = (risk / total) * 100
  return (
    <div
      className="rr-bar"
      role="img"
      aria-label={`Risk ${fmtMoney(risk, 0)}, maximum reward ${fmtMoney(reward, 0)}`}
    >
      <div className="rr-seg rr-risk" style={{ width: `${riskPct}%` }}>
        {riskPct > 18 ? `risk ${fmtMoney(risk, 0)}` : ''}
      </div>
      <div className="rr-seg rr-reward" style={{ width: `${100 - riskPct}%` }}>
        {100 - riskPct > 18 ? `reward ${fmtMoney(reward, 0)}` : ''}
      </div>
    </div>
  )
}

function Checks({ checks }: { checks: CheckResult[] }) {
  return (
    <div>
      {checks.map((c) => (
        <div
          key={c.check_num}
          className={`check ${c.passed ? 'check-pass' : 'check-fail'}`}
        >
          <span className="check-icon" aria-hidden="true">{c.passed ? '✓' : '✗'}</span>
          <span className="check-name">
            {c.check_num}. {c.name}
            <span className="sr-only">{c.passed ? ' passed' : ' failed'}</span>
          </span>
          <span className="check-pts">
            {c.points_earned}/{c.points_possible}
          </span>
          <span className="check-note">{c.note}</span>
        </div>
      ))}
    </div>
  )
}

export default function DecisionCardComponent({
  decision,
  defaultOpen = false,
}: {
  decision: Decision
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)

  const tone = OUTCOME_TONE[decision.outcome] ?? 'neutral'
  const score = decision.opportunity_score
  const isDebit = decision.strategy_type === 'DEBIT'
  const risk = isDebit && decision.debit_paid !== null ? decision.debit_paid * 100 : decision.max_loss
  const reward = isDebit ? decision.max_reward : (decision.credit_received ?? 0) * 100

  const required = decision.required_move_pct
  const expected = decision.expected_move_pct

  return (
    <article className="dcard" style={{ ['--edge' as any]: `var(--${tone})` }}>
      <button
        className="dcard-head"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span className={`chev ${open ? 'open' : ''}`} aria-hidden="true">▶</span>
        <span className="dcard-sym">{decision.underlying}</span>
        <span className="dcard-strategy">
          {decision.selected_strategy}
          {decision.volatility_condition ? ` · ${decision.volatility_condition}` : ''}
        </span>
        <span className="dcard-spacer" />
        {score !== null && <span className="dcard-score">{score}</span>}
        {decision.confidence && (
          <Badge tone={CONFIDENCE_TONE[decision.confidence] ?? 'neutral'} dot={false}>
            {decision.confidence}
          </Badge>
        )}
        <Badge tone={tone}>{decision.outcome.replace('_', ' ')}</Badge>
      </button>

      {open && (
        <div className="dcard-body">
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }} className="mono">
            {formatTs(decision.ts)} · cycle {decision.cycle_id} · {decision.trend_condition}
          </div>

          {decision.strategy_rationale && (
            <p className="rationale">{decision.strategy_rationale}</p>
          )}

          {isDebit && risk && reward ? (
            <>
              <div className="section-label">Risk / reward</div>
              <RiskRewardBar risk={risk} reward={reward} />
              {decision.reward_risk !== null && (
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 6 }}>
                  <strong className="tnum">{decision.reward_risk.toFixed(2)} : 1</strong>{' '}
                  reward-to-risk
                </div>
              )}
            </>
          ) : null}

          {required !== null && expected !== null && expected > 0 && (
            <>
              <div className="section-label">Move needed vs expected</div>
              <Meter
                label={`Needs ${fmtPct(required)} · expects ±${fmtPct(expected)}`}
                valueText={`${((required / expected) * 100).toFixed(0)}% of expected move`}
                fraction={required / expected}
                tone={required / expected <= 0.8 ? 'good' : 'critical'}
              />
            </>
          )}

          {decision.checks?.length > 0 && (
            <>
              <div className="section-label">
                Checklist ({decision.checks.filter((c) => c.passed).length}/
                {decision.checks.length} passed)
              </div>
              <Checks checks={decision.checks} />
            </>
          )}

          {(decision.expiry || decision.short_symbol) && (
            <>
              <div className="section-label">Structure</div>
              <div className="kv">
                <div className="kv-item">
                  <div className="kv-k">{isDebit ? 'Debit' : 'Credit'}</div>
                  <div className="kv-v">
                    {fmtMoney(isDebit ? decision.debit_paid : decision.credit_received)}
                  </div>
                </div>
                <div className="kv-item">
                  <div className="kv-k">Width</div>
                  <div className="kv-v">{fmtMoney(decision.spread_width)}</div>
                </div>
                <div className="kv-item">
                  <div className="kv-k">Max loss</div>
                  <div className="kv-v">{fmtMoney(decision.max_loss, 0)}</div>
                </div>
                <div className="kv-item">
                  <div className="kv-k">DTE</div>
                  <div className="kv-v">{decision.dte ?? '—'}</div>
                </div>
                <div className="kv-item">
                  <div className="kv-k">Expiry</div>
                  <div className="kv-v">{decision.expiry ?? '—'}</div>
                </div>
                <div className="kv-item">
                  <div className="kv-k">Long</div>
                  <div className="kv-v sym">{decision.long_symbol ?? '—'}</div>
                </div>
                <div className="kv-item">
                  <div className="kv-k">Short</div>
                  <div className="kv-v sym">{decision.short_symbol ?? '—'}</div>
                </div>
                {decision.order_id && (
                  <div className="kv-item">
                    <div className="kv-k">Order</div>
                    <div className="kv-v sym">{decision.order_id}</div>
                  </div>
                )}
              </div>
            </>
          )}

          {decision.risk_gate_result && (
            <div style={{ marginTop: 14 }}>
              <Badge tone={decision.risk_gate_result === 'APPROVED' ? 'good' : 'critical'}>
                Risk gate {decision.risk_gate_result.toLowerCase()}
              </Badge>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 5 }}>
                {decision.risk_gate_reason}
              </div>
            </div>
          )}

          {decision.reject_reason && (
            <>
              <div className="section-label">Why not traded</div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                {decision.reject_reason}
              </div>
            </>
          )}

          {decision.why_not?.rejected_alternative && (
            <>
              <div className="section-label">Why not the other structure</div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                {decision.why_not.rejected_alternative}
              </div>
            </>
          )}
        </div>
      )}
    </article>
  )
}
