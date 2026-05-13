'use client'

import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ChevronRight } from 'lucide-react'
import { useApp } from '@/lib/store'
import type { ApiEvent } from '@/lib/api'
import { parseSummaryTopics } from '@/lib/utils'
import { cn } from '@/lib/utils'
import Link from 'next/link'

interface RecentEventsStripProps {
  events: ApiEvent[]
  loading: boolean
}

// Deterministic thread color from event id
const THREAD_COLORS = [
  'border-l-rose-500',
  'border-l-amber-500',
  'border-l-sky-500',
  'border-l-violet-500',
  'border-l-emerald-500',
]

function threadColor(id: string) {
  let hash = 0
  for (let i = 0; i < id.length; i++) hash = (hash * 31 + id.charCodeAt(i)) & 0xffffffff
  return THREAD_COLORS[Math.abs(hash) % THREAD_COLORS.length]
}

export function RecentEventsStrip({ events, loading }: RecentEventsStripProps) {
  const { i18n, lang } = useApp()

  return (
    <Card className="border-border/50">
      <CardHeader className="pb-2 flex flex-row items-center justify-between">
        <p className="text-xs uppercase tracking-widest text-muted-foreground font-mono">
          {i18n.landing.recentEventsStrip}
        </p>
        <Link href="/events">
          <Button variant="ghost" size="sm" className="text-[10px] gap-1 h-6 px-2">
            {i18n.landing.allEvents} <ChevronRight size={12} />
          </Button>
        </Link>
      </CardHeader>

      <CardContent className="p-0">
        {loading ? (
          <div className="px-6 pb-6 space-y-3">
            {Array(3).fill(0).map((_, i) => (
              <div key={i} className="animate-pulse h-16 bg-muted/40 rounded" />
            ))}
          </div>
        ) : events.length === 0 ? (
          <div className="px-6 pb-6 py-8 text-center text-xs text-muted-foreground italic">
            {i18n.landing.noRecentEvents}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 divide-x divide-border/40">
            {events.map((ev) => {
              const topics = parseSummaryTopics(ev.summary)
              const what = topics?.[0]?.what ?? ev.summary ?? ''
              const who = topics?.[0]?.who ?? ''
              const dateStr = new Date(ev.start).toLocaleString(
                lang === 'zh' ? 'zh-CN' : lang === 'ja' ? 'ja-JP' : 'en-US',
                { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }
              )
              const color = threadColor(ev.id)

              return (
                <div
                  key={ev.id}
                  className={cn('border-l-2 pl-4 py-5 pr-5 space-y-2', color)}
                >
                  <div className="flex items-start justify-between gap-2">
                    <h4 className="font-medium text-sm leading-tight line-clamp-1 flex-1">
                      {ev.topic || what}
                    </h4>
                    <span className="text-[9px] text-muted-foreground whitespace-nowrap font-mono shrink-0">
                      {dateStr}
                    </span>
                  </div>
                  <p className="text-[11px] text-muted-foreground line-clamp-2 leading-relaxed">
                    {what}
                  </p>
                  {who && (
                    <p className="text-[10px] text-muted-foreground/70 italic truncate">— {who}</p>
                  )}
                  <div className="flex gap-1.5 flex-wrap">
                    {ev.tags.slice(0, 3).map(tag => (
                      <Badge
                        key={tag}
                        variant="secondary"
                        className="text-[9px] px-1.5 py-0 h-4 font-normal"
                      >
                        #{tag}
                      </Badge>
                    ))}
                    {ev.salience > 0.7 && (
                      <Badge className="text-[9px] px-1.5 py-0 h-4 font-normal bg-accent-foreground/15 text-accent-foreground border-0 hover:bg-accent-foreground/20">
                        ★ {i18n.landing.highSalience}
                      </Badge>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
