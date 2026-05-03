'use client'

import { useEffect, useRef, useCallback } from 'react'
import { Pencil, Trash2, ArrowRight } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { type ApiEvent } from '@/lib/api'
import { cn } from '@/lib/utils'
import { i18n } from '@/lib/i18n'

interface EventTimelineProps {
  events: ApiEvent[]
  maxCount: number
  highlightIds?: Set<string>
  onEventClick: (ev: ApiEvent) => void
  onEdit: (ev: ApiEvent) => void
  onDelete: (ev: ApiEvent) => void
}

function esc(s: string | null | undefined) {
  return String(s ?? '')
}

export function EventTimeline({
  events,
  maxCount,
  highlightIds = new Set(),
  onEventClick,
  onEdit,
  onDelete,
}: EventTimelineProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const bridgeLayerRef = useRef<SVGSVGElement>(null)

  const sorted = [...events]
    .sort((a, b) => b.salience - a.salience)
    .slice(0, maxCount)
    .sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime())

  const drawBridges = useCallback(() => {
    const container = containerRef.current
    const svg = bridgeLayerRef.current
    if (!container || !svg) return

    const containerRect = container.getBoundingClientRect()
    svg.innerHTML = ''
    svg.setAttribute('width', String(containerRect.width))
    svg.setAttribute('height', String(container.scrollHeight))

    events.forEach(ev => {
      if (!ev.inherit_from?.length) return
      ev.inherit_from.forEach(parentId => {
        const parentDot = container.querySelector<HTMLElement>(`[data-dot="${parentId}"]`)
        const childDot = container.querySelector<HTMLElement>(`[data-dot="${ev.id}"]`)
        if (!parentDot || !childDot) return
        const pRect = parentDot.getBoundingClientRect()
        const cRect = childDot.getBoundingClientRect()
        const x = containerRect.width / 2
        const y1 = pRect.top - containerRect.top + pRect.height / 2 + container.scrollTop
        const y2 = cRect.top - containerRect.top + cRect.height / 2 + container.scrollTop
        if (Math.abs(y2 - y1) < 4) return
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line')
        line.setAttribute('x1', String(x))
        line.setAttribute('y1', String(y1))
        line.setAttribute('x2', String(x))
        line.setAttribute('y2', String(y2))
        line.setAttribute('stroke', 'var(--color-border)')
        line.setAttribute('stroke-width', '1.5')
        line.setAttribute('stroke-dasharray', '4 3')
        svg.appendChild(line)
      })
    })
  }, [events])

  useEffect(() => {
    const timer = setTimeout(drawBridges, 80)
    return () => clearTimeout(timer)
  }, [sorted, drawBridges])

  if (!sorted.length) {
    return (
      <div className="text-muted-foreground flex flex-col items-center py-16 text-sm">
        <p>{i18n.events.noData}</p>
        <p className="mt-1 text-xs">{i18n.events.noDataHint}</p>
      </div>
    )
  }

  return (
    <div ref={containerRef} className="relative px-4 py-6">
      {/* SVG bridge layer */}
      <svg
        ref={bridgeLayerRef}
        className="pointer-events-none absolute inset-0"
        style={{ zIndex: 0 }}
      />

      {/* Center line */}
      <div className="bg-border absolute top-0 bottom-0 left-1/2 w-px -translate-x-px" />

      <div className="relative flex flex-col gap-8" style={{ zIndex: 1 }}>
        {sorted.map((ev, i) => {
          const side = i % 2 === 0 ? 'left' : 'right'
          const highlighted = highlightIds.has(ev.id)
          const timeStr = new Date(ev.start).toLocaleDateString('zh-CN', {
            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
          })
          return (
            <div
              key={ev.id}
              className={cn(
                'flex items-start gap-4',
                side === 'left' ? 'flex-row' : 'flex-row-reverse',
              )}
            >
              {/* Card */}
              <div className="w-[calc(50%-2rem)]">
                <div
                  className={cn(
                    'group/card bg-card ring-foreground/10 cursor-pointer rounded-xl p-3 text-sm shadow-sm ring-1 transition-all hover:ring-2 hover:ring-primary/30',
                    highlighted && 'ring-2 ring-primary',
                  )}
                  onClick={() => onEventClick(ev)}
                >
                  <div className="mb-1 flex items-start justify-between gap-2">
                    <div className="font-medium leading-snug">{esc(ev.content)}</div>
                    <div
                      className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover/card:opacity-100"
                      onClick={e => e.stopPropagation()}
                    >
                      <Button variant="ghost" size="icon-xs" onClick={() => onEdit(ev)}>
                        <Pencil />
                      </Button>
                      <Button variant="destructive" size="icon-xs" onClick={() => onDelete(ev)}>
                        <Trash2 />
                      </Button>
                    </div>
                  </div>
                  <div className="text-muted-foreground text-xs">{timeStr}</div>
                  <div className="mt-2 flex flex-wrap gap-1">
                    <Badge variant="secondary" className="text-xs">
                      {(ev.salience * 100).toFixed(0)}%
                    </Badge>
                    <Badge variant="outline" className="text-xs">
                      {ev.group ? esc(ev.group.slice(0, 12)) : i18n.events.privateChat}
                    </Badge>
                    {ev.participants?.length > 0 && (
                      <Badge variant="outline" className="text-xs">
                        {ev.participants.length} 人
                      </Badge>
                    )}
                    {ev.tags?.slice(0, 3).map(t => (
                      <Badge key={t} variant="secondary" className="text-xs">
                        {esc(t)}
                      </Badge>
                    ))}
                  </div>
                  {ev.inherit_from?.length > 0 && (
                    <div className="text-muted-foreground mt-1.5 flex items-center gap-1 text-xs">
                      <ArrowRight className="size-3" />
                      承接自 {ev.inherit_from.length} 个事件
                    </div>
                  )}
                </div>
              </div>

              {/* Dot */}
              <div className="relative flex size-4 shrink-0 items-center justify-center">
                <div
                  data-dot={ev.id}
                  className={cn(
                    'size-3 rounded-full ring-2 ring-background transition-all',
                    highlighted
                      ? 'bg-primary ring-primary/40 scale-125'
                      : ev.inherit_from?.length
                        ? 'bg-primary/70'
                        : 'bg-muted-foreground/60',
                  )}
                />
              </div>

              {/* Spacer for the other side */}
              <div className="w-[calc(50%-2rem)]" />
            </div>
          )
        })}
      </div>
    </div>
  )
}
