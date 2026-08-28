import { useState, useEffect } from 'react'
import type { Decision, Position, WatchItem, Event, Account, BaselineRecord, CircuitBreaker } from './types'

const POLL_INTERVAL = 5000

function usePoll<T>(
  url: string,
  defaultValue: T,
  interval: number = POLL_INTERVAL
): T {
  const [data, setData] = useState<T>(defaultValue)

  useEffect(() => {
    let active = true

    const fetchData = async () => {
      try {
        const resp = await fetch(url)
        if (resp.ok && active) {
          setData(await resp.json())
        }
      } catch {
        // network error — keep last data
      }
    }

    fetchData()
    const id = setInterval(fetchData, interval)
    return () => {
      active = false
      clearInterval(id)
    }
  }, [url, interval])

  return data
}

export function useDecisions(limit = 50, outcome?: string): Decision[] {
  const params = new URLSearchParams({ limit: String(limit) })
  if (outcome) params.set('outcome', outcome)
  return usePoll<Decision[]>(`/api/decisions?${params}`, [])
}

export function usePositions(): Position[] {
  return usePoll<Position[]>('/api/positions', [])
}

export function useWatchItems(state?: string): WatchItem[] {
  const params = state ? `?state=${state}` : ''
  return usePoll<WatchItem[]>(`/api/watch_items${params}`, [])
}

export function useEvents(limit = 100, cycle_id?: string): Event[] {
  const params = new URLSearchParams({ limit: String(limit) })
  if (cycle_id) params.set('cycle_id', cycle_id)
  return usePoll<Event[]>(`/api/events?${params}`, [])
}

export function usePipelineLatest(): Record<string, Event[]> {
  return usePoll<Record<string, Event[]>>('/api/pipeline/latest?cycles=3', {})
}

export function useAccount(): Account | null {
  return usePoll<Account | null>('/api/account', null)
}

export function useBaselines(type?: string): BaselineRecord[] {
  const params = type ? `?type=${type}` : ''
  return usePoll<BaselineRecord[]>(`/api/baselines${params}`, [])
}

export function useCircuitBreaker(): CircuitBreaker | null {
  return usePoll<CircuitBreaker | null>('/api/circuit_breaker/today', null)
}
