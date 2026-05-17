'use client'

import { type ApiEvent } from '@/lib/api'
import { CHART_COLORS as THREAD_COLORS } from '@/lib/colors'
import { cn } from '@/lib/utils'

export interface SourceThread {
  id: string
  label: string
  color: string
  count: number
}

/** Derive ordered threads from a list of events — colour assignment matches EventTimeline */
export function buildThreads(events: ApiEvent[], privateLabel: string): SourceThread[] {
  const seen: SourceThread[] = []
  const map: Record<string, SourceThread> = {}
  for (const ev of events) {
    const key = ev.group || '__pvt__'
    if (!map[key]) {
      const thread: SourceThread = {
        id: key,
        label: key === '__pvt__' ? privateLabel : key,
        color: THREAD_COLORS[seen.length % THREAD_COLORS.length],
        count: 0,
      }
      map[key] = thread
      seen.push(thread)
    }
    map[key].count++
  }
  return seen
}

interface SourcePanelProps {
  threads: SourceThread[]
  dimmedIds: Set<string>
  onToggle: (id: string) => void
  totalEvents: number
  totalConversations?: number
  className?: string
}

export function SourcePanel({
  threads,
  dimmedIds,
  onToggle,
  totalEvents,
  totalConversations,
  className,
}: SourcePanelProps) {
  return (
    <aside
      data-testid="source-panel"
      className={cn(
        'hidden md:flex flex-col w-52 shrink-0 border-r bg-muted/5 overflow-y-auto',
        className
      )}
    >
      {/* Panel header — shows live counts */}
      <div className="px-4 py-3 border-b shrink-0">
        <p className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted-foreground/60">
          {threads.length} SOURCES · {totalEvents} EVENTS{totalConversations != null ? ` · ${totalConversations} THREADS` : ''}
        </p>
      </div>

      {/* Source list */}
      <div className="flex-1 py-2">
        {threads.map(th => {
          const active = !dimmedIds.has(th.id)
          return (
            <button
              key={th.id}
              onClick={() => onToggle(th.id)}
              className={cn(
                'w-full flex items-center gap-3 px-4 py-2.5 text-left transition-opacity hover:bg-muted/20',
                !active && 'opacity-40'
              )}
              aria-pressed={active}
            >
              {/* Colour strip */}
              <span
                className="w-1 h-7 rounded-full shrink-0"
                style={{ background: th.color }}
              />
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold truncate">{th.label}</p>
                <p className="font-mono text-[9px] text-muted-foreground/60 uppercase tracking-wider truncate">
                  {th.id === '__pvt__' ? 'PRIVATE · DM' : 'GROUP'}
                </p>
              </div>
              {/* Event count badge */}
              <span
                className="shrink-0 min-w-[20px] text-center text-[10px] font-mono font-bold rounded px-1"
                style={{
                  background: active
                    ? `color-mix(in srgb, ${th.color} 18%, transparent)`
                    : undefined,
                  color: active ? th.color : 'var(--muted-foreground)',
                }}
              >
                {th.count}
              </span>
            </button>
          )
        })}
      </div>

    </aside>
  )
}
