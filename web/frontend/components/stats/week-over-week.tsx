'use client'

import { useMemo } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { useApp } from '@/lib/store'
import type { ApiEvent } from '@/lib/api'
import { cn } from '@/lib/utils'

interface WeekOverWeekProps {
  events: ApiEvent[]
}

export function WeekOverWeek({ events }: WeekOverWeekProps) {
  const { i18n } = useApp()

  const { thisWeek, lastWeek, delta, pct } = useMemo(() => {
    const now = Date.now()
    const day = 86_400_000
    const thisWeek = events.filter(ev => now - new Date(ev.start).getTime() < 7 * day).length
    const lastWeek = events.filter(ev => {
      const age = now - new Date(ev.start).getTime()
      return age >= 7 * day && age < 14 * day
    }).length
    const delta = thisWeek - lastWeek
    const pct = lastWeek === 0 ? null : Math.abs(Math.round((delta / lastWeek) * 100))
    return { thisWeek, lastWeek, delta, pct }
  }, [events])

  const isUp = delta > 0
  const isFlat = delta === 0

  return (
    <Card className="border-border/50">
      <div className="px-6 pt-5 pb-3 border-b border-border/40">
        <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground font-mono">
          {i18n.stats.weekOverWeek}
        </p>
        <p className="text-xs text-muted-foreground mt-0.5">{i18n.stats.weekOverWeekDesc}</p>
      </div>
      <CardContent className="py-5 px-6">
        <div className="flex items-end gap-6">
          <div className="flex flex-col">
            <span className="text-4xl font-bold tabular-nums">{thisWeek}</span>
            <span className="text-[9px] uppercase tracking-widest text-muted-foreground mt-0.5">
              {i18n.stats.events} · {i18n.stats.weekOverWeekDesc.split(' vs ')[0] ?? '7d'}
            </span>
          </div>
          <div className="flex flex-col mb-1">
            <span className={cn(
              'text-sm font-bold font-mono',
              isFlat ? 'text-muted-foreground' : isUp ? 'text-accent-foreground' : 'text-destructive'
            )}>
              {isFlat
                ? i18n.stats.wowFlat
                : isUp
                ? `${i18n.stats.wowIncrease} ${pct != null ? pct + '%' : ''}`
                : `${i18n.stats.wowDecrease} ${pct != null ? pct + '%' : ''}`}
            </span>
            <span className="text-[9px] text-muted-foreground/60">
              {lastWeek} → {thisWeek}
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
