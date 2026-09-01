import React from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import type { BaselineRecord } from '../types'

interface EquityPoint {
  ts: string
  agent?: number
  unfiltered?: number
  passive?: number
}

function buildChartData(
  baselines: BaselineRecord[],
  agentEquityHistory: { ts: string; equity: number }[]
): EquityPoint[] {
  const byTs: Record<string, EquityPoint> = {}

  for (const b of baselines) {
    const key = b.ts.slice(0, 16) // minute-level bucketing
    if (!byTs[key]) byTs[key] = { ts: key }
    const details = b.details as Record<string, unknown>
    if (b.baseline_type === 'PASSIVE' && b.underlying === 'SPY') {
      byTs[key].passive = details.pnl_pct != null ? Number(details.pnl_pct) : undefined
    }
    if (b.baseline_type === 'UNFILTERED') {
      // UNFILTERED baseline — track count of WOULD_TRADE vs total as proxy
    }
  }

  for (const pt of agentEquityHistory) {
    const key = pt.ts.slice(0, 16)
    if (!byTs[key]) byTs[key] = { ts: key }
    byTs[key].agent = pt.equity
  }

  return Object.values(byTs).sort((a, b) => a.ts.localeCompare(b.ts))
}

const s: Record<string, any> = {
  panel: {
    background: '#12121a',
    border: '1px solid #1e1e2e',
    borderRadius: 6,
    padding: 16,
    marginBottom: 16,
  },
  title: { fontSize: 11, color: '#64748b', letterSpacing: 2, marginBottom: 12 },
  empty: { color: '#64748b', fontSize: 12, padding: '24px 0', textAlign: 'center' as const },
}

interface Props {
  baselines: BaselineRecord[]
  agentEquityHistory?: { ts: string; equity: number }[]
}

export default function EquityCurve({ baselines, agentEquityHistory = [] }: Props) {
  const data = buildChartData(baselines, agentEquityHistory)

  if (data.length < 2) {
    return (
      <div style={s.panel}>
        <div style={s.title}>EQUITY CURVE</div>
        <div style={s.empty}>Insufficient data — accumulating history...</div>
      </div>
    )
  }

  return (
    <div style={s.panel}>
      <div style={s.title}>EQUITY CURVE</div>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
          <XAxis
            dataKey="ts"
            tick={{ fill: '#64748b', fontSize: 9 }}
            tickFormatter={(v) => v.slice(11, 16)}
          />
          <YAxis tick={{ fill: '#64748b', fontSize: 9 }} />
          <Tooltip
            contentStyle={{ background: '#12121a', border: '1px solid #1e1e2e', fontSize: 11 }}
            labelStyle={{ color: '#64748b' }}
          />
          <Legend wrapperStyle={{ fontSize: 10, color: '#64748b' }} />
          <Line
            type="monotone"
            dataKey="agent"
            name="Agent"
            stroke="#3b82f6"
            dot={false}
            strokeWidth={2}
          />
          <Line
            type="monotone"
            dataKey="passive"
            name="Passive (SPY)"
            stroke="#9ca3af"
            dot={false}
            strokeWidth={1}
            strokeDasharray="4 2"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
