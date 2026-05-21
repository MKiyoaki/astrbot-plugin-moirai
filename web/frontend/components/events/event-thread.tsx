'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { Archive, Lock, Pencil, Trash2, Users } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import type { ApiEvent } from '@/lib/api'
import { buildSessions, dayStart } from '@/lib/session-clustering'
import { useApp } from '@/lib/store'
import { cn } from '@/lib/utils'

const ROW_H = 78
const SESSION_GAP = 56
const DAY_GAP = 20
const TOP_PAD = 80
const BOTTOM_PAD = 70
const THREAD_AMP = 28
const THREAD_X = 156
const CARD_X = 208
const CARD_MIN_W = 320
const RIGHT_PAD = 24
const TIME_X = 14

interface EventThreadProps {
  events: ApiEvent[]
  timeGap: number
  highlightIds?: Set<string>
  onEventClick: (ev: ApiEvent) => void
  selectedEventId: string | null
  onSelectionChange: (id: string | null) => void
  onEdit: (ev: ApiEvent) => void
  onDelete: (ev: ApiEvent) => void
  onArchive?: (ev: ApiEvent) => void
  accent: string
}

interface ThreadRow {
  ev: ApiEvent
  y: number
  x: number
  sessionIdx: number
  day: number
}

interface DayMark {
  y: number
  label: string
}

interface SessionMark {
  minY: number
  maxY: number
  count: number
}

function threadX(y: number) {
  return THREAD_X + Math.sin(((y - TOP_PAD) / 240) * Math.PI) * THREAD_AMP
}

function fmtClock(value: string) {
  return new Date(value).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

function fmtDayLong(ts: number) {
  return new Date(ts).toLocaleDateString(undefined, { month: 'short', day: 'numeric', weekday: 'short' })
}

function diamond(cx: number, cy: number, r: number) {
  return `M ${cx} ${cy - r * 1.45} L ${cx + r} ${cy} L ${cx} ${cy + r * 1.45} L ${cx - r} ${cy} Z`
}

function mobiusOrbitPath(cx: number, cy: number) {
  return [
    `M ${cx} ${cy}`,
    `C ${cx + 8} ${cy - 13}, ${cx + 25} ${cy - 13}, ${cx + 25} ${cy}`,
    `C ${cx + 25} ${cy + 13}, ${cx + 8} ${cy + 13}, ${cx} ${cy}`,
    `C ${cx - 8} ${cy - 13}, ${cx - 25} ${cy - 13}, ${cx - 25} ${cy}`,
    `C ${cx - 25} ${cy + 13}, ${cx - 8} ${cy + 13}, ${cx} ${cy}`,
  ].join(' ')
}

function buildThreadPath(height: number) {
  const points: { x: number; y: number }[] = []
  for (let y = TOP_PAD - 28; y <= height - BOTTOM_PAD + 28; y += 18) {
    points.push({ x: threadX(y), y })
  }
  if (points.length < 2) return ''

  let d = `M ${points[0].x.toFixed(2)} ${points[0].y.toFixed(2)}`
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[Math.max(0, i - 1)]
    const p1 = points[i]
    const p2 = points[i + 1]
    const p3 = points[Math.min(points.length - 1, i + 2)]
    const c1x = p1.x + (p2.x - p0.x) / 6
    const c1y = p1.y + (p2.y - p0.y) / 6
    const c2x = p2.x - (p3.x - p1.x) / 6
    const c2y = p2.y - (p3.y - p1.y) / 6
    d += ` C ${c1x.toFixed(2)} ${c1y.toFixed(2)}, ${c2x.toFixed(2)} ${c2y.toFixed(2)}, ${p2.x.toFixed(2)} ${p2.y.toFixed(2)}`
  }
  return d
}

function useContainerWidth() {
  const ref = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const obs = new ResizeObserver(entries => setWidth(entries[0]?.contentRect.width ?? 0))
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  return [ref, width] as const
}

