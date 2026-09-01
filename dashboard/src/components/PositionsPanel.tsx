import React from 'react'
import type { Position } from '../types'

function computeDte(expiry: string): number {
  const exp = new Date(expiry)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return Math.round((exp.getTime() - today.getTime()) / 86400000)
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
  table: { width: '100%', borderCollapse: 'collapse' as const, fontSize: 11 },
  th: {
    textAlign: 'left' as const,
    color: '#64748b',
    padding: '4px 8px',
    borderBottom: '1px solid #1e1e2e',
    fontSize: 10,
    letterSpacing: 1,
  },
  td: { padding: '6px 8px', borderBottom: '1px solid #1a1a2e' },
  empty: { color: '#64748b', fontSize: 12, padding: 8 },
}

function pnlColor(pnl: number | null): string {
  if (pnl === null) return '#e2e8f0'
  if (pnl > 0) return '#22c55e'
  if (pnl < 0) return '#ef4444'
  return '#e2e8f0'
}

export default function PositionsPanel({ positions }: { positions: Position[] }) {
  const open = positions.filter((p) => p.state === 'OPEN')

  return (
    <div style={s.panel}>
      <div style={s.title}>OPEN POSITIONS ({open.length})</div>
      {open.length === 0 ? (
        <div style={s.empty}>No open positions.</div>
      ) : (
        <table style={s.table}>
          <thead>
            <tr>
              {['Underlying', 'Strategy', 'Credit', 'P-Target', 'Stop', 'DTE', 'Expiry', 'Status'].map((h) => (
                <th key={h} style={s.th}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {open.map((pos) => {
              const dte = computeDte(pos.expiry)
              const nearStop = false // would need live marks
              return (
                <tr key={pos.id} style={{ background: dte <= 2 ? '#1e1a0a' : 'transparent' }}>
                  <td style={{ ...s.td, fontWeight: 'bold', color: '#f59e0b' }}>{pos.underlying}</td>
                  <td style={s.td}>{pos.strategy}</td>
                  <td style={{ ...s.td, color: '#22c55e' }}>${pos.credit_received.toFixed(2)}</td>
                  <td style={s.td}>${pos.profit_target.toFixed(2)}</td>
                  <td style={s.td}>${pos.stop_loss_level.toFixed(2)}</td>
                  <td style={{ ...s.td, color: dte <= 2 ? '#ef4444' : '#e2e8f0' }}>{dte}d</td>
                  <td style={{ ...s.td, color: '#64748b' }}>{pos.expiry}</td>
                  <td style={{ ...s.td, color: '#22c55e' }}>OPEN</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
