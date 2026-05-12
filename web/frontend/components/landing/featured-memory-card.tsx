'use client'

import Link from 'next/link'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useApp } from '@/lib/store'
import type { ApiEvent } from '@/lib/api'
import { parseSummaryTopics } from '@/lib/utils'

interface FeaturedMemoryCardProps {
  event: ApiEvent | null
}

export function FeaturedMemoryCard({ event }: FeaturedMemoryCardProps) {
  const { i18n, lang } = useApp()

  if (!event) {
    return (
      <Card className="flex flex-col justify-center items-center min-h-[260px] bg-accent/20 border-dashed border-accent-foreground/20">
        <p className="text-xs text-muted-foreground italic">{i18n.landing.noFeaturedMemory}</p>
      </Card>
    )
  }

  const topics = parseSummaryTopics(event.summary)
  const quote = topics?.[0]?.what ?? event.summary ?? ''
  const who = topics?.[0]?.who ?? ''

  const dateStr = new Date(event.start).toLocaleDateString(
    lang === 'zh' ? 'zh-CN' : lang === 'ja' ? 'ja-JP' : 'en-US',
    { month: 'numeric', day: 'numeric' }
  )

  return (
    <Link href="/events" className="block h-full">
      <Card className="flex flex-col justify-between min-h-[260px] h-full bg-accent/25 border-accent-foreground/15 hover:bg-accent/35 transition-colors cursor-pointer p-6">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-accent-foreground text-xs font-mono tracking-wider">★</span>
            <p className="text-[10px] uppercase tracking-[0.15em] text-accent-foreground/70 font-mono">
              {i18n.landing.featuredMemory}
            </p>
          </div>
        </div>

        <CardContent className="p-0 flex-1 flex flex-col justify-center py-4">
          <blockquote className="text-lg font-serif leading-relaxed text-foreground line-clamp-4">
            &ldquo;{quote}&rdquo;
          </blockquote>
          {who && (
            <p className="mt-2 text-xs text-muted-foreground italic">— {who}</p>
          )}
        </CardContent>

        <div className="flex items-center justify-between mt-2">
          <div className="flex gap-1.5 flex-wrap">
            {event.tags.slice(0, 3).map(tag => (
              <Badge
                key={tag}
                variant="secondary"
                className="text-[9px] px-1.5 py-0 h-4 font-normal bg-accent-foreground/10 text-accent-foreground border-0"
              >
                #{tag}
              </Badge>
            ))}
          </div>
          <span className="text-[10px] text-muted-foreground whitespace-nowrap font-mono">
            {dateStr}
          </span>
        </div>
      </Card>
    </Link>
  )
}
