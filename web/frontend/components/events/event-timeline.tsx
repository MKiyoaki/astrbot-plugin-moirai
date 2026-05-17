'use client'

import React, { useState, useRef, useEffect, useMemo, useCallback } from 'react'
import { Pencil, Trash2, Lock, Archive } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { type ApiEvent } from '@/lib/api'
import { useApp } from '@/lib/store'
import { getTagColor, CHART_COLORS as THREAD_COLORS } from '@/lib/colors'

// ── Layout constants ──────────────────────────────────────────────────────────

const HEADER_H   = 44   // thread label row
const EVENT_H    = 36   // pixels allocated per event row
const SESSION_PX = 20   // extra gap between sessions
const TCW        = 90   // thread column width
const LP         = 52   // left label area width
const NR         = 5    // node radius
const ELPH       = 8    // session capsule horizontal pad
const ELPV       = 10   // session capsule vertical pad
const BG         = 20   // tooltip offset

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtTime(ts: string) {
  return new Date(ts).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

function fmtDay(ts: number) {
  const d = new Date(ts)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function dayStart(ts: number) {
  const d = new Date(ts); d.setHours(0, 0, 0, 0); return d.getTime()
}

// ── Session clustering ────────────────────────────────────────────────────────

interface Session { events: ApiEvent[]; startTs: number; endTs: number }

function buildSessions(events: ApiEvent[], timeGap: number): Session[] {
  const sorted = [...events]
    .filter(ev => ev?.start)
    .sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime())
  const sessions: Session[] = []
  for (const ev of sorted) {
    const ts = new Date(ev.start).getTime()
    const last = sessions[sessions.length - 1]
    if (last && ts - last.endTs <= timeGap) {
      last.events.push(ev); last.endTs = ts
    } else {
      sessions.push({ events: [ev], startTs: ts, endTs: ts })
    }
  }
  return sessions
}

// ── Layout: assign a Y pixel to every event ───────────────────────────────────
// Events are laid out top-to-bottom in chronological order.
// Within a session: EVENT_H per event.
// Between sessions: SESSION_PX extra gap.
// This means spacing is density-based, NOT proportional to elapsed time.

interface RowInfo {
  ev: ApiEvent
  y: number          // center Y of this event row
  sessionIdx: number
  isFirstInSession: boolean
  isLastInSession: boolean
  day: number        // dayStart timestamp
  showDayLabel: boolean
}

function buildLayout(
  allEvents: ApiEvent[],
  timeGap: number,
): { rows: RowInfo[]; totalH: number } {
  const sorted = [...allEvents]
    .filter(ev => ev?.start)
    .sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime())

  if (!sorted.length) return { rows: [], totalH: HEADER_H + 40 }

  // Group into sessions (ignoring thread boundaries for the global Y layout)
  const sessions = buildSessions(sorted, timeGap)

  const rows: RowInfo[] = []
  let y = HEADER_H + SESSION_PX
  let lastDay = -1

  sessions.forEach((sess, si) => {
    if (si > 0) y += SESSION_PX  // extra gap before new session

    sess.events.forEach((ev, ei) => {
      const day = dayStart(new Date(ev.start).getTime())
      const showDayLabel = day !== lastDay
      if (showDayLabel) lastDay = day

      rows.push({
        ev,
        y: y + EVENT_H / 2,
        sessionIdx: si,
        isFirstInSession: ei === 0,
        isLastInSession: ei === sess.events.length - 1,
        day,
        showDayLabel,
      })
      y += EVENT_H
    })
  })

  return { rows, totalH: y + SESSION_PX + 16 }
}

// ── Component ─────────────────────────────────────────────────────────────────

interface Thread { id: string; label: string; color: string }

interface EventTimelineProps {
  events: ApiEvent[]
  timeGap: number
  highlightIds?: Set<string>
  onEventClick: (ev: ApiEvent) => void
  selectedEventId: string | null
  onSelectionChange: (id: string | null) => void
  onEdit: (ev: ApiEvent) => void
  onDelete: (ev: ApiEvent) => void
  onArchive?: (ev: ApiEvent) => void
  externalDimmedIds?: Set<string>
}

