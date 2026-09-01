import React from 'react'

export type Tone = 'good' | 'warning' | 'serious' | 'critical' | 'neutral'

/** Outcome -> tone. Status colour is reserved for state, never for series. */
export const OUTCOME_TONE: Record<string, Tone> = {
  TRADE: 'good',
  WATCH: 'warning',
  REJECT: 'critical',
  STAND_ASIDE: 'neutral',
  EXPIRED: 'neutral',
}

export const CONFIDENCE_TONE: Record<string, Tone> = {
  HIGH: 'good',
  MEDIUM: 'warning',
  LOW: 'neutral',
}

/** Status pill. The dot carries the colour; the label always wears ink, so it
 *  stays legible even where the status hue itself is below text contrast. */
export function Badge({
  tone = 'neutral',
  children,
  dot = true,
}: {
  tone?: Tone
  children: React.ReactNode
  dot?: boolean
}) {
  return (
    <span className={`badge badge-${tone}`}>
      {dot && <span className="dot" aria-hidden="true" />}
      {children}
    </span>
  )
}

export function Panel({
  title,
  actions,
  children,
  flush = false,
}: {
  title: string
  actions?: React.ReactNode
  children: React.ReactNode
  flush?: boolean
}) {
  return (
    <section className="panel">
      <header className="panel-head">
        <h2 className="panel-title">{title}</h2>
        {actions}
      </header>
      <div className={flush ? 'panel-body-flush' : 'panel-body'}>{children}</div>
    </section>
  )
}

/** Loading, error and empty are three different things — say which. */
export function DataState({
  loading,
  error,
  empty,
  emptyText,
  emptyIcon = '—',
  children,
}: {
  loading: boolean
  error: string | null
  empty: boolean
  emptyText: string
  emptyIcon?: string
  children: React.ReactNode
}) {
  if (loading) {
    return (
      <div style={{ display: 'grid', gap: 8 }} aria-busy="true">
        <div className="skeleton" style={{ width: '70%' }} />
        <div className="skeleton" style={{ width: '45%' }} />
        <div className="skeleton" style={{ width: '58%' }} />
      </div>
    )
  }
  if (error) {
    return (
      <div className="state state-err" role="alert">
        <span className="state-icon" aria-hidden="true">⚠</span>
        Can’t reach the agent ({error}).<br />
        Showing nothing rather than stale data.
      </div>
    )
  }
  if (empty) {
    return (
      <div className="state">
        <span className="state-icon" aria-hidden="true">{emptyIcon}</span>
        {emptyText}
      </div>
    )
  }
  return <>{children}</>
}

export function Meter({
  label,
  valueText,
  fraction,
  tone = 'neutral',
}: {
  label: string
  valueText: string
  fraction: number
  tone?: Tone
}) {
  const pct = Math.max(0, Math.min(1, fraction)) * 100
  return (
    <div className="meter">
      <div className="meter-head">
        <span>{label}</span>
        <span className="tnum">{valueText}</span>
      </div>
      <div
        className="meter-track"
        role="img"
        aria-label={`${label}: ${valueText}`}
      >
        <div
          className="meter-fill"
          style={{ width: `${pct}%`, background: `var(--${tone})` }}
        />
      </div>
    </div>
  )
}

export function fmtMoney(n: number | null | undefined, dp = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  return `$${n.toLocaleString(undefined, {
    minimumFractionDigits: dp,
    maximumFractionDigits: dp,
  })}`
}

export function fmtPct(n: number | null | undefined, dp = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  return `${(n * 100).toFixed(dp)}%`
}

export function fmtAgo(seconds: number | null): string {
  if (seconds === null) return 'never'
  if (seconds < 5) return 'just now'
  if (seconds < 60) return `${seconds}s ago`
  const m = Math.floor(seconds / 60)
  if (m < 60) return `${m}m ago`
  return `${Math.floor(m / 60)}h ago`
}
