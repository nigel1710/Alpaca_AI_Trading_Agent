import React from 'react'
import type { Event } from '../types'

const STAGES = [
  { key: 'MARKET_SCAN', label: 'Scan' },
  { key: 'MARKET_ANALYSIS', label: 'Analyse' },
  { key: 'STRATEGY_SELECTION', label: 'Select' },
  { key: 'OPPORTUNITY_EVALUATION', label: 'Score' },
  { key: 'RISK_REVIEW', label: 'Risk gate' },
  { key: 'FINAL_DECISION', label: 'Decision' },
]

function formatTime(ts: string): string {
  try {
    return new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/New_York',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(new Date(ts))
  } catch {
    return ts
  }
}

function summarise(stage: string, payload: Record<string, unknown>): string {
  if (stage === 'FINAL_DECISION') return String(payload.outcome ?? '')
  if (stage === 'OPPORTUNITY_EVALUATION') return `${payload.score} · ${payload.outcome}`
  if (stage === 'STRATEGY_SELECTION') return String(payload.strategy ?? '')
  if (stage === 'MARKET_ANALYSIS') {
    return `${payload.vol_regime ?? payload.vol_condition ?? ''} / ${payload.trend_condition ?? ''}`
  }
  if (stage === 'RISK_REVIEW') return payload.approved ? 'approved' : 'rejected'
  return ''
}

export default function PipelinePanel({ pipeline }: { pipeline: Record<string, Event[]> }) {
  const cycleIds = Object.keys(pipeline)

  return (
    <div style={{ display: 'grid', gap: 18 }}>
      {cycleIds.map((cycleId) => {
        const events = pipeline[cycleId]
        const present = new Set(events.map((e) => e.stage))
        const latestFor = (stage: string) => {
          const list = events.filter((e) => e.stage === stage)
          return list[list.length - 1]
        }

        return (
          <div key={cycleId}>
            <div
              className="mono"
              style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 7 }}
            >
              cycle {cycleId}
            </div>
            <ol
              style={{
                display: 'flex',
                gap: 6,
                listStyle: 'none',
                margin: 0,
                padding: 0,
                overflowX: 'auto',
              }}
            >
              {STAGES.map((stage) => {
                const done = present.has(stage.key)
                const ev = latestFor(stage.key)
                return (
                  <li
                    key={stage.key}
                    style={{
                      flex: '1 1 0',
                      minWidth: 96,
                      padding: '8px 10px',
                      borderRadius: 'var(--radius-sm)',
                      background: done ? 'var(--surface-2)' : 'transparent',
                      border: `1px solid ${done ? 'var(--border)' : 'transparent'}`,
                      borderTop: `2px solid ${done ? 'var(--good)' : 'var(--border-firm)'}`,
                      opacity: done ? 1 : 0.45,
                    }}
                  >
                    <div style={{ fontSize: 11, fontWeight: 600 }}>{stage.label}</div>
                    {ev && (
                      <>
                        <div
                          style={{
                            fontSize: 10,
                            color: 'var(--text-secondary)',
                            marginTop: 3,
                            wordBreak: 'break-word',
                          }}
                        >
                          {summarise(stage.key, ev.payload)}
                        </div>
                        <div
                          className="mono"
                          style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 3 }}
                        >
                          {formatTime(ev.ts)}
                        </div>
                      </>
                    )}
                  </li>
                )
              })}
            </ol>
          </div>
        )
      })}
    </div>
  )
}
