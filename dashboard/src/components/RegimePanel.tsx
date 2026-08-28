import React from 'react'
import type { Event } from '../types'

interface RegimeData {
  underlying: string
  vol_condition: string | null
  trend_condition: string | null
  vol_ratio: number | null
  separation_pct: number | null
  strategy: string | null
  score: number | null
  ts: string | null
}

function extractRegime(events: Event[]): Record<string, RegimeData> {
  const regime: Record<string, RegimeData> = {}

  for (const e of events) {
    if (!e.underlying) continue
    const sym = e.underlying

    if (e.stage === 'MARKET_ANALYSIS') {
      const p = e.payload as Record<string, unknown>
      if (!regime[sym]) {
        regime[sym] = { underlying: sym, vol_condition: null, trend_condition: null, vol_ratio: null, separation_pct: null, strategy: null, score: null, ts: null }
      }
      regime[sym].vol_condition = (p.vol_condition as string) || null
      regime[sym].trend_condition = (p.trend_condition as string) || null
      regime[sym].vol_ratio = p.vol_ratio != null ? Number(p.vol_ratio) : null
      regime[sym].separation_pct = p.separation_pct != null ? Number(p.separation_pct) : null
      regime[sym].ts = e.ts
    }

    if (e.stage === 'STRATEGY_SELECTION') {
      const p = e.payload as Record<string, unknown>
      if (!regime[sym]) {
        regime[sym] = { underlying: sym, vol_condition: null, trend_condition: null, vol_ratio: null, separation_pct: null, strategy: null, score: null, ts: null }
      }
      regime[sym].strategy = (p.strategy as string) || null
    }

    if (e.stage === 'OPPORTUNITY_EVALUATION') {
      const p = e.payload as Record<string, unknown>
      if (!regime[sym]) {
        regime[sym] = { underlying: sym, vol_condition: null, trend_condition: null, vol_ratio: null, separation_pct: null, strategy: null, score: null, ts: null }
      }
      regime[sym].score = p.score != null ? Number(p.score) : null
    }
  }

  return regime
}

const s: Record<string, React.CSSProperties> = {
  panel: {
    background: '#12121a',
    border: '1px solid #1e1e2e',
    borderRadius: 6,
    padding: 16,
    marginBottom: 16,
  },
  title: { fontSize: 11, color: '#64748b', letterSpacing: 2, marginBottom: 12 },
  row: {
    display: 'flex',
    alignItems: 'center',
    gap: 16,
    padding: '8px 0',
    borderBottom: '1px solid #1a1a2e',
    fontSize: 11,
  },
  sym: { fontWeight: 'bold', color: '#f59e0b', minWidth: 40 },
  tag: (val: string): React.CSSProperties => ({
    padding: '2px 6px',
    borderRadius: 3,
    fontSize: 10,
    background:
      val === 'ELEVATED' || val === 'UP'
        ? '#1a2e1a'
        : val === 'DEPRESSED' || val === 'DOWN'
        ? '#2e1a1a'
        : '#1a1a2e',
    color:
      val === 'ELEVATED' || val === 'UP'
        ? '#22c55e'
        : val === 'DEPRESSED' || val === 'DOWN'
        ? '#ef4444'
        : '#94a3b8',
  }),
  num: { color: '#64748b' },
  strategy: { color: '#93c5fd', fontSize: 10 },
  score: (v: number): React.CSSProperties => ({
    color: v >= 80 ? '#22c55e' : v >= 60 ? '#f59e0b' : '#ef4444',
    fontWeight: 'bold',
  }),
}

export default function RegimePanel({ events }: { events: Event[] }) {
  const regime = extractRegime(events)
  const symbols = Object.keys(regime)

  return (
    <div style={s.panel}>
      <div style={s.title}>REGIME READINGS</div>
      {symbols.length === 0 && (
        <div style={{ color: '#64748b', fontSize: 12 }}>No regime data yet.</div>
      )}
      {symbols.map((sym) => {
        const r = regime[sym]
        return (
          <div key={sym} style={s.row}>
            <span style={s.sym}>{sym}</span>
            {r.vol_condition && (
              <span>
                <span style={s.tag(r.vol_condition)}>{r.vol_condition}</span>
                {r.vol_ratio && <span style={s.num}> ({r.vol_ratio.toFixed(2)}x)</span>}
              </span>
            )}
            {r.trend_condition && (
              <span>
                <span style={s.tag(r.trend_condition)}>{r.trend_condition}</span>
                {r.separation_pct != null && (
                  <span style={s.num}> ({(r.separation_pct * 100).toFixed(3)}% sep)</span>
                )}
              </span>
            )}
            {r.strategy && <span style={s.strategy}>{r.strategy}</span>}
            {r.score != null && <span style={s.score(r.score)}>{r.score}/100</span>}
          </div>
        )
      })}
    </div>
  )
}