export function EventTimeline({
  events, timeGap, highlightIds,
  onEventClick, selectedEventId, onSelectionChange,
  onEdit, onDelete, onArchive, externalDimmedIds,
}: EventTimelineProps) {
  const { i18n } = useApp()

  const [internalDimmedIds, setInternalDimmedIds] = useState<Set<string>>(new Set())
  const [hoveredEvId, setHoveredEvId]         = useState<string | null>(null)
  const [bubbleEvId, setBubbleEvId]           = useState<string | null>(null)
  const [pendingArchiveId, setPendingArchiveId] = useState<string | null>(null)
  const archiveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const hoverTimerRef   = useRef<ReturnType<typeof setTimeout> | null>(null)
  const scrollRef       = useRef<HTMLDivElement>(null)
  const outerRef        = useRef<HTMLDivElement>(null)
  const [outerW, setOuterW] = useState(0)
  const [scrollH, setScrollH] = useState(0)
  const dimmedIds = externalDimmedIds ?? internalDimmedIds

  useEffect(() => {
    const el = outerRef.current; if (!el) return
    const obs = new ResizeObserver(e => setOuterW(e[0]?.contentRect.width ?? 0))
    obs.observe(el); return () => obs.disconnect()
  }, [])

  useEffect(() => {
    const el = scrollRef.current; if (!el) return
    const obs = new ResizeObserver(e => setScrollH(e[0]?.contentRect.height ?? 0))
    obs.observe(el); return () => obs.disconnect()
  }, [])

  const clearHover = useCallback(() => {
    if (hoverTimerRef.current) { clearTimeout(hoverTimerRef.current); hoverTimerRef.current = null }
  }, [])
  const scheduleHoverClear = useCallback((fn: () => void) => {
    clearHover()
    hoverTimerRef.current = setTimeout(() => { fn(); hoverTimerRef.current = null }, 200)
  }, [clearHover])

  // ── Threads (unique groups, stable colors) ────────────────────────────────

  const threads = useMemo<Thread[]>(() => {
    const all: Thread[] = []; const seen = new Set<string>()
    for (const ev of events) {
      if (!ev?.start) continue
      const key = ev.group || '__pvt__'
      if (!seen.has(key)) {
        seen.add(key)
        all.push({
          id: key,
          label: key === '__pvt__' ? i18n.events.privateChat : key,
          color: THREAD_COLORS[all.length % THREAD_COLORS.length],
        })
      }
    }
    return all
  }, [events, i18n.events.privateChat])

  const threadIdx = useMemo(() => {
    const m: Record<string, number> = {}
    threads.forEach((th, i) => { m[th.id] = i })
    return m
  }, [threads])

  // Responsive column width
  const tcw = useMemo(() => {
    if (!outerW || !threads.length) return TCW
    const available = outerW - LP
    return Math.max(56, Math.min(TCW, Math.floor(available / threads.length)))
  }, [outerW, threads.length])

  const thX = useCallback((ti: number) => LP + ti * tcw + tcw / 2, [tcw])

  // ── Layout ────────────────────────────────────────────────────────────────

  const { rows, totalH } = useMemo(
    () => buildLayout(events, timeGap),
    [events, timeGap]
  )

  // Map ev.id → row
  const rowById = useMemo(() => {
    const m: Record<string, RowInfo> = {}
    rows.forEach(r => { m[r.ev.id] = r })
    return m
  }, [rows])

  // Sessions info for capsule rendering per thread
  // For each thread, find consecutive rows in the same session → draw one capsule
  const threadSessionRanges = useMemo(() => {
    const result: Record<string, { minY: number; maxY: number; count: number }[]> = {}
    threads.forEach(th => { result[th.id] = [] })

    // Group rows by (threadId, sessionIdx)
    const groups: Record<string, Record<number, number[]>> = {}
    threads.forEach(th => { groups[th.id] = {} })

    rows.forEach(row => {
      const key = row.ev.group || '__pvt__'
      if (!groups[key]) return
      if (!groups[key][row.sessionIdx]) groups[key][row.sessionIdx] = []
      groups[key][row.sessionIdx].push(row.y)
    })

    threads.forEach(th => {
      Object.values(groups[th.id]).forEach(ys => {
        if (ys.length < 2) return
        result[th.id].push({ minY: Math.min(...ys), maxY: Math.max(...ys), count: ys.length })
      })
    })
    return result
  }, [rows, threads])

  const svgW = LP + threads.length * tcw
  const svgH = Math.max(totalH, scrollH)

  // ── Scroll to selected ────────────────────────────────────────────────────

  useEffect(() => {
    if (!selectedEventId) return
    const t = setTimeout(() => {
      const row = rowById[selectedEventId]; if (!row) return
      scrollRef.current?.scrollTo({ top: row.y - (scrollRef.current.clientHeight / 2), behavior: 'smooth' })
    }, 350)
    return () => clearTimeout(t)
  }, [selectedEventId, rowById])

  // ── Diamond ───────────────────────────────────────────────────────────────

  const diamond = (cx: number, cy: number, r: number) =>
    `M ${cx} ${cy - r * 1.5} L ${cx + r} ${cy} L ${cx} ${cy + r * 1.5} L ${cx - r} ${cy} Z`

  const activeId   = hoveredEvId ?? bubbleEvId
  const activeRow  = activeId ? rowById[activeId] : null
  const activeTi   = activeRow ? (threadIdx[activeRow.ev.group || '__pvt__'] ?? 0) : 0
  const activeThread = activeRow ? threads[activeTi] : null

  return (
    <div ref={outerRef} className="flex flex-col h-full overflow-hidden">
      <div ref={scrollRef} className="flex-1 overflow-y-auto overflow-x-auto relative"
        onClick={() => onSelectionChange(null)}>
        <div className="relative" style={{ width: svgW, minHeight: svgH }}>

          {/* ── SVG layer ── */}
          <svg className="absolute inset-0 pointer-events-none"
            style={{ width: svgW, height: svgH, overflow: 'visible' }}>

            {/* Thread column header backgrounds */}
            {threads.map((th, ti) => {
              const x = thX(ti); const dim = dimmedIds.has(th.id)
              return (
                <rect key={`hbg-${th.id}`}
                  x={x - tcw / 2 + 2} y={2} width={tcw - 4} height={HEADER_H - 4}
                  fill={th.color} fillOpacity={dim ? 0.02 : 0.07} rx={4} />
              )
            })}

            {/* Header separator */}
            <line x1={0} y1={HEADER_H} x2={svgW} y2={HEADER_H}
              stroke="currentColor" strokeOpacity={0.08} strokeWidth={1} />

            {/* Vertical thread lines — extend to full visible height */}
            {threads.map((th, ti) => {
              const x = thX(ti); const dim = dimmedIds.has(th.id)
              return (
                <line key={`vl-${th.id}`}
                  x1={x} y1={HEADER_H} x2={x} y2={svgH}
                  stroke={th.color} strokeWidth={1} strokeOpacity={dim ? 0.05 : 0.2} />
              )
            })}

            {/* Decorative background grid — subtle vertical guides between threads */}
            {threads.length > 0 && Array.from({ length: threads.length - 1 }, (_, i) => {
              const x = LP + (i + 1) * tcw
              return (
                <line key={`grid-${i}`}
                  x1={x} y1={HEADER_H} x2={x} y2={svgH}
                  stroke="currentColor" strokeWidth={0.5} strokeOpacity={0.03} strokeDasharray="2 8" />
              )
            })}

            {/* Session capsules per thread */}
            {threads.map(th => {
              const dim = dimmedIds.has(th.id)
              const ti  = threadIdx[th.id] ?? 0
              const x   = thX(ti)
              return (threadSessionRanges[th.id] || []).map((range, ri) => (
                <rect key={`cap-${th.id}-${ri}`}
                  x={x - ELPH} y={range.minY - ELPV}
                  width={ELPH * 2} height={range.maxY - range.minY + ELPV * 2}
                  rx={ELPH}
                  fill={th.color} fillOpacity={dim ? 0.01 : 0.06}
                  stroke={th.color} strokeOpacity={dim ? 0.05 : 0.3}
                  strokeWidth={1} strokeDasharray="4 3" />
              ))
            })}

            {/* Horizontal tick lines + day labels — one per event row */}
            {rows.map(row => {
              return (
                <g key={`tick-${row.ev.id}`}>
                  <line
                    x1={LP} y1={row.y} x2={svgW} y2={row.y}
                    stroke="currentColor" strokeOpacity={0.07}
                    strokeWidth={1} strokeDasharray="3 5" />
                  {row.showDayLabel && (
                    <text x={LP - 6} y={row.y + 3}
                      textAnchor="end" fontSize={9} fontFamily="monospace"
                      fill="currentColor" fillOpacity={0.45}>
                      {fmtDay(row.day)}
                    </text>
                  )}
                </g>
              )
            })}

            {/* Event nodes */}
            {rows.map(row => {
              const key    = row.ev.group || '__pvt__'
              const ti     = threadIdx[key] ?? 0
              const thread = threads[ti]
              if (!thread) return null
              const x      = thX(ti)
              const dim    = dimmedIds.has(thread.id)
              const isHov  = hoveredEvId === row.ev.id
              const isSel  = selectedEventId === row.ev.id
              const isHigh = highlightIds?.has(row.ev.id) ?? false
              const isArc  = row.ev.status === 'archived'
              const isLock = row.ev.is_locked
              const r      = NR * (isHov || isSel || isHigh ? 1.35 : 1)
              const op     = dim ? 0.08 : 1

              if (isArc) {
                return (
                  <path key={row.ev.id} d={diamond(x, row.y, r)}
                    fill="none" stroke={thread.color}
                    strokeWidth={isSel || isHigh ? 1.8 : 1.2} strokeOpacity={0.5 * op}
                    strokeDasharray="3 2"
                    style={{ transition: 'all 0.2s ease' }} />
                )
              }
              return (
                <g key={row.ev.id} style={{ opacity: op }}>
                  {(row.ev.salience > 0.8 || isHigh) && !isSel && (
                    <circle cx={x} cy={row.y} r={r + 4}
                      fill="none" stroke={thread.color}
                      strokeWidth={0.8} strokeOpacity={0.25} />
                  )}
                  <circle cx={x} cy={row.y} r={Math.max(2, r)}
                    fill={isHov || isSel || isLock ? thread.color : 'var(--background)'}
                    stroke={thread.color}
                    strokeWidth={isSel || isHigh ? 2 : isLock ? 1.8 : 1.3}
                    style={{ transition: 'all 0.2s cubic-bezier(0.34,1.56,0.64,1)' }} />
                  {isLock && (
                    <circle cx={x} cy={row.y} r={Math.max(1, r * 0.3)}
                      fill="white" pointerEvents="none" />
                  )}
                </g>
              )
            })}
          </svg>

          {/* ── Thread header toggle buttons ── */}
          {!externalDimmedIds && threads.map((th, ti) => {
            const x = thX(ti); const dim = dimmedIds.has(th.id)
            return (
              <button key={`btn-${th.id}`}
                className="absolute flex items-center justify-center transition-opacity"
                style={{ left: x - tcw / 2 + 2, top: 2, width: tcw - 4, height: HEADER_H - 4, zIndex: 25, opacity: dim ? 0.35 : 1 }}
                onClick={e => { e.stopPropagation(); setInternalDimmedIds(prev => { const n = new Set(prev); if (n.has(th.id)) n.delete(th.id); else n.add(th.id); return n }) }}
                title={dim ? '显示此会话' : '隐藏此会话'}>
                <span className="font-mono text-[10px] font-semibold truncate px-1" style={{ color: th.color }}>
                  {th.label.length > 10 ? th.label.slice(0, 9) + '…' : th.label}
                </span>
              </button>
            )
          })}

          {/* ── Event hotspots ── */}
          {rows.map(row => {
            const key    = row.ev.group || '__pvt__'
            const ti     = threadIdx[key] ?? 0
            const thread = threads[ti]
            if (!thread) return null
            const x   = thX(ti)
            const dim = dimmedIds.has(thread.id)
            return (
              <div key={`hs-${row.ev.id}`}
                className="absolute cursor-pointer rounded-full"
                style={{ left: x - 12, top: row.y - 12, width: 24, height: 24, zIndex: 20, opacity: dim ? 0.08 : 1 }}
                onMouseEnter={e => { e.stopPropagation(); clearHover(); setHoveredEvId(row.ev.id) }}
                onMouseLeave={() => scheduleHoverClear(() => setHoveredEvId(null))}
                onClick={e => {
                  e.stopPropagation()
                  if (selectedEventId === row.ev.id) onSelectionChange(null)
                  else { onSelectionChange(row.ev.id); onEventClick(row.ev) }
                }} />
            )
          })}

          {/* ── Hover tooltip ── */}
          {activeRow && activeThread && (() => {
            const { ev } = activeRow
            const ex = thX(activeTi)
            const ey = activeRow.y
            const flipLeft = activeTi >= threads.length / 2
            return (
              <div className="absolute z-50 pointer-events-auto"
                style={{ left: flipLeft ? ex - BG : ex + BG, top: ey, animation: 'tlBubbleIn 0.12s ease-out' }}
                onMouseEnter={() => { clearHover(); setBubbleEvId(ev.id) }}
                onMouseLeave={() => {
                  setBubbleEvId(null); setHoveredEvId(null)
                  if (archiveTimerRef.current) clearTimeout(archiveTimerRef.current)
                  setPendingArchiveId(null)
                }}>
                <div
                  className={`${flipLeft ? '-translate-x-full' : ''} -translate-y-1/2 min-w-48 max-w-64 rounded-lg border bg-card p-3 shadow-xl ring-1 ring-black/5`}
                  style={{ borderLeftColor: activeThread.color, borderLeftWidth: 3 }}>
                  <p className="mb-1 text-sm font-semibold leading-snug flex items-center gap-1.5">
                    {ev.content || ev.topic || ev.id}
                    {ev.is_locked && <Lock className="size-3 text-amber-500 shrink-0" />}
                  </p>
                  <p className="mb-2 font-mono text-[10px] text-muted-foreground">{fmtTime(ev.start)}</p>
                  <div className="flex flex-wrap gap-1.5">
                    {(ev.tags ?? []).slice(0, 4).map(tag => {
                      const c = getTagColor(tag)
                      return (
                        <Badge key={tag} variant="secondary" className="rounded px-1.5 py-0 text-[10px]"
                          style={{ background: `color-mix(in srgb,${c} 12%,transparent)`, color: c }}>
                          #{tag}
                        </Badge>
                      )
                    })}
                  </div>
                  <div className="mt-2 pt-2 border-t flex items-center justify-between">
                    <span className="font-mono text-[10px] text-muted-foreground">
                      {(ev.salience * 100).toFixed(0)}% salience
                    </span>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="icon" className="h-6 w-6"
                        onClick={e => { e.stopPropagation(); onEdit(ev) }}>
                        <Pencil className="size-3" />
                      </Button>
                      {onArchive && (
                        <Button variant="ghost" size="icon"
                          className={`h-6 w-6 ${pendingArchiveId === ev.id ? 'bg-amber-500 text-white' : ''}`}
                          title={pendingArchiveId === ev.id ? i18n.common.confirm : i18n.events.archive}
                          onClick={e => {
                            e.stopPropagation()
                            if (pendingArchiveId !== ev.id) {
                              setPendingArchiveId(ev.id)
                              if (archiveTimerRef.current) clearTimeout(archiveTimerRef.current)
                              archiveTimerRef.current = setTimeout(() => setPendingArchiveId(null), 3000)
                            } else {
                              if (archiveTimerRef.current) clearTimeout(archiveTimerRef.current)
                              setPendingArchiveId(null); onArchive(ev)
                            }
                          }}>
                          <Archive className="size-3" />
                        </Button>
                      )}
                      <Button variant="ghost" size="icon" className="h-6 w-6 text-destructive"
                        onClick={e => { e.stopPropagation(); onDelete(ev) }}>
                        <Trash2 className="size-3" />
                      </Button>
                    </div>
                  </div>
                </div>
              </div>
            )
          })()}
        </div>
      </div>
    </div>
  )
}
