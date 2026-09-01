import { useState, useEffect, useCallback, useRef } from 'react'
import type {
  Decision, Position, WatchItem, Event, Account, BaselineRecord,
  CircuitBreaker, Health,
} from './types'

const POLL_INTERVAL = 5000

/** A polled resource, with enough state to tell "nothing yet" from "broken".
 *
 * The previous version swallowed every error and silently kept stale data, so
 * an unreachable API looked exactly like an idle agent. Callers can now render
 * loading, error and empty as three different things.
 */
export interface Polled<T> {
  data: T
  loading: boolean   // first load only
  error: string | null
  updatedAt: number | null
}

function usePoll<T>(
  url: string,
  defaultValue: T,
  interval: number = POLL_INTERVAL
): Polled<T> {
  const [data, setData] = useState<T>(defaultValue)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [updatedAt, setUpdatedAt] = useState<number | null>(null)
  const seeded = useRef(false)

  useEffect(() => {
    let active = true

    const fetchData = async () => {
      try {
        const resp = await fetch(url)
        if (!active) return
        if (!resp.ok) {
          setError(`HTTP ${resp.status}`)
          return
        }
        setData(await resp.json())
        setError(null)
        setUpdatedAt(Date.now())
      } catch {
        if (active) setError('unreachable')
      } finally {
        if (active && !seeded.current) {
          seeded.current = true
          setLoading(false)
        }
      }
    }

    fetchData()
    const id = setInterval(fetchData, interval)
    return () => {
      active = false
      clearInterval(id)
    }
  }, [url, interval])

  return { data, loading, error, updatedAt }
}

export function useDecisions(limit = 50, outcome?: string): Polled<Decision[]> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (outcome) params.set('outcome', outcome)
  return usePoll<Decision[]>(`/api/decisions?${params}`, [])
}

export function usePositions(): Polled<Position[]> {
  return usePoll<Position[]>('/api/positions', [])
}

export function useWatchItems(state?: string): Polled<WatchItem[]> {
  const params = state ? `?state=${state}` : ''
  return usePoll<WatchItem[]>(`/api/watch_items${params}`, [])
}

export function useEvents(limit = 100, cycle_id?: string): Polled<Event[]> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (cycle_id) params.set('cycle_id', cycle_id)
  return usePoll<Event[]>(`/api/events?${params}`, [])
}

export function usePipelineLatest(): Polled<Record<string, Event[]>> {
  return usePoll<Record<string, Event[]>>('/api/pipeline/latest?cycles=3', {})
}

export function useAccount(): Polled<Account | null> {
  return usePoll<Account | null>('/api/account', null)
}

export function useBaselines(type?: string): Polled<BaselineRecord[]> {
  const params = type ? `?type=${type}` : ''
  return usePoll<BaselineRecord[]>(`/api/baselines${params}`, [])
}

export function useCircuitBreaker(): Polled<CircuitBreaker | null> {
  return usePoll<CircuitBreaker | null>('/api/circuit_breaker/today', null)
}

/** Agent liveness: scheduler state and market hours, straight from the server. */
export function useHealth(): Polled<Health | null> {
  return usePoll<Health | null>('/api/health', null, 10000)
}

/** Seconds since a timestamp, ticking once a second. */
export function useSecondsSince(ts: number | null): number | null {
  const [, force] = useState(0)
  useEffect(() => {
    const id = setInterval(() => force((n) => n + 1), 1000)
    return () => clearInterval(id)
  }, [])
  return ts === null ? null : Math.floor((Date.now() - ts) / 1000)
}

/** Current time in real US Eastern time — the market's timezone, not the viewer's. */
export function useEasternClock(): string {
  const fmt = useCallback(
    () =>
      new Intl.DateTimeFormat('en-US', {
        timeZone: 'America/New_York',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      }).format(new Date()),
    []
  )
  const [now, setNow] = useState(fmt)
  useEffect(() => {
    const id = setInterval(() => setNow(fmt()), 1000)
    return () => clearInterval(id)
  }, [fmt])
  return now
}
