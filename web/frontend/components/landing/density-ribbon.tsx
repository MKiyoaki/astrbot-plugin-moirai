'use client'

import { useMemo } from 'react'
import { Card } from '@/components/ui/card'
import { useApp } from '@/lib/store'
import type { ApiEvent } from '@/lib/api'
import { cn } from '@/lib/utils'

interface DensityRibbonProps {
  events: ApiEvent[]
}

export function DensityRibbon({ events }: DensityRibbonProps) {
  const { i18n } = useApp()

  const days = useMemo(() => {
    const buckets: Record<string, { count: number; maxSalience: number; hasEmotional: boolean }> = {}
    const now = new Date()

    for (let i = 6; i >= 0; i--) {
      const d = new Date(now)
      d.setDate(d.getDate() - i)
      const key = d.toISOString().split('T')[0]
      buckets[key] = { count: 0, maxSalience: 0, hasEmotional: false }
    }

    for (const ev of events) {
      const key = new Date(ev.start).toISOString().split('T')[0]
      if (key in buckets) {
        buckets[key].count++
        buckets[key].maxSalience = Math.max(buckets[key].maxSalience, ev.salience)
        // treat events with emotional tags as "emotionally strong"
        if (ev.tags.some(t => ['情感', '情绪', 'emotion', 'emotional', '感情'].includes(t.toLowerCase()))) {
          buckets[key].hasEmotional = true
        }
      }
    }

    return Object.entries(buckets).map(([date, data]) => ({ date, ...data }))
  }, [events])

  const maxCount = Math.max(...days.map(d => d.count), 1)

  return (
    <Card className="px-6 py-4 border-border/50">
      <div className="flex items-center justify-between mb-3">
        <div>
          <p className="text-xs font-medium text-foreground">{i18n.landing.densityLabel}</p>
          <p className="text-[9px] uppercase tracking-widest text-muted-foreground font-mono mt-0.5">
            {i18n.landing.densitySubtitle}
          </p>
        </div>
      </div>
      <div className="flex gap-1.5 items-end h-10">
        {days.map(({ date, count, maxSalience, hasEmotional }) => {
          const heightPct = count === 0 ? 8 : Math.max(15, (count / maxCount) * 100)
          const isHighSalience = maxSalience > 0.7
          const blockClass = cn(
            'flex-1 rounded-sm transition-all',
            count === 0
              ? 'bg-muted/40'
              : isHighSalience
              ? 'bg-accent-foreground/80'
              : hasEmotional
              ? 'bg-amber-500/60'
              : 'bg-muted-foreground/40'
          )
          return (
            <div
              key={date}
              title={`${date}: ${count} events`}
              className={blockClass}
              style={{ height: `${heightPct}%` }}
            />
          )
        })}
      </div>
      <div className="flex justify-between mt-1.5">
        {days.map(({ date }) => (
          <span key={date} className="flex-1 text-center text-[8px] text-muted-foreground font-mono">
            {new Date(date + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'narrow' })}
          </span>
        ))}
      </div>
    </Card>
  )
}
