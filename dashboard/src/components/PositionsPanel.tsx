import React from 'react'
import type { Position } from '../types'
import { Badge, fmtMoney } from './ui'

export default function PositionsPanel({ positions }: { positions: Position[] }) {
  return (
    <div className="table-scroll">
      <table className="table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Structure</th>
            <th>Entry</th>
            <th>Width</th>
            <th>Max loss</th>
            <th>DTE</th>
            <th>Expiry</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => {
            const isDebit = p.strategy_type === 'DEBIT'
            return (
              <tr key={p.id}>
                <td className="mono" style={{ fontWeight: 700 }}>{p.underlying}</td>
                <td>
                  <Badge tone={isDebit ? 'good' : 'neutral'} dot={false}>
                    {p.strategy}
                  </Badge>
                </td>
                <td>
                  {isDebit
                    ? `−${fmtMoney(p.debit_paid)}`
                    : `+${fmtMoney(p.credit_received)}`}
                </td>
                <td>{fmtMoney(p.spread_width, 0)}</td>
                <td>{fmtMoney(p.max_loss, 0)}</td>
                <td>{p.dte_at_entry}</td>
                <td className="mono" style={{ fontSize: 11 }}>{p.expiry}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
