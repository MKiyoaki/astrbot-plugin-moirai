'use client'

import { useState, useRef } from 'react'
import { Pencil, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { TagFilter } from '@/components/shared/tag-filter'
import { type ApiEvent } from '@/lib/api'
import { i18n } from '@/lib/i18n'

const THREAD_COLORS = ['#7dd3fc', '#86efac', '#fca5a5', '#c4b5fd', '#fdba74', '#67e8f9', '#fde68a']
const AX = 28, FTX = 58, TW = 14, TG = 16, NR = 5, RH = 68, TP = 40, BG = 14, MERGE = 7_200_000

const tx = (i: number) => FTX + i * (TW + TG)

interface Thread {
  id: string
  label: string
  color: string
  events: ApiEvent[]
}

interface RowInfo {
  idx: number
  tsMs: number
}

function buildRowMap(threads: Thread[]) {
  const evts = threads
    .flatMap(t => t.events.map(ev => ({ ...ev, tsMs: new Date(ev.start).getTime() })))
    .sort((a, b) => a.tsMs - b.tsMs)

  const rows: RowInfo[] = []
  const erm: Record<string, number> = {}

  for (const ev of evts) {
    const last = rows[rows.length - 1]
    if (last && ev.tsMs - last.tsMs <= MERGE) {
      erm[ev.id] = last.idx
    } else {
      const idx = rows.length
      rows.push({ idx, tsMs: ev.tsMs })
      erm[ev.id] = idx
    }
  }

  return { erm, total: rows.length, rows }
}

function fmtDate(ts: number) {
  return new Date(ts).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}

function fmtTime(ts: string) {
  return new Date(ts).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

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
  highlightIds: _highlightIds,
  tagList,
  onEventClick,
  onEdit,
  onDelete,
}: EventTimelineProps) {
  const [activeTags, setActiveTags] = useState<Set<string>>(new Set())
  const [dimmedIds, setDimmedIds] = useState<Set<string>>(new Set())
  const [hoveredThreadId, setHoveredThreadId] = useState<string | null>(null)
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Sort by salience desc, slice, re-sort by time asc
  const visible = [...events]
    .sort((a, b) => b.salience - a.salience)
    .slice(0, maxCount)
    .sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime())

  if (!visible.length) {
    return (
      <div className="flex flex-col items-center py-16 text-sm text-muted-foreground">
        <p>{i18n.events.noData}</p>
        <p className="mt-1 text-xs">{i18n.events.noDataHint}</p>
      </div>
    )
  }

  // Group into threads by group_id
  const allThreads: Thread[] = []
  const threadMap: Record<string, Thread> = {}
  for (const ev of visible) {
    const key = ev.group || '__pvt__'
    if (!threadMap[key]) {
      const thread: Thread = {
        id: key,
        label: key === '__pvt__' ? i18n.events.privateChat : key,
        color: THREAD_COLORS[allThreads.length % THREAD_COLORS.length],
        events: [],
      }
      threadMap[key] = thread
      allThreads.push(thread)
    }
    threadMap[key].events.push(ev)
  }

  // Tag filter: which threads match
  const matchedIds = new Set<string>()
  if (activeTags.size === 0) {
    for (const th of allThreads) matchedIds.add(th.id)
  } else {
    for (const th of allThreads) {
      if (th.events.some(ev => (ev.tags ?? []).some(t => activeTags.has(t)))) {
        matchedIds.add(th.id)
      }
    }
  }

  const threads = allThreads.filter(th => matchedIds.has(th.id))

  const handleTagsChange = (next: Set<string>) => {
    setActiveTags(next)
    setDimmedIds(new Set())
  }

  const toggleDim = (id: string) => {
    const next = new Set(dimmedIds)
    if (next.has(id)) next.delete(id); else next.add(id)
    setDimmedIds(next)
  }

  const enterHover = (id: string) => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current)
    setHoveredThreadId(id)
  }

  const leaveHover = () => {
    hoverTimerRef.current = setTimeout(() => setHoveredThreadId(null), 150)
  }

  const keepHover = () => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current)
  }

  const getOpacity = (thread: Thread) => {
    if (hoveredThreadId !== null) return hoveredThreadId === thread.id ? 1 : 0.1
    if (dimmedIds.has(thread.id)) return 0.1
    return 1
  }

  const { erm, total, rows } = buildRowMap(threads)
  const ry = (i: number) => TP + i * RH
  const svgH = TP + total * RH + 60

  return (
    <div className="flex flex-col h-full">
      {/* Tag filter bar */}
      <TagFilter tags={tagList} value={activeTags} onChange={handleTagsChange} />

      {/* Thread toggle bar */}
      {allThreads.length > 1 && (
        <div className="border-b px-4 py-2 shrink-0">
          <p className="mb-1.5 text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">
            {i18n.events.threadAxis}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {allThreads.map(th => {
              const matched = matchedIds.has(th.id)
              const lit = matched && !dimmedIds.has(th.id)
              return (
                <button
                  key={th.id}
                  disabled={!matched}
                  onClick={() => matched && toggleDim(th.id)}
                  className="inline-flex items-center gap-1.5 rounded border px-2.5 py-0.5 text-[10.5px] transition-all"
                  style={matched ? {
                    borderColor: lit ? `${th.color}55` : undefined,
                    background: lit ? `${th.color}12` : undefined,
                    color: lit ? th.color : undefined,
                  } : { opacity: 0.38 }}
                >
                  <span
                    className="inline-block size-1.5 shrink-0 rounded-full"
                    style={{ background: lit ? th.color : undefined }}
                  />
                  {th.label}
                </button>
              )
            })}
          </div>
        </div>
      )}

      {/* Canvas */}
      <div className="relative flex-1 overflow-y-auto overflow-x-hidden" style={{ minHeight: svgH }}>
        {/* Visual SVG layer (no pointer events) */}
        <svg
          className="absolute left-0 top-0"
          style={{ width: '100%', height: svgH, pointerEvents: 'none', overflow: 'visible' }}
        >
          {/* Main axis */}
          <line
            x1={AX} y1={TP - 10} x2={AX} y2={svgH - BG}
            stroke="currentColor" strokeOpacity={0.15} strokeWidth={1.5}
          />
          {/* Row ticks + date labels */}
          {rows.map(row => (
            <g key={row.idx}>
              <line
                x1={AX - 3} y1={ry(row.idx)} x2={AX + 3} y2={ry(row.idx)}
                stroke="currentColor" strokeOpacity={0.1} strokeWidth={1}
              />
              <text
                x={AX - 5} y={ry(row.idx) + 3}
                textAnchor="end" fill="currentColor" fillOpacity={0.2}
                fontSize={9} fontFamily="monospace"
              >
                {fmtDate(row.tsMs)}
              </text>
            </g>
          ))}

          {/* Threads */}
          {threads.map((thread, ti) => {
            const x = tx(ti)
            const op = getOpacity(thread)
            const evRows = thread.events.map(ev => erm[ev.id])
            const minR = Math.min(...evRows)
            const maxR = Math.max(...evRows)
            const isHov = hoveredThreadId === thread.id

            return (
              <g key={thread.id} style={{ opacity: op, transition: 'opacity 0.15s' }}>
                {/* Vertical thread line */}
                <line
                  x1={x} y1={ry(minR)} x2={x} y2={ry(maxR)}
                  stroke={thread.color} strokeWidth={1.5} strokeOpacity={0.7}
                />
                {/* End marker */}
                <line
                  x1={x - 8} y1={ry(maxR) + 18}
                  x2={x + 8} y2={ry(maxR) + 18}
                  stroke={thread.color} strokeWidth={1} strokeOpacity={0.5}
                />
                {/* Dashed connector to main axis */}
                <line
                  x1={AX + 3} y1={ry(maxR) + 18}
                  x2={x - 8} y2={ry(maxR) + 18}
                  stroke={thread.color}
                  strokeDasharray="3 2" strokeWidth={1}
                  strokeOpacity={isHov ? 0.6 : 0.15}
                />
                {/* Nodes */}
                {thread.events.map(ev => {
                  const y = ry(erm[ev.id] ?? 0)
                  return (
                    <g key={ev.id}>
                      {isHov && (
                        <circle cx={x} cy={y} r={10} fill={thread.color} fillOpacity={0.08} />
                      )}
                      <circle
                        cx={x} cy={y}
                        r={isHov ? 6.5 : NR}
                        fill={isHov ? thread.color : 'var(--background, #0f172a)'}
                        stroke={thread.color} strokeWidth={1.5}
                        style={{ transition: 'r 0.1s, fill 0.1s' }}
                      />
                    </g>
                  )
                })}
              </g>
            )
          })}
        </svg>

        {/* Hover zones (HTML for reliable pointer events) */}
        {threads.map((thread, ti) => {
          const x = tx(ti)
          const evRows = thread.events.map(ev => erm[ev.id])
          const minR = Math.min(...evRows)
          const maxR = Math.max(...evRows)
          return (
            <div
              key={thread.id}
              className="absolute cursor-pointer"
              style={{
                left: x - (TW + TG) / 2,
                top: ry(minR) - 20,
                width: TW + TG,
                height: ry(maxR) - ry(minR) + 40,
                zIndex: 10,
              }}
              onMouseEnter={() => enterHover(thread.id)}
              onMouseLeave={leaveHover}
            />
          )
        })}

        {/* Bubble cards (shown on hover) */}
        {hoveredThreadId && (() => {
          const ti = threads.findIndex(t => t.id === hoveredThreadId)
          const thread = threads[ti]
          if (!thread) return null
          const x = tx(ti)
          // Track per-row slot index to stagger cards that share the same row
          const rowSlot: Record<number, number> = {}
          return thread.events.map(ev => {
            const rowIdx = erm[ev.id]
            if (rowIdx === undefined) return null
            const slot = rowSlot[rowIdx] ?? 0
            rowSlot[rowIdx] = slot + 1
            return (
              <div
                key={ev.id}
                className="absolute z-20 min-w-36 max-w-56 cursor-default rounded-lg border bg-card p-2 shadow-md"
                style={{
                  top: ry(rowIdx) - 24 + slot * 58,
                  left: x + NR + BG,
                  borderLeftColor: thread.color,
                  borderLeftWidth: 2,
                  animation: 'tlBubbleIn 0.13s ease',
                }}
                onMouseEnter={keepHover}
                onMouseLeave={leaveHover}
                onClick={() => onEventClick(ev)}
              >
                {/* Connector line */}
                <div
                  className="absolute -left-2 top-1/2 h-px w-2 -translate-y-1/2 opacity-50"
                  style={{ background: thread.color }}
                />
                <p className="mb-1 truncate text-sm font-semibold leading-snug">
                  {ev.content || ev.topic || ev.id}
                </p>
                <p className="mb-1.5 font-mono text-[10px] text-muted-foreground">
                  {fmtTime(ev.start)}
                </p>
                <div className="flex flex-wrap items-center gap-1">
                  {(ev.tags ?? []).slice(0, 3).map(tag => (
                    <span
                      key={tag}
                      className="rounded px-1 py-0.5 text-[10px] font-medium"
                      style={{ background: `${thread.color}16`, color: thread.color }}
                    >
                      {tag}
                    </span>
                  ))}
                  <span
                    className="ml-auto rounded px-1 py-0.5 font-mono text-[10px]"
                    style={{
                      color: ev.salience >= 0.85 ? '#f59e0b'
                        : ev.salience >= 0.70 ? '#38bdf8'
                        : undefined,
                    }}
                  >
                    {(ev.salience * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="mt-1.5 flex justify-end gap-1" onClick={e => e.stopPropagation()}>
                  <Button variant="ghost" size="icon-xs" onClick={() => onEdit(ev)}>
                    <Pencil className="size-3" />
                  </Button>
                  <Button variant="destructive" size="icon-xs" onClick={() => onDelete(ev)}>
                    <Trash2 className="size-3" />
                  </Button>
                </div>
              </div>
            )
          })
        })()}

        {/* Canvas spacer */}
        <div style={{ height: svgH }} />
      </div>
    </div>
  )
}
