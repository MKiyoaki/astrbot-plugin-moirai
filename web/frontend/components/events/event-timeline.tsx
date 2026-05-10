'use client'

import React, { useState, useRef, useEffect, useMemo } from 'react'
import { Pencil, Trash2, Lock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { type ApiEvent } from '@/lib/api'
import { useApp } from '@/lib/store'

// 使用 Tailwind / Shadcn 语义化图表变量，完美适配明暗模式切换
const THREAD_COLORS = [
  'var(--color-chart-1)',
  'var(--color-chart-2)',
  'var(--color-chart-3)',
  'var(--color-chart-4)',
  'var(--color-chart-5)',
]

// 基础绘图指标
const DEFAULT_METRICS = {
  AX: 64,  // 主轴 X 坐标
  FTX: 100, // 第一个线程的 X 坐标
  TW: 18,  // 线程可点击热区宽度
  TG: 22,  // 线程之间的间距
  NR: 7,   // 节点半径
  RH: 100, // 行高 (缩小时会动态调整)
  TP: 60,  // 顶部内边距
  BG: 20,  // 气泡间距
}

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

/**
 * 根据 timeGap 聚合行。如果两个事件的时间差小于 timeGap，则可能放在同一行（或紧邻）。
 * 实际上 timeGap 在这里作为最小视觉间距的参考。
 */
function buildRowMap(threads: Thread[], timeGap: number) {
  const evts = threads
    .flatMap(t => t.events.map(ev => ({ ...ev, tsMs: new Date(ev.start).getTime() })))
    .sort((a, b) => a.tsMs - b.tsMs)

  const rows: RowInfo[] = []
  const erm: Record<string, number> = {}

  for (const ev of evts) {
    const last = rows[rows.length - 1]
    // 使用传入的 timeGap 作为行聚合阈值
    if (last && ev.tsMs - last.tsMs <= timeGap / 2) {
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
  timeGap: number
  highlightIds?: Set<string>
  onEventClick: (ev: ApiEvent) => void
  selectedEventId: string | null
  onSelectionChange: (id: string | null) => void
  onEdit: (ev: ApiEvent) => void
  onDelete: (ev: ApiEvent) => void
}

export function EventTimeline({
  events,
  timeGap,
  onEventClick,
  selectedEventId,
  onSelectionChange,
  onEdit,
  onDelete,
}: EventTimelineProps) {
  const { i18n } = useApp()
  const [dimmedIds, setDimmedIds] = useState<Set<string>>(new Set())
  const [hoveredEventId, setHoveredEventId] = useState<string | null>(null)
  const [hoveredStack, setHoveredStack] = useState<{ row: number; tid: string } | null>(null)
  const [metrics, setMetrics] = useState(DEFAULT_METRICS)
  
  const containerRef = useRef<HTMLDivElement>(null)
  const scrollAreaRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const width = entry.contentRect.width
        if (width < 800) {
          setMetrics({ AX: 40, FTX: 70, TW: 14, TG: 12, NR: 5, RH: 80, TP: 40, BG: 16 })
        } else if (width > 1600) {
          setMetrics({ AX: 80, FTX: 130, TW: 22, TG: 32, NR: 9, RH: 120, TP: 80, BG: 24 })
        } else {
          setMetrics(DEFAULT_METRICS)
        }
      }
    })

    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  const visible = useMemo(() => {
    return [...events].sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime())
  }, [events])

  const threads = useMemo(() => {
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
    return allThreads
  }, [visible])

  const { erm, total, rows } = useMemo(() => buildRowMap(threads, timeGap), [threads, timeGap])
  
  const threadRowGroups = useMemo(() => {
    const groups: Record<string, Record<number, ApiEvent[]>> = {}
    threads.forEach(thread => {
      groups[thread.id] = {}
      thread.events.forEach(ev => {
        const rowIdx = erm[ev.id]
        if (rowIdx === undefined) return
        if (!groups[thread.id][rowIdx]) groups[thread.id][rowIdx] = []
        groups[thread.id][rowIdx].push(ev)
      })
    })
    return groups
  }, [threads, erm])

  const tx = (ti: number) => metrics.FTX + ti * (metrics.TW + metrics.TG)
  const ry = (idx: number) => metrics.TP + idx * metrics.RH

  useEffect(() => {
    if (selectedEventId && containerRef.current) {
      const timer = setTimeout(() => {
        const rowIdx = erm[selectedEventId]
        if (rowIdx !== undefined) {
          const y = ry(rowIdx)
          const viewport = containerRef.current?.querySelector('[data-radix-scroll-area-viewport]')
          if (viewport) {
            const viewportHeight = (viewport as HTMLElement).clientHeight
            if (viewportHeight > 0) {
              const targetScroll = y - viewportHeight / 2
              viewport.scrollTo({ top: targetScroll, behavior: 'smooth' })
            }
          }
        }
      }, 350) 
      return () => clearTimeout(timer)
    }
  }, [selectedEventId, erm, ry])

  const svgH = Math.max(400, metrics.TP + total * metrics.RH + 60)

  const renderInheritanceLines = () => {
    const lines: React.ReactNode[] = []
    visible.forEach(ev => {
      if (!ev.inherit_from?.length) return
      const targetRow = erm[ev.id]
      if (targetRow === undefined) return
      
      const threadIdx = threads.findIndex(t => (t.id === (ev.group || '__pvt__')))
      if (threadIdx === -1) return
      const targetX = tx(threadIdx)
      const targetY = ry(targetRow)

      ev.inherit_from.forEach(parentEmailId => {
        const parentEv = visible.find(e => e.id === parentEmailId)
        const parentRow = erm[parentEmailId]
        
        if (parentEv && parentRow !== undefined) {
          const parentThreadIdx = threads.findIndex(t => t.id === (parentEv.group || '__pvt__'))
          if (parentThreadIdx === -1) return
          const parentX = tx(parentThreadIdx)
          const parentY = ry(parentRow)
          lines.push(
            <path
              key={`${parentEmailId}-${ev.id}`}
              d={`M ${parentX} ${parentY} C ${parentX} ${(parentY + targetY) / 2}, ${targetX} ${(parentY + targetY) / 2}, ${targetX} ${targetY}`}
              stroke="currentColor" strokeWidth={1} strokeOpacity={0.2} fill="none" strokeDasharray="4 2"
            />
          )
        } else {
          lines.push(
            <g key={`broken-${parentEmailId}-${ev.id}`}>
              <defs>
                <linearGradient id={`grad-broken-${ev.id}`} x1="0%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" stopColor="currentColor" stopOpacity="0" />
                  <stop offset="100%" stopColor="currentColor" stopOpacity="0.15" />
                </linearGradient>
              </defs>
              <line
                x1={targetX} y1={targetY} x2={targetX} y2={targetY - 40}
                stroke={`url(#grad-broken-${ev.id})`} strokeWidth={1.5} strokeDasharray="3 3" className="animate-pulse"
              />
            </g>
          )
        }
      })
    })
    return lines
  }

  return (
    <div className="flex flex-col h-full overflow-hidden" ref={containerRef}>
      {threads.length > 1 && (
        <div className="border-b px-4 py-2 shrink-0 bg-muted/5">
          <p className="mb-1.5 text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">
            活跃群组轴
          </p>
          <ToggleGroup 
            type="multiple"
            className="flex flex-wrap gap-1.5 justify-start"
            value={threads.filter(th => !dimmedIds.has(th.id)).map(th => th.id)}
            onValueChange={(values: string[]) => {
              const newDimmed = new Set<string>()
              threads.forEach(th => { if (!values.includes(th.id)) newDimmed.add(th.id) })
              setDimmedIds(newDimmed)
            }}
          >
            {threads.map(th => {
              const lit = !dimmedIds.has(th.id)
              return (
                <ToggleGroupItem
                  key={th.id} value={th.id}
                  className="h-6 inline-flex items-center gap-1.5 rounded border px-2.5 py-0.5 text-[10.5px] transition-all data-[state=on]:bg-transparent"
                  style={{
                    borderColor: lit ? `color-mix(in srgb, ${th.color} 40%, transparent)` : 'transparent',
                    background: lit ? `color-mix(in srgb, ${th.color} 15%, transparent)` : undefined,
                    color: lit ? th.color : undefined,
                  }}
                >
                  <span className="inline-block size-1.5 shrink-0 rounded-full" style={{ background: lit ? th.color : undefined }} />
                  {th.label}
                </ToggleGroupItem>
              )
            })}
          </ToggleGroup>
        </div>
      )}

      <ScrollArea className="flex-1" onClick={() => onSelectionChange(null)}>
        <div className="relative w-full" style={{ minHeight: svgH }}>
          <svg className="absolute left-0 top-0" style={{ width: '100%', height: svgH, pointerEvents: 'none', overflow: 'visible' }}>
            {/* Top extension: dashed line up to the controls area */}
            <line 
              x1={metrics.AX} y1={0} x2={metrics.AX} y2={metrics.TP - 10} 
              stroke="currentColor" strokeOpacity={0.2} strokeWidth={1.5} strokeDasharray="4 4"
            />
            {/* Main axis line */}
            <line 
              x1={metrics.AX} y1={metrics.TP - 10} x2={metrics.AX} y2={svgH - 20} 
              stroke="currentColor" strokeOpacity={0.3} strokeWidth={1.5} 
            />
            {rows.map(row => (
              <g key={row.idx}>
                <line 
                  x1={metrics.AX - 4} y1={ry(row.idx)} x2={metrics.AX + 4} y2={ry(row.idx)} 
                  stroke="currentColor" strokeOpacity={0.4} strokeWidth={1.5} 
                />
                <text 
                  x={metrics.AX - 8} y={ry(row.idx) + 3} textAnchor="end" 
                  fill="currentColor" fillOpacity={0.6} fontSize={12} fontFamily="monospace" fontWeight="bold"
                >
                  {fmtDate(row.tsMs)}
                </text>
              </g>
            ))}
            {renderInheritanceLines()}
            {threads.map((thread, ti) => {
              const x = tx(ti)
              const op = dimmedIds.has(thread.id) ? 0.1 : 1
              const rowIndices = Object.keys(threadRowGroups[thread.id] || {}).map(Number).sort((a, b) => a - b)
              if (rowIndices.length === 0) return null
              const minR = rowIndices[0]
              const maxR = rowIndices[rowIndices.length - 1]
              return (
                <g key={thread.id} style={{ opacity: op }}>
                  <line x1={x} y1={ry(minR)} x2={x} y2={ry(maxR)} stroke={thread.color} strokeWidth={2} strokeOpacity={0.9} />
                  {rowIndices.map(rowIdx => {
                    const group = threadRowGroups[thread.id][rowIdx]
                    const y = ry(rowIdx)
                    const isStackHovered = hoveredStack?.row === rowIdx && hoveredStack?.tid === thread.id
                    if (group.length > 1) {
                      return (
                        <g key={`${thread.id}-${rowIdx}`}>
                          {group.map((ev, i) => {
                            const isHov = hoveredEventId === ev.id
                            const isSel = selectedEventId === ev.id
                            const isArchived = ev.status === 'archived'
                            const spreadFactor = isStackHovered ? 2.8 : 1.4
                            const offset = (i - (group.length - 1) / 2) * (metrics.NR * spreadFactor)
                            const r = isStackHovered ? (isHov || isSel ? metrics.NR * 1.5 : metrics.NR) : metrics.NR
                            const circleOp = isStackHovered ? 1 : 0.8
                            const finalR = ev.is_locked && !isStackHovered ? r * 1.2 : r
                            return (
                              <g key={ev.id}>
                                <circle
                                  cx={x + offset} cy={y} r={Math.max(2, finalR)}
                                  fill={isHov || isSel || ev.is_locked ? thread.color : 'var(--background)'}
                                  stroke={thread.color} strokeWidth={ev.is_locked || isSel ? 2.5 : 1.8} strokeOpacity={circleOp}
                                  strokeDasharray={isArchived ? "2,1" : undefined}
                                  style={{ transition: 'all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)', opacity: isArchived ? 0.5 : 1 }}
                                />
                                {ev.is_locked && (
                                  <circle 
                                    cx={x + offset} cy={y} r={Math.max(1, finalR / 3)} 
                                    fill="white" pointerEvents="none"
                                    style={{ transition: 'all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)' }} 
                                  />
                                )}
                              </g>
                            )
                          })}
                        </g>
                      )
                    } else {
                      const ev = group[0]
                      const isHov = hoveredEventId === ev.id
                      const isSel = selectedEventId === ev.id
                      const isArchived = ev.status === 'archived'
                      const r = isHov || isSel ? metrics.NR * 1.5 : metrics.NR
                      const finalR = ev.is_locked ? r * 1.2 : r
                      return (
                        <g key={ev.id}>
                          <circle
                            cx={x} cy={y} r={finalR}
                            fill={isHov || isSel || ev.is_locked ? thread.color : 'var(--background)'}
                            stroke={thread.color} strokeWidth={ev.is_locked || isSel ? 2.5 : 1.8}
                            strokeDasharray={isArchived ? "2,1" : undefined}
                            style={{ transition: 'all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)', opacity: isArchived ? 0.5 : 1 }}
                          />
                          {ev.is_locked && (
                            <circle 
                              cx={x} cy={y} r={finalR / 3} 
                              fill="white" pointerEvents="none"
                              style={{ transition: 'all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)' }} 
                            />
                          )}
                        </g>
                      )
                    }
                  })}
                </g>
              )
            })}
          </svg>

          {threads.map((thread, ti) => {
            const x = tx(ti)
            const rowIndices = Object.keys(threadRowGroups[thread.id] || {}).map(Number)
            return rowIndices.map(rowIdx => {
              const group = threadRowGroups[thread.id][rowIdx]
              const y = ry(rowIdx)
              const isStackHovered = hoveredStack?.row === rowIdx && hoveredStack?.tid === thread.id
              return (
                <div
                  key={`${thread.id}-${rowIdx}`} className="absolute"
                  style={{ left: x - 20, top: y - 20, width: 40, height: 40, zIndex: 20 }}
                  onMouseEnter={() => setHoveredStack({ row: rowIdx, tid: thread.id })}
                  onMouseLeave={() => { setHoveredStack(null); setHoveredEventId(null) }}
                >
                   <div className="relative size-full">
                     {group.map((ev, i) => {
                       const spreadFactor = isStackHovered ? 2.8 : 1.4
                       const offset = (i - (group.length - 1) / 2) * (metrics.NR * spreadFactor)
                       return (
                         <div
                           key={ev.id} className="absolute cursor-pointer rounded-full"
                           style={{ left: 20 + offset - 12, top: 20 - 12, width: 24, height: 24, zIndex: 30, transition: 'all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)' }}
                           onMouseEnter={(e) => { e.stopPropagation(); setHoveredEventId(ev.id) }}
                           onMouseLeave={() => setHoveredEventId(null)}
                           onClick={(e) => { 
                             e.stopPropagation(); 
                             if (selectedEventId === ev.id) onSelectionChange(null);
                             else { onSelectionChange(ev.id); onEventClick(ev); }
                           }}
                         />
                       )
                     })}
                   </div>
                </div>
              )
            })
          })}

          {hoveredEventId && (() => {
            const ev = visible.find(e => e.id === hoveredEventId)
            if (!ev) return null
            const rowIdx = erm[ev.id]
            if (rowIdx === undefined) return null
            const thread = threads.find(t => t.id === (ev.group || '__pvt__'))
            if (!thread) return null
            const ti = threads.findIndex(t => t.id === thread.id)
            if (ti === -1) return null
            const group = threadRowGroups[thread.id][rowIdx] || []
            const i = group.findIndex(e => e.id === ev.id)
            const isStackHovered = hoveredStack?.row === rowIdx && hoveredStack?.tid === thread.id
            const spreadFactor = isStackHovered ? 2.8 : 1.4
            const offset = (i - (group.length - 1) / 2) * (metrics.NR * spreadFactor)
            const x = tx(ti)
            return (
              <div
                className="absolute z-50 min-w-48 max-w-64 pointer-events-none rounded-lg border bg-card p-3 shadow-xl ring-1 ring-black/5"
                style={{
                  top: ry(rowIdx) - 20, left: x + offset + metrics.NR + metrics.BG,
                  borderLeftColor: thread.color, borderLeftWidth: 3,
                  animation: 'tlBubbleIn 0.15s cubic-bezier(0.16, 1, 0.3, 1)',
                }}
              >
                <p className="mb-1 text-sm font-semibold leading-tight flex items-center gap-1.5">
                  {ev.content || ev.topic || ev.id}
                  {ev.is_locked && <Lock className="size-3 text-amber-500" />}
                </p>
                <p className="mb-2 font-mono text-[10px] text-muted-foreground">{fmtTime(ev.start)}</p>
                <div className="flex flex-wrap items-center gap-1.5">
                  {(ev.tags ?? []).slice(0, 4).map(tag => (
                    <Badge key={tag} variant="secondary" className="rounded px-1.5 py-0 text-[10px] font-medium" style={{ background: `color-mix(in srgb, ${thread.color} 12%, transparent)`, color: thread.color }}>
                      #{tag}
                    </Badge>
                  ))}
                </div>
                <div className="mt-2.5 pt-2 border-t flex items-center justify-between">
                   <div className="flex items-center gap-2">
                     <span className="text-[10px] text-muted-foreground uppercase font-bold tracking-tighter">Salience</span>
                     <span className="font-mono text-xs font-bold" style={{ color: ev.salience > 0.8 ? 'var(--color-chart-2)' : 'inherit' }}>
                       {(ev.salience * 100).toFixed(0)}%
                     </span>
                   </div>
                   <div className="flex gap-1 pointer-events-auto">
                     <Button variant="ghost" size="icon" className="h-6 w-6" onClick={(e) => { e.stopPropagation(); onEdit(ev) }}><Pencil className="size-3" /></Button>
                     <Button variant="ghost" size="icon" className="h-6 w-6 text-destructive hover:text-destructive" onClick={(e) => { e.stopPropagation(); onDelete(ev) }}><Trash2 className="size-3" /></Button>
                   </div>
                </div>
              </div>
            )
          })()}
        </div>
      </ScrollArea>
    </div>
  )
}
