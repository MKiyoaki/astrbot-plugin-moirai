'use client'

import { useMemo } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { useApp } from '@/lib/store'
import type { ApiEvent } from '@/lib/api'
import { cn } from '@/lib/utils'

interface HourlyPatternProps {
  events: ApiEvent[]
}

export function HourlyPattern({ events }: HourlyPatternProps) {
  const { i18n } = useApp()

  const hourly = useMemo(() => {
    const counts = Array(24).fill(0) as number[]
    for (const ev of events) {
      const h = new Date(ev.start).getHours()
      counts[h]++
    }
    return counts
  }, [events])

  const maxCount = Math.max(...hourly, 1)

  // Group into dawn/morning/afternoon/evening/night bands for color
  const bandColor = (h: number) => {
    if (h < 6) return 'bg-muted-foreground/30'      // night
    if (h < 12) return 'bg-accent-foreground/50'    // morning
    if (h < 18) return 'bg-accent-foreground/80'    // afternoon
    if (h < 22) return 'bg-accent-foreground/60'    // evening
    return 'bg-muted-foreground/30'                  // late night
  }

  return (
    <Card className="border-border/50">
      <div className="px-6 pt-5 pb-3 border-b border-border/40">
        <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground font-mono">
          {i18n.stats.hourlyPattern}
        </p>
        <p className="text-xs text-muted-foreground mt-0.5">{i18n.stats.hourlyDesc}</p>
      </div>
      <CardContent className="py-5 px-6">
        <div className="flex items-end gap-0.5 h-16">
          {hourly.map((count, h) => (
            <div
              key={h}
              title={`${h}:00 — ${count}`}
              className={cn('flex-1 rounded-sm transition-all duration-500', count > 0 ? bandColor(h) : 'bg-muted/30')}
              style={{ height: `${count === 0 ? 6 : Math.max(10, (count / maxCount) * 100)}%` }}
            />
          ))}
        </div>
        {/* Hour ticks: only 0, 6, 12, 18, 23 */}
        <div className="relative mt-1 h-3">
          {[0, 6, 12, 18, 23].map((h) => (
            <span
              key={h}
              className="absolute text-[8px] font-mono text-muted-foreground/50 -translate-x-1/2"
              style={{ left: `${(h / 23) * 100}%` }}
            >
              {h}
            </span>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
