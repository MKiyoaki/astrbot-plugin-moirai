'use client'

import { useApp } from '@/lib/store'
import type { PluginStats } from '@/lib/api'

interface StatMastheadProps {
  stats: PluginStats
  totalTime: number
}

export function StatMasthead({ stats, totalTime }: StatMastheadProps) {
  const { i18n } = useApp()

  const totalMemory = (stats.events ?? 0) + (stats.archived_events ?? 0)

  const items = [
    { value: stats.events ?? 0, label: i18n.stats.events },
    { value: stats.personas ?? 0, label: i18n.stats.personas },
    { value: stats.impressions ?? 0, label: i18n.stats.impressions },
    { value: stats.locked_count ?? 0, label: i18n.stats.locked },
    { value: stats.summaries ?? 0, label: i18n.stats.summaries },
    { value: stats.groups ?? 0, label: i18n.stats.groups },
    ...(totalMemory > (stats.events ?? 0)
      ? [{ value: totalMemory, label: i18n.stats.totalMemory }]
      : []),
    {
      value: totalTime > 0 ? `${totalTime.toFixed(2)}s` : '—',
      label: i18n.stats.avgResponse,
      mono: true,
    },
  ]

  return (
    <div className="border-t border-b border-border/60 py-5">
      <div className="flex flex-wrap gap-x-10 gap-y-4">
        {items.map((item, idx) => (
          <div key={idx} className="flex flex-col min-w-[64px]">
            <span className={`text-3xl font-bold tracking-tight tabular-nums ${item.mono ? 'font-mono text-2xl' : ''}`}>
              {item.value}
            </span>
            <span className="text-[9px] uppercase tracking-[0.18em] text-muted-foreground mt-0.5">
              {item.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
