'use client'

import { useMemo } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { useApp } from '@/lib/store'
import type { ApiEvent, GraphData } from '@/lib/api'

interface PersonaRankProps {
  events: ApiEvent[]
  graph: GraphData | null
}

export function PersonaRank({ events, graph }: PersonaRankProps) {
  const { i18n } = useApp()

  const ranked = useMemo(() => {
    const freq: Record<string, number> = {}
    for (const ev of events) {
      for (const uid of ev.participants ?? []) {
        freq[uid] = (freq[uid] ?? 0) + 1
      }
    }
    // Resolve uid → display name using graph node labels
    const labelMap: Record<string, string> = {}
    for (const node of graph?.nodes ?? []) {
      labelMap[node.data.id] = node.data.label
    }
    return Object.entries(freq)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([uid, count]) => ({ uid, label: labelMap[uid] ?? uid, count }))
  }, [events, graph])

  const maxCount = ranked[0]?.count ?? 1

  return (
    <Card className="border-border/50">
      <div className="px-6 pt-5 pb-3 border-b border-border/40">
        <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground font-mono">
          {i18n.stats.personaRank}
        </p>
        <p className="text-xs text-muted-foreground mt-0.5">{i18n.stats.personaRankDesc}</p>
      </div>
      <CardContent className="py-4 px-6">
        {ranked.length === 0 ? (
          <p className="text-xs text-muted-foreground/40 italic py-4 text-center">{i18n.stats.noData}</p>
        ) : (
          <div className="space-y-2.5">
            {ranked.map(({ uid, label, count }, idx) => (
              <div key={uid} className="flex items-center gap-3">
                <span className="text-[9px] font-mono text-muted-foreground/50 w-4 text-right shrink-0">
                  {idx + 1}
                </span>
                <span className="text-xs truncate flex-1">{label}</span>
                <div className="w-20 h-0.5 bg-muted rounded-full overflow-hidden shrink-0">
                  <div
                    className="h-full bg-accent-foreground/70 transition-all duration-700"
                    style={{ width: `${(count / maxCount) * 100}%` }}
                  />
                </div>
                <span className="text-[11px] font-mono font-bold text-accent-foreground w-6 text-right shrink-0">
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
