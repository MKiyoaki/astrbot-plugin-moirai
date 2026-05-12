'use client'

import { useMemo } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { useApp } from '@/lib/store'
import type { ApiEvent } from '@/lib/api'
import { cn } from '@/lib/utils'

interface SalienceDistProps {
  events: ApiEvent[]
}

export function SalienceDist({ events }: SalienceDistProps) {
  const { i18n } = useApp()

  const dist = useMemo(() => {
    let low = 0, mid = 0, high = 0
    for (const ev of events) {
      if (ev.salience < 0.3) low++
      else if (ev.salience < 0.7) mid++
      else high++
    }
    const total = events.length || 1
    return [
      { label: i18n.stats.salienceLow, count: low, pct: (low / total) * 100, color: 'bg-muted-foreground/40' },
      { label: i18n.stats.salienceMid, count: mid, pct: (mid / total) * 100, color: 'bg-accent-foreground/50' },
      { label: i18n.stats.salienceHigh, count: high, pct: (high / total) * 100, color: 'bg-accent-foreground' },
    ]
  }, [events, i18n])

  return (
    <Card className="border-border/50">
      <div className="px-6 pt-5 pb-3 border-b border-border/40">
        <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground font-mono">
          {i18n.stats.salienceDist}
        </p>
      </div>
      <CardContent className="py-5 px-6 space-y-4">
        {/* Stacked bar */}
        <div className="flex h-3 rounded-full overflow-hidden gap-0.5">
          {dist.map((d) => (
            <div
              key={d.label}
              className={cn('transition-all duration-700', d.color)}
              style={{ width: `${d.pct}%` }}
            />
          ))}
        </div>
        {/* Legend */}
        <div className="flex justify-between">
          {dist.map((d) => (
            <div key={d.label} className="flex flex-col items-center gap-0.5">
              <span className="text-lg font-bold tabular-nums text-accent-foreground">{d.count}</span>
              <span className="text-[9px] uppercase tracking-widest text-muted-foreground">{d.label}</span>
              <span className="text-[9px] font-mono text-muted-foreground/60">{d.pct.toFixed(0)}%</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
