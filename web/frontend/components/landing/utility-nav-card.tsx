'use client'

import Link from 'next/link'
import { Card, CardContent } from '@/components/ui/card'
import { useApp } from '@/lib/store'
import type { PluginStats, GraphData } from '@/lib/api'
import { cn } from '@/lib/utils'

interface UtilityNavCardsProps {
  stats: PluginStats
  graph: GraphData | null
}

export function UtilityNavCards({ stats, graph }: UtilityNavCardsProps) {
  const { i18n } = useApp()

  const nodeCount = graph?.nodes?.length ?? 0
  const edgeCount = graph?.edges?.length ?? 0
  const chapterCount = stats.summaries ?? 0
  const avgRecall = stats.perf?.avg_recall_time != null
    ? `${(stats.perf.avg_recall_time as number).toFixed(3)}s`
    : '—'

  const cards = [
    {
      href: '/recall',
      mark: '○',
      title: i18n.nav.recall,
      desc: i18n.landing.recallDesc,
      meta: `${avgRecall} ${i18n.landing.avgRecallLabel}`,
    },
    {
      href: '/graph',
      mark: '◇',
      title: i18n.nav.graph,
      desc: i18n.landing.graphDesc,
      meta: `${nodeCount} ${i18n.landing.nodesLabel} · ${edgeCount} ${i18n.landing.edgesLabel}`,
    },
    {
      href: '/summary',
      mark: '□',
      title: i18n.nav.summary,
      desc: i18n.landing.summaryDesc,
      meta: `${chapterCount} ${i18n.landing.chaptersLabel}`,
      ribbon: true,
    },
  ]

  return (
    <div className="grid grid-cols-3 gap-4">
      {cards.map((card, idx) => (
        <Link key={card.href} href={card.href}>
          <Card
            className={cn(
              'h-full cursor-pointer transition-colors hover:bg-accent/40 border-border/50',
              idx === 2 && 'relative overflow-hidden'
            )}
          >
            {card.ribbon && (
              <div className="absolute left-0 top-0 bottom-0 w-1 bg-accent-foreground/60" />
            )}
            <CardContent className="p-5 flex flex-col gap-3 h-full">
              <div className="flex items-start justify-between">
                <span className="text-xl text-muted-foreground/60 leading-none select-none">{card.mark}</span>
              </div>
              <div className="flex-1">
                <h3 className="font-semibold text-sm text-foreground">{card.title}</h3>
                <p className="text-[11px] text-muted-foreground mt-1 leading-relaxed">{card.desc}</p>
              </div>
              <p className="text-[10px] text-accent-foreground/70 font-mono">— {card.meta}</p>
            </CardContent>
          </Card>
        </Link>
      ))}
    </div>
  )
}
