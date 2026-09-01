import React from 'react'
import type { Decision } from '../types'
import { Badge, OUTCOME_TONE, Tone } from './ui'

/** Volatility regime tone. CHEAP favours buying premium, RICH favours selling;
 *  FAIR is the "no edge either way" middle. */
const REGIME_TONE: Record<string, Tone> = {
  CHEAP: 'good',
  FAIR: 'neutral',
  RICH: 'warning',
  ELEVATED: 'warning',
  DEPRESSED: 'neutral',
}

const TREND_GLYPH: Record<string, string> = {
  UP: '↑',
  DOWN: '↓',
  RANGE: '↔',
}

/** Reads the most recent decision per underlying rather than replaying the raw
 *  event stream — the old version could show a strategy from an older cycle
 *  than the one displayed beside it. */
export default function RegimePanel({ decisions }: { decisions: Decision[] }) {
  const latest = new Map<string, Decision>()
  for (const d of decisions) {
    const prev = latest.get(d.underlying)
    if (!prev || new Date(d.ts) > new Date(prev.ts)) latest.set(d.underlying, d)
  }
  const rows = [...latest.values()].sort((a, b) =>
    a.underlying.localeCompare(b.underlying)
  )

  return (
    <div className="table-scroll">
      <table className="table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Volatility</th>
            <th>Trend</th>
            <th>Selected</th>
            <th style={{ textAlign: 'right' }}>Score</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((d) => (
            <tr key={d.underlying}>
              <td className="mono" style={{ fontWeight: 700 }}>{d.underlying}</td>
              <td>
                <Badge tone={REGIME_TONE[d.volatility_condition ?? ''] ?? 'neutral'}>
                  {d.volatility_condition ?? '—'}
                </Badge>
              </td>
              <td>
                <span aria-hidden="true" style={{ marginRight: 4 }}>
                  {TREND_GLYPH[d.trend_condition ?? ''] ?? ''}
                </span>
                {d.trend_condition ?? '—'}
              </td>
              <td style={{ fontSize: 11 }}>{d.selected_strategy ?? '—'}</td>
              <td style={{ textAlign: 'right' }}>
                <Badge tone={OUTCOME_TONE[d.outcome] ?? 'neutral'} dot={false}>
                  {d.opportunity_score ?? '—'}
                </Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
