'use client'

import { useMemo } from 'react'
import type { DateRange } from 'react-day-picker'
import type { SpindleCard as SpindleCardData } from '@/lib/events-aggregator'
import { useI18n } from '@/lib/store'
import { SpindleCard } from './spindle-card'

interface SpindleGridProps {
  spindles: SpindleCardData[]
  search: string
  activeTags: Set<string>
  dateRange?: DateRange
  onOpen: (groupId: string) => void
}

function inRange(start: string, dateRange?: DateRange) {
  if (!dateRange?.from) return true
  const ts = new Date(start).getTime()
  const from = dateRange.from.getTime()
  const to = dateRange.to ? dateRange.to.getTime() + 86400000 : from + 86400000
  return ts >= from && ts <= to
}

function matchesSpindle(spindle: SpindleCardData, search: string, activeTags: Set<string>, dateRange?: DateRange) {
  const q = search.trim().toLowerCase()
  if (q) {
    const hit = spindle.name.toLowerCase().includes(q) ||
      spindle.groupId.toLowerCase().includes(q) ||
      spindle.events.some(ev =>
        (ev.content || '').toLowerCase().includes(q) ||
        (ev.topic || '').toLowerCase().includes(q) ||
        (ev.tags || []).some(tag => tag.toLowerCase().includes(q)) ||
        (ev.participants || []).some(name => name.toLowerCase().includes(q))
      )
    if (!hit) return false
  }
  if (activeTags.size > 0 && !spindle.events.some(ev => (ev.tags ?? []).some(tag => activeTags.has(tag)))) return false
  if (dateRange?.from && !spindle.events.some(ev => inRange(ev.start, dateRange))) return false
  return true
}

export function SpindleGrid({ spindles, search, activeTags, dateRange, onOpen }: SpindleGridProps) {
  const { i18n } = useI18n()
  // Each match scans every event in the spindle — recompute only when filters change.
  const visible = useMemo(
    () => spindles.filter(spindle => matchesSpindle(spindle, search, activeTags, dateRange)),
    [spindles, search, activeTags, dateRange])
  const totalEvents = useMemo(
    () => spindles.reduce((sum, spindle) => sum + spindle.total, 0),
    [spindles])

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-4 px-4 py-4">
        <section className="rounded-md border bg-muted/10 px-4 py-3">
          <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
            {i18n.events.todayInTheLoom}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {i18n.events.loomSummary
              .replace('{filtered}', String(visible.length))
              .replace('{total}', String(totalEvents))}
          </p>
        </section>

        <div className="grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-3.5">
          {visible.map((spindle, index) => (
            <SpindleCard key={spindle.groupId} spindle={spindle} index={index} onOpen={onOpen} />
          ))}
        </div>
      </div>
    </div>
  )
}
