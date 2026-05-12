'use client'

import { Card, CardContent } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { useApp } from '@/lib/store'
import type { PluginStats } from '@/lib/api'

interface Averages {
  participants: string
  tags: string
  salience: string
  edges: string
}

interface AvgMetricsProps {
  averages: Averages
  stats: PluginStats
}

export function AvgMetrics({ averages, stats }: AvgMetricsProps) {
  const { i18n, lang } = useApp()

  const rows = [
    { label: i18n.stats.avgNodes, value: averages.participants },
    { label: i18n.stats.avgTags, value: averages.tags },
    { label: i18n.stats.avgEdges, value: averages.edges },
    { label: i18n.stats.avgSalience, value: averages.salience },
  ]

  return (
    <Card className="border-border/50 h-full">
      <div className="px-6 pt-5 pb-3 border-b border-border/40">
        <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground font-mono">
          {i18n.stats.avgMetrics}
        </p>
        <p className="text-xs text-muted-foreground mt-0.5">
          {lang === 'zh' ? '每事件平均指标' : 'Per-event averages'}
        </p>
      </div>
      <CardContent className="py-4 px-6">
        <div className="space-y-4">
          {rows.map((row) => (
            <div key={row.label} className="flex items-baseline justify-between">
              <span className="text-xs text-muted-foreground">— {row.label}</span>
              <span className="text-xl font-bold tabular-nums text-accent-foreground">{row.value}</span>
            </div>
          ))}
          <Separator className="my-1 opacity-50" />
          <div className="flex items-baseline justify-between">
            <span className="text-xs text-muted-foreground">— {i18n.stats.summaryDays}</span>
            <span className="text-xl font-bold tabular-nums text-accent-foreground">
              {stats.summary_days ?? 0}
              <span className="text-xs font-normal text-muted-foreground ml-1">d</span>
            </span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-xs text-muted-foreground">— {i18n.stats.summaryAvgChars}</span>
            <span className="text-xl font-bold tabular-nums text-accent-foreground">
              {stats.avg_summary_chars ?? 0}
              <span className="text-xs font-normal text-muted-foreground ml-1">ch</span>
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
