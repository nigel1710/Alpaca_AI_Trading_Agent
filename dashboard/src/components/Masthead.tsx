import React from 'react'
import type { Account, Health } from '../types'
import { Badge, fmtMoney, fmtAgo } from './ui'
import { useEasternClock } from '../api'

/** Top strip: identity, agent liveness, account, and a clock that is actually
 *  Eastern time (the previous one printed the viewer's local time labelled
 *  "ET", which on a trading dashboard is worse than showing nothing). */
export default function Masthead({
  account,
  health,
  connected,
  secondsSinceUpdate,
  theme,
  onToggleTheme,
}: {
  account: Account | null
  health: Health | null
  connected: boolean
  secondsSinceUpdate: number | null
  theme: 'light' | 'dark'
  onToggleTheme: () => void
}) {
  const clock = useEasternClock()

  const marketOpen = health?.market_hours ?? false
  const schedulerOn = health?.scheduler_enabled ?? false
  const schedulerUp = health?.scheduler_running ?? false

  // Distinguish "not configured to run" from "configured but dead".
  const agent = !connected
    ? { tone: 'critical' as const, text: 'DISCONNECTED' }
    : !schedulerOn
      ? { tone: 'neutral' as const, text: 'MANUAL MODE' }
      : schedulerUp
        ? { tone: 'good' as const, text: 'AGENT LIVE' }
        : { tone: 'critical' as const, text: 'SCHEDULER DOWN' }

  return (
    <header className="masthead">
      <div>
        <div className="brand">Options Alpha Agent</div>
        <div className="brand-sub">
          Adaptive asymmetric options strategy
          {health?.watchlist?.length ? ` · ${health.watchlist.join(' ')}` : ''}
        </div>
      </div>

      <div className="masthead-right">
        <Badge tone={agent.tone}>{agent.text}</Badge>

        <Badge tone={marketOpen ? 'good' : 'neutral'}>
          {marketOpen ? 'Market open' : 'Market closed'}
        </Badge>

        {health && (
          <Badge tone={health.dry_run ? 'neutral' : 'warning'} dot={false}>
            {health.dry_run ? 'Paper · dry run' : 'Live orders'}
          </Badge>
        )}

        {account && (
          <div className="metric-inline">
            <span className="k">Equity</span>
            <span className="v">{fmtMoney(account.equity)}</span>
          </div>
        )}

        <div className="metric-inline">
          <span className="k">New York</span>
          <span className="v mono">{clock}</span>
        </div>

        <div className="metric-inline">
          <span className="k">Updated</span>
          <span className="v" style={{ fontSize: 12, fontWeight: 500 }}>
            {fmtAgo(secondsSinceUpdate)}
          </span>
        </div>

        <button
          className="icon-btn"
          onClick={onToggleTheme}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
          title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
        >
          {theme === 'dark' ? '☀' : '☾'}
        </button>
      </div>
    </header>
  )
}
