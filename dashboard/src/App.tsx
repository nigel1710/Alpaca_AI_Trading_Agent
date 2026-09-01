import React, { useEffect, useMemo, useState } from 'react'
import {
  useDecisions, usePositions, useWatchItems, usePipelineLatest,
  useAccount, useCircuitBreaker, useHealth, useSecondsSince,
} from './api'
import Masthead from './components/Masthead'
import PipelinePanel from './components/PipelinePanel'
import PositionsPanel from './components/PositionsPanel'
import RegimePanel from './components/RegimePanel'
import StatsRow from './components/StatsRow'
import DecisionCardComponent from './components/DecisionCard'
import { Badge, DataState, Panel } from './components/ui'
import type { Decision } from './types'

type Filter = 'ALL' | 'TRADE' | 'WATCH' | 'REJECT' | 'STAND_ASIDE'
const FILTERS: Filter[] = ['ALL', 'TRADE', 'WATCH', 'REJECT', 'STAND_ASIDE']

function useTheme(): ['light' | 'dark', () => void] {
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    try {
      const saved = localStorage.getItem('oaa-theme')
      if (saved === 'light' || saved === 'dark') return saved
    } catch {
      /* private mode / blocked storage — fall through to the default */
    }
    return 'light'
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    try {
      localStorage.setItem('oaa-theme', theme)
    } catch {
      /* not persisting is fine; the toggle still works for this session */
    }
  }, [theme])

  return [theme, () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))]
}

export default function App() {
  const account = useAccount()
  const decisions = useDecisions(100)
  const positions = usePositions()
  const watchItems = useWatchItems('WATCHING')
  const pipeline = usePipelineLatest()
  const cb = useCircuitBreaker()
  const health = useHealth()

  const [theme, toggleTheme] = useTheme()
  const [filter, setFilter] = useState<Filter>('ALL')

  const secondsSince = useSecondsSince(decisions.updatedAt)
  const connected = !decisions.error && !health.error

  const counts = useMemo(() => {
    const c: Record<string, number> = { ALL: decisions.data.length }
    for (const d of decisions.data) c[d.outcome] = (c[d.outcome] ?? 0) + 1
    return c
  }, [decisions.data])

  const visible: Decision[] = useMemo(
    () =>
      filter === 'ALL'
        ? decisions.data
        : decisions.data.filter((d) => d.outcome === filter),
    [decisions.data, filter]
  )

  const halted = cb.data?.halted === 1

  return (
    <div className="app">
      <Masthead
        account={account.data}
        health={health.data}
        connected={connected}
        secondsSinceUpdate={secondsSince}
        theme={theme}
        onToggleTheme={toggleTheme}
      />

      {halted && (
        <div
          className="panel"
          role="alert"
          style={{
            borderLeft: '3px solid var(--critical)',
            background: 'var(--critical-wash)',
            marginBottom: 16,
            padding: '12px 16px',
            fontSize: 13,
          }}
        >
          <strong>Circuit breaker active</strong> — {cb.data?.halt_reason}. No new
          orders until the next trading day.
        </div>
      )}

      <div style={{ marginBottom: 16 }}>
        <Panel title="Activity">
          <StatsRow decisions={decisions.data} />
        </Panel>
      </div>

      <div style={{ marginBottom: 16 }}>
        <Panel title="Decision pipeline">
          <DataState
            loading={pipeline.loading}
            error={pipeline.error}
            empty={Object.keys(pipeline.data).length === 0}
            emptyText="No scan cycles recorded yet."
            emptyIcon="◷"
          >
            <PipelinePanel pipeline={pipeline.data} />
          </DataState>
        </Panel>
      </div>

      <div className="grid-main">
        <div className="stack">
          <Panel title={`Open positions (${positions.data.length})`} flush>
            <DataState
              loading={positions.loading}
              error={positions.error}
              empty={positions.data.length === 0}
              emptyText="No open positions."
              emptyIcon="○"
            >
              <PositionsPanel positions={positions.data} />
            </DataState>
          </Panel>

          <Panel title="Market regime" flush>
            <DataState
              loading={decisions.loading}
              error={decisions.error}
              empty={decisions.data.length === 0}
              emptyText="No regime readings yet."
              emptyIcon="◐"
            >
              <RegimePanel decisions={decisions.data} />
            </DataState>
          </Panel>

          <Panel title={`Watching (${watchItems.data.length})`}>
            <DataState
              loading={watchItems.loading}
              error={watchItems.error}
              empty={watchItems.data.length === 0}
              emptyText="Nothing in the watch list."
              emptyIcon="◇"
            >
              <div style={{ display: 'grid', gap: 12 }}>
                {watchItems.data.map((item) => (
                  <div key={item.id}>
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        flexWrap: 'wrap',
                      }}
                    >
                      <strong className="mono">{item.underlying}</strong>
                      <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                        {item.strategy}
                      </span>
                      <Badge tone="warning" dot={false}>{item.score}/100</Badge>
                      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                        {item.cycles_remaining} cycle
                        {item.cycles_remaining === 1 ? '' : 's'} left
                      </span>
                    </div>
                    <div
                      style={{
                        fontSize: 11,
                        color: 'var(--text-muted)',
                        marginTop: 3,
                      }}
                    >
                      {item.promoting_condition}
                    </div>
                  </div>
                ))}
              </div>
            </DataState>
          </Panel>
        </div>

        <Panel
          title={`Decisions (${visible.length})`}
          flush
          actions={
            <div className="chips">
              {FILTERS.map((f) => (
                <button
                  key={f}
                  className="chip"
                  aria-pressed={filter === f}
                  onClick={() => setFilter(f)}
                >
                  {f === 'STAND_ASIDE' ? 'ASIDE' : f}
                  <span className="count">{counts[f] ?? 0}</span>
                </button>
              ))}
            </div>
          }
        >
          <div className="scroll-y">
            <DataState
              loading={decisions.loading}
              error={decisions.error}
              empty={visible.length === 0}
              emptyText={
                decisions.data.length === 0
                  ? 'No decisions yet — waiting for the first scan cycle.'
                  : `No ${filter.toLowerCase().replace('_', ' ')} decisions.`
              }
              emptyIcon="◇"
            >
              {visible.map((d, i) => (
                <DecisionCardComponent
                  key={`${d.cycle_id}-${d.underlying}-${d.ts}`}
                  decision={d}
                  defaultOpen={i === 0}
                />
              ))}
            </DataState>
          </div>
        </Panel>
      </div>
    </div>
  )
}
