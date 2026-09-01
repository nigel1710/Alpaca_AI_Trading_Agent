import React from 'react'
import type { Decision } from '../types'

/** Headline counts. A stat tile beats a chart here: these are single numbers,
 *  not a shape over time (and the equity series is usually too short to plot). */
export default function StatsRow({ decisions }: { decisions: Decision[] }) {
  const total = decisions.length
  const by = (o: string) => decisions.filter((d) => d.outcome === o).length

  const scored = decisions.filter((d) => d.opportunity_score !== null)
  const avgScore = scored.length
    ? Math.round(scored.reduce((s, d) => s + (d.opportunity_score ?? 0), 0) / scored.length)
    : null

  const rrs = decisions
    .map((d) => d.reward_risk)
    .filter((r): r is number => r !== null && r > 0)
  const avgRR = rrs.length ? rrs.reduce((a, b) => a + b, 0) / rrs.length : null

  const tiles: Array<{ k: string; v: string; tone?: string }> = [
    { k: 'Decisions', v: String(total) },
    { k: 'Traded', v: String(by('TRADE')), tone: 'var(--good)' },
    { k: 'Watching', v: String(by('WATCH')), tone: 'var(--warning)' },
    { k: 'Declined', v: String(by('REJECT') + by('STAND_ASIDE')), tone: 'var(--neutral)' },
    { k: 'Avg score', v: avgScore === null ? '—' : `${avgScore}` },
    { k: 'Avg R:R', v: avgRR === null ? '—' : `${avgRR.toFixed(2)}×` },
  ]

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(92px, 1fr))',
        gap: 12,
      }}
    >
      {tiles.map((t) => (
        <div key={t.k}>
          <div className="kv-k">{t.k}</div>
          <div
            style={{
              fontSize: 22,
              fontWeight: 650,
              fontVariantNumeric: 'tabular-nums',
              lineHeight: 1.2,
              color: t.tone ?? 'var(--text-primary)',
            }}
          >
            {t.v}
          </div>
        </div>
      ))}
    </div>
  )
}
