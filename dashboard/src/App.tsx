import React, { useState } from 'react'
import {
  useDecisions,
  usePositions,
  useWatchItems,
  useEvents,
  usePipelineLatest,
  useAccount,
  useBaselines,
  useCircuitBreaker,
} from './api'
import PipelinePanel from './components/PipelinePanel'
import PositionsPanel from './components/PositionsPanel'
import DecisionCardComponent from './components/DecisionCard'
import RegimePanel from './components/RegimePanel'
import EquityCurve from './components/EquityCurve'
import type { Decision } from './types'

const palette = {
  bg: '#0a0a0f',
  panel: '#12121a',
  border: '#1e1e2e',
  text: '#e2e8f0',
  muted: '#64748b',
  green: '#22c55e',
  red: '#ef4444',
  amber: '#f59e0b',
  blue: '#3b82f6',
}

const s: Record<string, React.CSSProperties> = {
  root: {
    background: palette.bg,
    color: palette.text,
    minHeight: '100vh',
    fontFamily: "'Courier New', monospace",
    padding: 16,
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '12px 16px',
    background: palette.panel,
    border: `1px solid ${palette.border}`,
    borderRadius: 6,
    marginBottom: 16,
  },
  headerTitle: { fontSize: 18, fontWeight: 'bold', color: palette.amber, letterSpacing: 2 },
  headerRight: { display: 'flex', gap: 24, alignItems: 'center', fontSize: 12 },
  badge: (live: boolean): React.CSSProperties => ({
    padding: '2px 8px',
    borderRadius: 3,
    background: live ? '#2e1a1a' : '#1a2e1a',
    color: live ? palette.red : palette.green,
    fontSize: 10,
    fontWeight: 'bold',
    border: `1px solid ${live ? palette.red : palette.green}`,
  }),
  equity: { color: palette.green, fontWeight: 'bold' },
  clock: { color: palette.muted },
  grid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 },
  leftCol: {},
  rightCol: {},
  sectionTitle: {
    fontSize: 11,
    color: palette.muted,
    letterSpacing: 2,
    marginBottom: 8,
    marginTop: 16,
  },
  cbHalt: {
    background: '#2e1a1a',
    border: `1px solid ${palette.red}`,
    borderRadius: 4,
    padding: '8px 12px',
    color: palette.red,
    fontSize: 11,
    marginBottom: 16,
  },
  watchPanel: {
    background: palette.panel,
    border: `1px solid ${palette.amber}`,
    borderRadius: 6,
    padding: 16,
    marginBottom: 16,
  },
  watchItem: {
    padding: '6px 0',
    borderBottom: `1px solid #1a1a2e`,
    fontSize: 11,
  },
}

function useNow(): string {
  const [now, setNow] = React.useState(new Date().toLocaleTimeString())
  React.useEffect(() => {
    const id = setInterval(() => setNow(new Date().toLocaleTimeString()), 1000)
    return () => clearInterval(id)
  }, [])
  return now
}

export default function App() {
  const account = useAccount()
  const decisions = useDecisions(100)
  const positions = usePositions()
  const watchItems = useWatchItems('WATCHING')
  const events = useEvents(200)
  const pipeline = usePipelineLatest()
  const baselines = useBaselines()
  const cb = useCircuitBreaker()
  const now = useNow()

  // Detect DRY_RUN from a simple health check (or assume based on cookie)
  const [dryRun, setDryRun] = React.useState(true)
  React.useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then((d) => setDryRun(d.dry_run !== false))
      .catch(() => {})
  }, [])

  const isHalted = cb && cb.halted === 1

  return (
    <div style={s.root}>
      {/* Header */}
      <div style={s.header}>
        <div style={s.headerTitle}>OPTIONS ALPHA AGENT</div>
        <div style={s.headerRight}>
          <span style={s.badge(dryRun === false)}>{dryRun ? 'DRY RUN' : 'LIVE'}</span>
          {account && (
            <span style={s.equity}>Equity: ${account.equity.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
          )}
          <span style={s.clock}>{now} ET</span>
        </div>
      </div>

      {/* Circuit breaker alert */}
      {isHalted && (
        <div style={s.cbHalt}>
          ⚠ CIRCUIT BREAKER ACTIVE — {cb.halt_reason} — No new orders until next trading day.
        </div>
      )}

      {/* Pipeline */}
      <PipelinePanel pipeline={pipeline} />

      <div style={s.grid}>
        <div style={s.leftCol}>
          {/* Positions */}
          <PositionsPanel positions={positions} />

          {/* Regime */}
          <RegimePanel events={events} />

          {/* WATCH items */}
          <div style={s.watchPanel}>
            <div style={{ fontSize: 11, color: palette.muted, letterSpacing: 2, marginBottom: 10 }}>
              WATCHING ({watchItems.length})
            </div>
            {watchItems.length === 0 && (
              <div style={{ color: palette.muted, fontSize: 12 }}>No items in WATCH state.</div>
            )}
            {watchItems.map((item) => (
              <div key={item.id} style={s.watchItem}>
                <span style={{ color: palette.amber, fontWeight: 'bold' }}>{item.underlying}</span>
                {' | '}
                <span>{item.strategy}</span>
                {' | '}
                <span style={{ color: item.score >= 80 ? palette.green : palette.amber }}>
                  {item.score}/100
                </span>
                {' | '}
                <span style={{ color: palette.muted }}>
                  {item.cycles_remaining} cycle(s) left
                </span>
                <div style={{ color: palette.muted, fontSize: 9, marginTop: 2 }}>
                  Needs: {item.promoting_condition?.slice(0, 80)}
                </div>
              </div>
            ))}
          </div>

          {/* Equity curve */}
          <EquityCurve baselines={baselines} />
        </div>

        <div style={s.rightCol}>
          {/* Decision log */}
          <div style={{ fontSize: 11, color: palette.muted, letterSpacing: 2, marginBottom: 8 }}>
            DECISION LOG ({decisions.length})
          </div>
          {decisions.map((d: Decision) => (
            <DecisionCardComponent key={d.id} decision={d} />
          ))}
          {decisions.length === 0 && (
            <div style={{ color: palette.muted, fontSize: 12 }}>
              No decisions yet — waiting for first scan cycle.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