function useThreadLayout(events: ApiEvent[], timeGap: number) {
  return useMemo(() => {
    const sessions = buildSessions(events, timeGap)
    const rows: ThreadRow[] = []
    const dayMarks: DayMark[] = []
    const sessionMarks: SessionMark[] = []
    let y = TOP_PAD
    let lastDay = -1

    sessions.forEach((session, sessionIdx) => {
      if (sessionIdx > 0) y += SESSION_GAP
      const startY = y
      session.events.forEach(ev => {
        const ts = new Date(ev.start).getTime()
        const day = dayStart(ts)
        if (day !== lastDay) {
          if (lastDay !== -1) y += DAY_GAP
          dayMarks.push({ y: y - ROW_H * 0.35, label: fmtDayLong(day) })
          lastDay = day
        }
        const rowY = y
        rows.push({ ev, y: rowY, x: threadX(rowY), sessionIdx, day })
        y += ROW_H
      })
      const endY = y - ROW_H
      if (session.events.length > 1) sessionMarks.push({ minY: startY - 18, maxY: endY + 18, count: session.events.length })
    })

    return {
      rows,
      dayMarks,
      sessionMarks,
      height: Math.max(320, y + BOTTOM_PAD),
    }
  }, [events, timeGap])
}

function SalienceMeter({ value, accent }: { value: number; accent: string }) {
  const active = Math.max(1, Math.ceil((value ?? 0) * 5))
  return (
    <span className="inline-flex items-center gap-0.5" aria-label={`salience ${Math.round((value ?? 0) * 100)}%`}>
      {Array.from({ length: 5 }, (_, index) => (
        <span
          key={index}
          className="size-1.5 rounded-full"
          style={{ background: index < active ? accent : 'color-mix(in srgb, var(--muted-foreground) 24%, transparent)' }}
        />
      ))}
    </span>
  )
}

interface ThreadEventCardProps {
  ev: ApiEvent
  y: number
  cardW: number
  accent: string
  selected: boolean
  highlighted: boolean
  onSelect: () => void
  onEdit: (ev: ApiEvent) => void
  onDelete: (ev: ApiEvent) => void
  onArchive?: (ev: ApiEvent) => void
}

