import React from 'react'
import type { Event } from '../types'

const STAGES = [
  'MARKET_SCAN',
  'MARKET_ANALYSIS',
  'STRATEGY_SELECTION',
  'OPPORTUNITY_EVALUATION',
  'RISK_REVIEW',
  'FINAL_DECISION',
]

const STAGE_LABELS: Record<string, string> = {
  MARKET_SCAN: 'Market Scan',
  MARKET_ANALYSIS: 'Analysis',
  STRATEGY_SELECTION: 'Strategy',
  OPPORTUNITY_EVALUATION: 'Evaluation',
  RISK_REVIEW: 'Risk Gate',
  FINAL_DECISION: 'Decision',
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
  cycleRow: { marginBottom: 12 },
  cycleId: { fontSize: 10, color: '#64748b', marginBottom: 6 },
  stages: { display: 'flex', gap: 4, flexWrap: 'wrap' as const },
  stage: (active: boolean, done: boolean): React.CSSProperties => ({
    background: done ? '#1a2e1a' : active ? '#1e1e2e' : '#0d0d14',
    border: `1px solid ${done ? '#22c55e' : active ? '#3b82f6' : '#1e1e2e'}`,
    borderRadius: 4,
    padding: '6px 10px',
    fontSize: 10,
    color: done ? '#22c55e' : active ? '#93c5fd' : '#4b5563',
    minWidth: 80,
  }),
  stageName: { fontWeight: 'bold', marginBottom: 2 },
  stageUnderlying: { color: '#f59e0b', fontSize: 9 },
  stageTime: { fontSize: 9, color: '#64748b', marginTop: 2 },
  stagePayload: { fontSize: 9, color: '#94a3b8', marginTop: 2, maxWidth: 120, wordBreak: 'break-word' as const },
}

function formatTime(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString()
  } catch {
    return ts
  }
}

function getPayloadSummary(stage: string, payload: Record<string, unknown>): string {
  if (stage === 'FINAL_DECISION') return `→ ${payload.outcome}`
  if (stage === 'OPPORTUNITY_EVALUATION') return `Score: ${payload.score} | ${payload.outcome}`
  if (stage === 'STRATEGY_SELECTION') return String(payload.strategy || '')
  if (stage === 'MARKET_ANALYSIS') {
    return `${payload.vol_condition} / ${payload.trend_condition}`
  }
  if (stage === 'RISK_REVIEW') return payload.approved ? '✓ APPROVED' : '✗ REJECTED'
  return ''
}

interface Props {
  pipeline: Record<string, Event[]>
}

export default function PipelinePanel({ pipeline }: Props) {
  const cycleIds = Object.keys(pipeline)

  return (
    <div style={s.panel}>
      <div style={s.title}>DECISION PIPELINE</div>
      {cycleIds.length === 0 && (
        <div style={{ color: '#64748b', fontSize: 12 }}>Waiting for first scan cycle...</div>
      )}
      {cycleIds.map((cycleId) => {
        const events = pipeline[cycleId]
        const stageMap = new Map<string, Event[]>()
        for (const e of events) {
          const list = stageMap.get(e.stage) || []
          list.push(e)
          stageMap.set(e.stage, list)
        }
        const presentStages = new Set(events.map((e) => e.stage))

        return (
          <div key={cycleId} style={s.cycleRow}>
            <div style={s.cycleId}>cycle: {cycleId}</div>
            <div style={s.stages}>
              {STAGES.map((stage, i) => {
                const stageEvents = stageMap.get(stage) || []
                const done = presentStages.has(stage)
                const active = !done && STAGES.slice(0, i).every((s) => presentStages.has(s))
                const latestEvent = stageEvents[stageEvents.length - 1]
                const underlying = latestEvent?.underlying
                const payload = (latestEvent?.payload as Record<string, unknown>) || {}
                const summary = done ? getPayloadSummary(stage, payload) : ''

                return (
                  <div key={stage} style={s.stage(active, done)}>
                    <div style={s.stageName}>{STAGE_LABELS[stage]}</div>
                    {underlying && <div style={s.stageUnderlying}>{underlying}</div>}
                    {summary && <div style={s.stagePayload}>{summary}</div>}
                    {latestEvent && <div style={s.stageTime}>{formatTime(latestEvent.ts)}</div>}
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}
