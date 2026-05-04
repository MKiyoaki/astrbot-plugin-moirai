'use client'

import { useState } from 'react'
import { Pencil, Trash2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { TagFilter } from '@/components/shared/tag-filter'
import { type ApiEvent } from '@/lib/api'
import { i18n } from '@/lib/i18n'
import { cn } from '@/lib/utils'

const THREAD_COLORS = ['#7dd3fc', '#86efac', '#fca5a5', '#c4b5fd', '#fdba74', '#67e8f9', '#fde68a']

interface EventTimelineProps {
  events: ApiEvent[]
  maxCount: number
  highlightIds?: Set<string>
  tagList: { name: string; count: number }[]
  onEventClick: (ev: ApiEvent) => void
  onEdit: (ev: ApiEvent) => void
  onDelete: (ev: ApiEvent) => void
}

export function EventTimeline({
  events,
  maxCount,
  highlightIds = new Set(),
  tagList,
  onEventClick,
  onEdit,
  onDelete,
}: EventTimelineProps) {
  const [activeTags, setActiveTags] = useState<Set<string>>(new Set())
  const [activeThreads, setActiveThreads] = useState<Set<string>>(new Set())

  // Sort by salience desc, slice to density cap
  const bySalience = [...events]
    .sort((a, b) => b.salience - a.salience)
    .slice(0, maxCount)

  if (!bySalience.length) {
    return (
      <div className="flex flex-col items-center py-16 text-sm text-muted-foreground">
        <p>{i18n.events.noData}</p>
        <p className="mt-1 text-xs">{i18n.events.noDataHint}</p>
      </div>
    )
  }

  // Assign a stable color per thread (group_id)
  const threadColorMap = new Map<string, string>()
  let colorIdx = 0
  for (const ev of bySalience) {
    const key = ev.group || '__pvt__'
    if (!threadColorMap.has(key)) {
      threadColorMap.set(key, THREAD_COLORS[colorIdx % THREAD_COLORS.length])
      colorIdx++
    }
  }

  // Apply tag + thread filters, then sort by time descending
  const visible = bySalience
    .filter(ev => {
      if (activeTags.size > 0 && !(ev.tags ?? []).some(t => activeTags.has(t))) return false
      const key = ev.group || '__pvt__'
      if (activeThreads.size > 0 && !activeThreads.has(key)) return false
      return true
    })
    .sort((a, b) => new Date(b.start).getTime() - new Date(a.start).getTime())

  const toggleThread = (key: string) => {
    const next = new Set(activeThreads)
    if (next.has(key)) next.delete(key); else next.add(key)
    setActiveThreads(next)
  }

  return (
    <div className="flex h-full flex-col">
      <TagFilter tags={tagList} value={activeTags} onChange={setActiveTags} />

      {/* Thread legend pills */}
      {threadColorMap.size > 1 && (
        <div className="shrink-0 border-b px-4 py-2">
          <p className="mb-1.5 text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">
            {i18n.events.threadAxis}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {Array.from(threadColorMap.entries()).map(([key, color]) => {
              const active = activeThreads.size === 0 || activeThreads.has(key)
              const label = key === '__pvt__' ? i18n.events.privateChat : key
              return (
                <button
                  key={key}
                  onClick={() => toggleThread(key)}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded border px-2.5 py-0.5 text-[10.5px] transition-all',
                    !active && 'opacity-40',
                  )}
                  style={active ? {
                    borderColor: `${color}55`,
                    background: `${color}12`,
                    color,
                  } : undefined}
                >
                  <span
                    className="inline-block size-1.5 shrink-0 rounded-full"
                    style={{ background: active ? color : undefined }}
                  />
                  {label}
                </button>
              )
            })}
          </div>
        </div>
      )}

      <ScrollArea className="flex-1">
        <div className="flex flex-col gap-2 p-4">
          {visible.length === 0 ? (
            <div className="py-12 text-center text-sm text-muted-foreground">
              {i18n.events.noData}
            </div>
          ) : visible.map(ev => {
            const key = ev.group || '__pvt__'
            const color = threadColorMap.get(key) ?? THREAD_COLORS[0]
            const isHighlighted = highlightIds.has(ev.id)

            return (
              <div
                key={ev.id}
                onClick={() => onEventClick(ev)}
                className={cn(
                  'group relative flex cursor-pointer flex-col gap-1.5 rounded-lg border bg-card p-3 transition-all hover:shadow-sm',
                  isHighlighted && 'ring-2 ring-primary',
                )}
                style={{ borderLeftColor: color, borderLeftWidth: 3 }}
              >
                {/* Title */}
                <p className="pr-14 text-sm font-medium leading-snug">
                  {ev.content || ev.topic || ev.id}
                </p>

                {/* Metadata */}
                <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                  <span>
                    {new Date(ev.start).toLocaleString('zh-CN', {
                      month: '2-digit', day: '2-digit',
                      hour: '2-digit', minute: '2-digit',
                    })}
                  </span>
                  {ev.group && <span className="font-mono">{ev.group}</span>}
                  {(ev.participants?.length ?? 0) > 0 && (
                    <span>
                      {ev.participants!.slice(0, 2).join(', ')}
                      {ev.participants!.length > 2 ? ` +${ev.participants!.length - 2}` : ''}
                    </span>
                  )}
                </div>

                {/* Tags + salience */}
                <div className="flex flex-wrap items-center gap-1">
                  {(ev.tags ?? []).slice(0, 4).map(tag => (
                    <Badge key={tag} variant="secondary" className="h-4 px-1.5 text-[10px]">
                      {tag}
                    </Badge>
                  ))}
                  <span
                    className="ml-auto font-mono text-[11px]"
                    style={{
                      color: ev.salience >= 0.85 ? '#f59e0b'
                        : ev.salience >= 0.70 ? '#38bdf8'
                        : undefined,
                    }}
                  >
                    {(ev.salience * 100).toFixed(0)}%
                  </span>
                </div>

                {/* Hover action buttons */}
                <div
                  className="absolute right-2 top-2 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100"
                  onClick={e => e.stopPropagation()}
                >
                  <Button variant="ghost" size="icon-xs" onClick={() => onEdit(ev)}>
                    <Pencil className="size-3" />
                  </Button>
                  <Button variant="destructive" size="icon-xs" onClick={() => onDelete(ev)}>
                    <Trash2 className="size-3" />
                  </Button>
                </div>
              </div>
            )
          })}
        </div>
      </ScrollArea>
    </div>
  )
}
