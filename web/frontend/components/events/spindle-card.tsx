'use client'

import { memo } from 'react'
import { Archive, ArrowRight, Clock, Lock, Sparkles, Users } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import type { SpindleCard as SpindleCardData } from '@/lib/events-aggregator'
import { useI18n } from '@/lib/store'
import { cn } from '@/lib/utils'
import { MiniThread } from './mini-thread'

interface SpindleCardProps {
  spindle: SpindleCardData
  index: number
  onOpen: (groupId: string) => void
}

function lastActiveLabel(value: string | null) {
  if (!value) return '--'
  return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function participantCount(events: SpindleCardData['events']) {
  const names = new Set<string>()
  for (const ev of events) {
    for (const participant of ev.participants ?? []) names.add(participant)
  }
  return names.size
}

function SpindleCardImpl({ spindle, index, onOpen }: SpindleCardProps) {
  const { i18n } = useI18n()
  const participantTotal = participantCount(spindle.events)

  return (
    <button
      type="button"
      className="group w-full text-left animate-in fade-in slide-in-from-bottom-3 duration-500 fill-mode-both"
      style={{ animationDelay: `${Math.min(index * 35, 360)}ms` }}
      onClick={() => onOpen(spindle.groupId)}
      aria-label={`${i18n.events.unspool}: ${spindle.name}`}
    >
      <Card
        className="overflow-hidden rounded-md bg-card/75 backdrop-blur-sm transition-all duration-300 hover:-translate-y-0.5 hover:shadow-lg"
        style={{ borderColor: `color-mix(in srgb, ${spindle.accent} 34%, var(--border))` }}
      >
        <CardContent className="flex flex-col gap-3 p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="flex min-w-0 items-start gap-3">
              <div
                className="flex size-11 shrink-0 items-center justify-center rounded-md border bg-background/70 font-serif text-xl font-semibold"
                style={{ borderColor: spindle.accent, color: spindle.accent }}
                aria-hidden
              >
                {spindle.glyph}
              </div>
              <div className="min-w-0">
                <p className="truncate font-serif text-base font-semibold leading-tight">{spindle.name}</p>
                <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                  {i18n.events.spindleLabel} {spindle.issue}
                </p>
              </div>
            </div>
            <div className="shrink-0 text-right">
              <p className="font-mono text-lg font-semibold leading-none" style={{ color: spindle.accent }}>
                {spindle.total}
              </p>
              <p className="mt-1 font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">
                {i18n.events.knotsLabel}
              </p>
            </div>
          </div>

          <div className="relative rounded-md border bg-muted/10 px-2 py-2">
            <svg className="pointer-events-none absolute right-2 top-1 h-7 w-24 opacity-50 transition-opacity group-hover:opacity-90" viewBox="0 0 96 28" aria-hidden>
              <path d="M2 18 Q 24 2 45 16 T 94 12" fill="none" stroke={spindle.accent} strokeWidth="1.2" strokeLinecap="round" className="silk-flow fast" />
              <circle cx="44" cy="16" r="2.5" fill={spindle.accent} />
              <circle cx="73" cy="12" r="1.8" fill="var(--background)" stroke={spindle.accent} />
            </svg>
            <MiniThread events={spindle.events} accent={spindle.accent} />
          </div>

          <div className="flex flex-wrap gap-1.5">
            {spindle.topTags.length > 0 ? spindle.topTags.map(tag => (
              <Badge key={tag} variant="outline" className="h-5 rounded px-1.5 font-mono text-[10px]">
                #{tag}
              </Badge>
            )) : (
              <Badge variant="secondary" className="h-5 rounded px-1.5 font-mono text-[10px]">
                {i18n.events.noData}
              </Badge>
            )}
          </div>

          <div className="flex items-center justify-between gap-2 border-t pt-3 text-[10px] text-muted-foreground">
            {[
              { icon: Users, value: participantTotal },
              { icon: Clock, value: lastActiveLabel(spindle.lastActiveAt) },
              { icon: Sparkles, value: spindle.highSalience },
              { icon: Lock, value: spindle.locked },
              { icon: Archive, value: spindle.archived },
            ].map(({ icon: Icon, value }, statIndex) => (
              <span key={statIndex} className="inline-flex min-w-0 items-center gap-1 font-mono">
                <Icon className="size-3 shrink-0" />
                <span className={cn(typeof value === 'string' && 'truncate')}>{value}</span>
              </span>
            ))}
          </div>

          <div className="flex items-center justify-end font-mono text-[10px] font-semibold uppercase tracking-[0.18em] opacity-0 transition-opacity group-hover:opacity-100" style={{ color: spindle.accent }}>
            {i18n.events.unspool}
            <ArrowRight className="ml-1 size-3" />
          </div>
        </CardContent>
      </Card>
    </button>
  )
}

/** Re-renders only when its own props change (see useI18n + stable parent callbacks). */
export const SpindleCard = memo(SpindleCardImpl)
