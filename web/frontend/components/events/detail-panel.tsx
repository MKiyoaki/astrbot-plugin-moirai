'use client'

import { useRef, useEffect } from 'react'
import { X, Tag, Users, Zap, BarChart2, Lock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Sheet, SheetContent, SheetHeader, SheetTitle,
} from '@/components/ui/sheet'
import { EventDetailCard } from '@/components/events/event-dialogs'
import { useIsMobile } from '@/hooks/use-mobile'
import { useApp } from '@/lib/store'
import { type ApiEvent } from '@/lib/api'
import { cn } from '@/lib/utils'
import { getTagColor } from '@/lib/colors'

interface DetailPanelProps {
  focusedEvent: ApiEvent | null
  axisEvents: ApiEvent[]
  allEvents?: ApiEvent[]
  onClose: () => void
  onEdit: (ev: ApiEvent) => void
  onDelete: (ev: ApiEvent) => void
  onLockToggle: (ev: ApiEvent) => void
  onArchive?: (ev: ApiEvent) => void
  onSelect: (ev: ApiEvent) => void
  className?: string
}

// ── Mini stats panel shown when no event is selected ─────────────────────────

function MiniStats({ events }: { events: ApiEvent[] }) {
  if (!events.length) return null

  // Top tags
  const tagCounts: Record<string, number> = {}
  for (const ev of events) {
    for (const t of ev.tags ?? []) tagCounts[t] = (tagCounts[t] ?? 0) + 1
  }
  const topTags = Object.entries(tagCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12)

  // Salience buckets (0-25, 25-50, 50-75, 75-100)
  const buckets = [0, 0, 0, 0]
  for (const ev of events) {
    const idx = Math.min(3, Math.floor((ev.salience ?? 0) * 4))
    buckets[idx]++
  }
  const maxBucket = Math.max(...buckets, 1)

  // Top participants
  const participantCounts: Record<string, number> = {}
  for (const ev of events) {
    for (const p of ev.participants ?? []) {
      participantCounts[p] = (participantCounts[p] ?? 0) + 1
    }
  }
  const topParticipants = Object.entries(participantCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)

  const locked   = events.filter(e => e.is_locked).length
  const archived = events.filter(e => e.status === 'archived').length

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b shrink-0">
        <span className="text-sm font-semibold">统计概览</span>
        <p className="text-[9px] font-mono uppercase tracking-wider text-muted-foreground/60 mt-0.5">
          EVENT STREAM · SUMMARY
        </p>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-4 space-y-5">

          {/* Counts */}
          <div className="grid grid-cols-2 gap-2">
            {[
              { label: '总事件', value: events.length, icon: <BarChart2 className="size-3" /> },
              { label: '已锁定', value: locked, icon: <Lock className="size-3" /> },
            ].map(({ label, value, icon }) => (
              <div key={label} className="rounded-md border bg-muted/20 px-3 py-2 flex flex-col gap-1">
                <div className="flex items-center gap-1 text-[10px] text-muted-foreground">{icon}{label}</div>
                <span className="text-lg font-semibold font-mono leading-none">{value}</span>
              </div>
            ))}
          </div>

          {/* Salience distribution */}
          <div>
            <div className="flex items-center gap-1.5 mb-2 text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
              <Zap className="size-3" />显著度分布
            </div>
            <div className="flex items-end gap-1 h-14">
              {buckets.map((count, i) => {
                const labels = ['0–25', '25–50', '50–75', '75–100']
                const pct = count / maxBucket
                const bgColors = [
                  'bg-primary/30',
                  'bg-primary/50',
                  'bg-primary/70',
                  'bg-primary',
                ]
                return (
                  <div key={i} className="flex flex-col items-center gap-1 flex-1">
                    <span className="text-[9px] font-mono text-muted-foreground/60">{count}</span>
                    <div
                      className={cn("w-full rounded-t-sm transition-all duration-500", bgColors[i])}
                      style={{
                        height: `${Math.max(4, pct * 36)}px`,
                      }}
                    />
                    <span className="text-[8px] font-mono text-muted-foreground/40">{labels[i]}</span>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Tags */}
          {topTags.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 mb-2 text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
                <Tag className="size-3" />热门标签
              </div>
              <div className="flex flex-wrap gap-1.5">
                {topTags.map(([tag, count]) => {
                  const color = getTagColor(tag)
                  return (
                    <span key={tag}
                      className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-mono"
                      style={{
                        background: `color-mix(in srgb, ${color} 15%, transparent)`,
                        color,
                        border: `1px solid color-mix(in srgb, ${color} 30%, transparent)`,
                      }}>
                      #{tag}
                      <span className="opacity-50">{count}</span>
                    </span>
                  )
                })}
              </div>
            </div>
          )}

          {/* Participants */}
          {topParticipants.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 mb-2 text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
                <Users className="size-3" />参与者
              </div>
              <div className="space-y-1.5">
                {topParticipants.map(([name, count]) => (
                  <div key={name} className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground truncate">{name}</span>
                    <div className="flex items-center gap-2 shrink-0 ml-2">
                      <div className="h-1 rounded-full bg-primary/20 overflow-hidden" style={{ width: 40 }}>
                        <div className="h-full rounded-full bg-primary/50 transition-all"
                          style={{ width: `${(count / (topParticipants[0]?.[1] ?? 1)) * 100}%` }} />
                      </div>
                      <span className="text-[10px] font-mono text-muted-foreground/60 w-4 text-right">{count}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Archived count */}
          {archived > 0 && (
            <p className="text-[10px] text-muted-foreground/40 font-mono">
              {archived} 个事件已封存
            </p>
          )}
        </div>
      </ScrollArea>
    </div>
  )
}

// ── Detail body (existing axis event list) ────────────────────────────────────

function DetailBody({
  focusedEvent, axisEvents, onClose, onEdit, onDelete, onLockToggle, onArchive, onSelect,
}: DetailPanelProps) {
  const { i18n, sudo } = useApp()
  const focusedCardRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!focusedEvent) return
    const id = setTimeout(() => {
      focusedCardRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    }, 300)
    return () => clearTimeout(id)
  }, [focusedEvent?.id])

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b shrink-0 bg-background/80 backdrop-blur sticky top-0 z-10">
        <div className="flex flex-col min-w-0 pr-4">
          <span className="text-sm font-semibold truncate">{i18n.events.detailTitle}</span>
          <p className="text-[9px] font-mono uppercase tracking-wider text-muted-foreground/60 truncate">
            {focusedEvent?.group || i18n.events.privateChat} · AXIS
          </p>
        </div>
        <Button variant="ghost" size="icon" className="size-8 shrink-0 -mr-2" onClick={onClose}>
          <X className="size-4" />
        </Button>
      </div>

      <ScrollArea className="flex-1 overscroll-contain">
        <div className="p-4 space-y-4 w-full min-w-0 overflow-x-hidden">
          {axisEvents.map((ev, idx) => (
            <div
              key={ev.id}
              ref={ev.id === focusedEvent?.id ? focusedCardRef : null}
              className="animate-in fade-in slide-in-from-right-4 duration-300 fill-mode-both"
              style={{ animationDelay: `${Math.min(idx * 40, 250)}ms` }}
            >
              <EventDetailCard
                event={ev}
                isFocused={ev.id === focusedEvent?.id}
                onEdit={onEdit}
                onDelete={onDelete}
                onLockToggle={onLockToggle}
                onArchive={onArchive}
                onSelect={() => onSelect(ev)}
                sudoMode={sudo}
              />
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}

// ── Public component ──────────────────────────────────────────────────────────

export function DetailPanel(props: DetailPanelProps) {
  const { focusedEvent, onClose, allEvents = [], className } = props
  const isMobile = useIsMobile()
  const open = !!focusedEvent

  if (isMobile) {
    return (
      <Sheet open={open} onOpenChange={v => !v && onClose()}>
        <SheetContent
          side="right"
          className="w-full sm:max-w-[440px] p-0 flex flex-col gap-0 border-l bg-background shadow-2xl"
        >
          <SheetHeader className="sr-only">
            <SheetTitle>事件详情</SheetTitle>
          </SheetHeader>
          {open && <DetailBody {...props} />}
        </SheetContent>
      </Sheet>
    )
  }

  return (
    <aside
      data-testid="detail-panel"
      className={cn(
        'w-80 lg:w-[400px] xl:w-[450px] 2xl:w-[500px] flex flex-col border-l bg-background/95 backdrop-blur shrink-0 overflow-hidden transition-all duration-300',
        className
      )}
    >
      <div
        key={open ? 'detail' : 'stats'}
        className="flex flex-col h-full animate-in fade-in duration-200"
      >
        {open
          ? <DetailBody {...props} />
          : <MiniStats events={allEvents} />
        }
      </div>
    </aside>
  )
}
