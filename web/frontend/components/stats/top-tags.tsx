'use client'

import { useMemo } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { useApp } from '@/lib/store'
import type { ApiEvent } from '@/lib/api'

interface TopTagsProps {
  events: ApiEvent[]
}

export function TopTags({ events }: TopTagsProps) {
  const { i18n, lang } = useApp()

  const topTags = useMemo(() => {
    const freq: Record<string, number> = {}
    for (const ev of events) {
      for (const tag of ev.tags ?? []) {
        freq[tag] = (freq[tag] ?? 0) + 1
      }
    }
    return Object.entries(freq)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 12)
  }, [events])

  const maxCount = topTags[0]?.[1] ?? 1

  return (
    <Card className="border-border/50">
      <div className="px-6 pt-5 pb-3 border-b border-border/40">
        <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground font-mono">
          {i18n.stats.topTags}
        </p>
        <p className="text-xs text-muted-foreground mt-0.5">{i18n.stats.topTagsDesc}</p>
      </div>
      <CardContent className="py-4 px-6">
        {topTags.length === 0 ? (
          <p className="text-xs text-muted-foreground/40 italic py-4 text-center">{i18n.stats.noData}</p>
        ) : (
          <div className="space-y-2.5">
            {topTags.map(([tag, count], idx) => (
              <div key={tag} className="flex items-center gap-3">
                <span className="text-[9px] font-mono text-muted-foreground/50 w-4 text-right shrink-0">
                  {idx + 1}
                </span>
                <span className="text-xs text-foreground truncate w-24 shrink-0">#{tag}</span>
                <div className="flex-1 h-0.5 bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full bg-accent-foreground/70 transition-all duration-700"
                    style={{ width: `${(count / maxCount) * 100}%` }}
                  />
                </div>
                <span className="text-[11px] font-mono font-bold text-accent-foreground shrink-0 w-6 text-right">
                  {count}
                </span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