function ThreadEventCard({ ev, y, cardW, accent, selected, highlighted, onSelect, onEdit, onDelete, onArchive }: ThreadEventCardProps) {
  const { i18n } = useApp()

  return (
    <foreignObject x={CARD_X} y={y - 32} width={cardW} height={70}>
      <div
        className={cn(
          'flex h-[64px] cursor-pointer flex-col justify-center gap-1 rounded-md border bg-card/95 px-3 shadow-sm transition-transform hover:translate-x-0.5',
          selected || highlighted ? 'shadow-md' : 'border-border/70'
        )}
        style={{ borderLeft: `3px solid ${accent}` }}
        onClick={event => { event.stopPropagation(); onSelect() }}
      >
        <div className="flex min-w-0 items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-1.5">
            <span className="truncate font-serif text-sm font-semibold leading-tight">
              {ev.topic || ev.content || ev.id}
            </span>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  {ev.is_locked ? <Lock className="size-3 shrink-0 text-muted-foreground cursor-default" /> : <span />}
                </TooltipTrigger>
                <TooltipContent><p>{i18n.events.lockedMemory}</p></TooltipContent>
              </Tooltip>
            </TooltipProvider>
            {ev.status === 'archived' && (
              <Badge variant="outline" className="h-4 shrink-0 rounded px-1 font-mono text-[9px]">{i18n.events.archive}</Badge>
            )}
          </div>
          <SalienceMeter value={ev.salience ?? 0} accent={accent} />
        </div>
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 flex-wrap gap-1 overflow-hidden">
            {(ev.tags ?? []).slice(0, 4).map(tag => (
              <Badge key={tag} variant="secondary" className="h-4 rounded px-1 font-mono text-[9px]">
                #{tag}
              </Badge>
            ))}
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <span className="inline-flex items-center gap-1 font-mono text-[10px] text-muted-foreground">
              <Users className="size-3" />
              {(ev.participants ?? []).length}
            </span>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="ghost" size="icon" className="size-6" onClick={event => { event.stopPropagation(); onEdit(ev) }}>
                    <Pencil className="size-3" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent><p>{i18n.common.edit}</p></TooltipContent>
              </Tooltip>
            </TooltipProvider>
            {onArchive && (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button variant="ghost" size="icon" className="size-6" onClick={event => { event.stopPropagation(); onArchive(ev) }}>
                      <Archive className="size-3" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent><p>{i18n.events.archive}</p></TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="ghost" size="icon" className="size-6 text-destructive" onClick={event => { event.stopPropagation(); onDelete(ev) }}>
                    <Trash2 className="size-3" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent><p>{i18n.common.delete}</p></TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        </div>
      </div>
    </foreignObject>
  )
}

export function EventThread({
  events,
  timeGap,
  highlightIds,
  onEventClick,
  selectedEventId,
  onSelectionChange,
  onEdit,
  onDelete,
  onArchive,
  accent,
}: EventThreadProps) {
  const { i18n } = useApp()
  const [containerRef, containerW] = useContainerWidth()
  const scrollRef = useRef<HTMLDivElement>(null)
  const drawPathRef = useRef<SVGPathElement>(null)
  const [pathLen, setPathLen] = useState(2000)
  const [focusedKnotId, setFocusedKnotId] = useState<string | null>(null)
  const { rows, dayMarks, sessionMarks, height } = useThreadLayout(events, timeGap)

  const svgW = Math.max(CARD_X + CARD_MIN_W + RIGHT_PAD, (containerW || 0) - 4)
  const cardW = Math.max(CARD_MIN_W, svgW - CARD_X - RIGHT_PAD)
  const threadPath = useMemo(() => buildThreadPath(height), [height])
  const rowById = useMemo(() => {
    const map = new Map<string, ThreadRow>()
    rows.forEach(row => map.set(row.ev.id, row))
    return map
  }, [rows])

  useEffect(() => {
    const path = drawPathRef.current
    if (!path) return
    try {
      setPathLen(path.getTotalLength())
    } catch {}
  }, [threadPath])

  useEffect(() => {
    if (!selectedEventId) return
    const row = rowById.get(selectedEventId)
    if (!row) return
    const t = setTimeout(() => {
      scrollRef.current?.scrollTo({ top: row.y - (scrollRef.current.clientHeight / 2), behavior: 'smooth' })
    }, 120)
    return () => clearTimeout(t)
  }, [selectedEventId, rowById])

  const selectEvent = (ev: ApiEvent) => {
    if (selectedEventId === ev.id) {
      onSelectionChange(null)
      return
    }
    onSelectionChange(ev.id)
    onEventClick(ev)
  }

  return (
    <div ref={containerRef} className="flex h-full flex-1 flex-col overflow-hidden">
      <div ref={scrollRef} className="flex-1 overflow-auto" onClick={() => onSelectionChange(null)}>
        <div className="relative" style={{ width: svgW, minHeight: height }}>
          <svg
            className="absolute inset-0"
            width={svgW}
            height={height}
            viewBox={`0 0 ${svgW} ${height}`}
            role="img"
            aria-label={i18n.events.threadAxis}
          >

            <path d={`M 32 20 Q 74 ${height * 0.28} 32 ${height - 20}`} fill="none" stroke={accent} strokeWidth="0.8" strokeOpacity="0.2" strokeDasharray="18 12" className="loom-axis-flow" />
            <path d={`M ${svgW - 38} 20 Q ${svgW - 88} ${height * 0.55} ${svgW - 40} ${height - 20}`} fill="none" stroke={accent} strokeWidth="0.8" strokeOpacity="0.16" strokeDasharray="16 14" className="loom-axis-flow" />

            {dayMarks.map(mark => (
              <g key={`${mark.label}-${mark.y}`}>
                <line x1={TIME_X} y1={mark.y} x2={svgW - RIGHT_PAD} y2={mark.y} stroke="currentColor" strokeOpacity="0.08" strokeDasharray="4 8" />
                <text x={TIME_X} y={mark.y - 6} fontSize="10" style={{ fontFamily: 'var(--font-mono)' }} fill="currentColor" opacity="0.48">
                  {mark.label}
                </text>
              </g>
            ))}

            {sessionMarks.map((mark, index) => (
              <g key={index}>
                <path
                  d={`M ${THREAD_X - 54} ${mark.minY - 8} Q ${THREAD_X - 62} ${mark.minY - 8} ${THREAD_X - 62} ${mark.minY} L ${THREAD_X - 62} ${mark.maxY} Q ${THREAD_X - 62} ${mark.maxY + 8} ${THREAD_X - 54} ${mark.maxY + 8}`}
                  fill="none"
                  stroke={accent}
                  strokeWidth="1"
                  strokeOpacity="0.34"
                />
                <text x={THREAD_X - 82} y={(mark.minY + mark.maxY) / 2} fontSize="10" style={{ fontFamily: 'var(--font-mono)' }} fill="currentColor" opacity="0.46">
                  x {mark.count}
                </text>
              </g>
            ))}

            <text x={THREAD_X - 26} y={32} fontSize="10" style={{ fontFamily: 'var(--font-serif)' }} fill="currentColor" opacity="0.45">
              ΚΛΩΘΩ
            </text>
            <text x={THREAD_X - 34} y={height - 24} fontSize="10" style={{ fontFamily: 'var(--font-serif)' }} fill="currentColor" opacity="0.45">
              ΑΤΡΟΠΟΣ
            </text>

            <path d={threadPath} fill="none" stroke={accent} strokeWidth="2" strokeLinecap="round" strokeOpacity="0.62" />
            <path
              ref={drawPathRef}
              d={threadPath}
              fill="none"
              stroke={accent}
              strokeWidth="1.2"
              strokeLinecap="round"
              strokeDasharray={pathLen}
              strokeDashoffset={pathLen}
              style={{ animation: 'thread-draw 1.2s cubic-bezier(.4,0,.2,1) forwards' }}
            />

            {rows.map(row => {
              const selected = selectedEventId === row.ev.id
              const highlighted = highlightIds?.has(row.ev.id) ?? false
              const focused = focusedKnotId === row.ev.id
              const active = selected || highlighted || focused
              const archived = row.ev.status === 'archived'
              const locked = row.ev.is_locked
              const r = Math.max(4, Math.min(8, 4 + (row.ev.salience ?? 0) * 4)) * (active ? 1.25 : 1)

              return (
                <g
                  key={row.ev.id}
                  role="button"
                  tabIndex={0}
                  aria-label={`${i18n.events.knotPrefix} ${row.ev.topic || row.ev.content || row.ev.id}`}
                  data-focused={focused ? 'true' : undefined}
                  onClick={event => {
                    event.stopPropagation()
                    selectEvent(row.ev)
                  }}
                  onFocus={() => setFocusedKnotId(row.ev.id)}
                  onBlur={() => setFocusedKnotId(current => current === row.ev.id ? null : current)}
                  onKeyDown={event => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      selectEvent(row.ev)
                    }
                  }}
                  className="event-knot cursor-pointer"
                >
                  <text x={TIME_X} y={row.y + 3} fontSize="10" style={{ fontFamily: 'var(--font-mono)' }} fill="currentColor" opacity="0.48">
                    {fmtClock(row.ev.start)}
                  </text>
                  <line x1={row.x + 9} y1={row.y} x2={CARD_X - 10} y2={row.y} stroke={accent} strokeWidth="0.9" strokeOpacity={active ? 0.62 : 0.24} />
                  {archived ? (
                    <path d={diamond(row.x, row.y, r)} fill="var(--background)" stroke={accent} strokeWidth={active ? 2 : 1.2} strokeDasharray="3 2" opacity={active ? 1 : 0.66} />
                  ) : (
                    <>
                      {(row.ev.salience ?? 0) > 0.8 && !active && (
                        <circle cx={row.x} cy={row.y} r={r + 5} fill="none" stroke={accent} strokeWidth="0.9" opacity="0.18" />
                      )}
                      {active && (
                        <g className="knot-mobius-orbit" aria-hidden>
                          <circle r="2.3" fill={accent} opacity="0.95">
                            <animateMotion dur="2.4s" repeatCount="indefinite" path={mobiusOrbitPath(row.x, row.y)} />
                          </circle>
                          <circle r="1.1" fill="var(--background)" opacity="0.85">
                            <animateMotion dur="2.4s" repeatCount="indefinite" path={mobiusOrbitPath(row.x, row.y)} />
                          </circle>
                        </g>
                      )}
                      <circle cx={row.x} cy={row.y} r={r} fill={locked || active ? accent : 'var(--background)'} stroke={accent} strokeWidth={active ? 2.2 : locked ? 1.8 : 1.3} />
                      {locked && <circle cx={row.x} cy={row.y} r={Math.max(1.5, r * 0.32)} fill="var(--background)" />}
                    </>
                  )}
                </g>
              )
            })}

            {rows.map(row => (
              <ThreadEventCard
                key={`card-${row.ev.id}`}
                ev={row.ev}
                y={row.y}
                cardW={cardW}
                accent={accent}
                selected={selectedEventId === row.ev.id}
                highlighted={highlightIds?.has(row.ev.id) ?? false}
                onSelect={() => selectEvent(row.ev)}
                onEdit={onEdit}
                onDelete={onDelete}
                onArchive={onArchive}
              />
            ))}
          </svg>
        </div>
      </div>
    </div>
  )
}
