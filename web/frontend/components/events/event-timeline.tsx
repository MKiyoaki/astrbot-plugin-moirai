'use client'

import { useState, useRef, useEffect } from 'react'
import { Pencil, Trash2, Lock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { TagFilter } from '@/components/shared/tag-filter'
import { type ApiEvent } from '@/lib/api'
import { i18n } from '@/lib/i18n'

// 使用 Tailwind / Shadcn 语义化图表变量，完美适配明暗模式切换
const THREAD_COLORS = [
  'var(--color-chart-1)',
  'var(--color-chart-2)',
  'var(--color-chart-3)',
  'var(--color-chart-4)',
  'var(--color-chart-5)',
]

// 基础时间合并阈值（不涉及视觉渲染，保持全局常量）
const MERGE = 7_200_000

// 定义基准绘图指标（桌面端默认值）
const DEFAULT_METRICS = {
  AX: 48,  // 主轴 X 坐标
  FTX: 78, // 第一个线程的 X 坐标
  TW: 14,  // 线程可点击热区宽度
  TG: 16,  // 线程之间的间距
  NR: 5,   // 节点半径
  RH: 100, // 行高
  TP: 40,  // 顶部内边距
  BG: 14,  // 气泡间距
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
  
  // 响应式指标状态
  const [metrics, setMetrics] = useState(DEFAULT_METRICS)
  
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // 监听容器宽度，动态计算绘制参数（实现真响应式）
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const width = entry.contentRect.width
        
        if (width < 600) {
          // 移动端：紧凑模式
          setMetrics({ AX: 32, FTX: 54, TW: 12, TG: 10, NR: 4, RH: 90, TP: 40, BG: 10 })
        } else if (width > 1200) {
          // 宽屏：舒展模式
          setMetrics({ AX: 60, FTX: 100, TW: 16, TG: 24, NR: 6, RH: 110, TP: 40, BG: 18 })
        } else {
          // 默认桌面端
          setMetrics(DEFAULT_METRICS)
        }
      }
    })

    observer.observe(container)
    return () => observer.disconnect()
  }, [])

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
  
  // 动态坐标计算函数
  const tx = (i: number) => metrics.FTX + i * (metrics.TW + metrics.TG)
  const ry = (i: number) => metrics.TP + i * metrics.RH
  const svgH = metrics.TP + total * metrics.RH + 60

  return (
    // 使用 ref 监听容器宽度
    <div className="flex flex-col h-full" ref={containerRef}>
      <TagFilter tags={tagList} value={activeTags} onChange={handleTagsChange} />

      {allThreads.length > 1 && (
        <div className="border-b px-4 py-2 shrink-0">
          <p className="mb-1.5 text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">
            {i18n.events.threadAxis}
          </p>
          <ToggleGroup 
            type="multiple"
            className="flex flex-wrap gap-1.5 justify-start"
            value={allThreads.filter(th => matchedIds.has(th.id) && !dimmedIds.has(th.id)).map(th => th.id)}
            onValueChange={(values: string[]) => {
              const newDimmed = new Set<string>()
              allThreads.forEach(th => {
                if (matchedIds.has(th.id) && !values.includes(th.id)) {
                  newDimmed.add(th.id)
                }
              })
              setDimmedIds(newDimmed)
            }}
          >
            {allThreads.map(th => {
              const matched = matchedIds.has(th.id)
              const lit = matched && !dimmedIds.has(th.id)
              return (
                <ToggleGroupItem
                  key={th.id}
                  value={th.id}
                  disabled={!matched}
                  className="h-6 inline-flex items-center gap-1.5 rounded border px-2.5 py-0.5 text-[10.5px] transition-all data-[state=on]:bg-transparent"
                  style={matched ? {
                    // 使用 color-mix 优雅实现 CSS 变量的透明度混合
                    borderColor: lit ? `color-mix(in srgb, ${th.color} 40%, transparent)` : 'transparent',
                    background: lit ? `color-mix(in srgb, ${th.color} 15%, transparent)` : undefined,
                    color: lit ? th.color : undefined,
                  } : { opacity: 0.38 }}
                >
                  <span
                    className="inline-block size-1.5 shrink-0 rounded-full"
                    style={{ background: lit ? th.color : undefined }}
                  />
                  {th.label}
                </ToggleGroupItem>
              )
            })}
          </ToggleGroup>
        </div>
      )}

      <ScrollArea className="flex-1">
        <div className="relative w-full" style={{ minHeight: svgH }}>
          {/* Visual SVG layer */}
          <svg
            className="absolute left-0 top-0"
            style={{ width: '100%', height: svgH, pointerEvents: 'none', overflow: 'visible' }}
          >
            {/* Main axis */}
            <line
              x1={metrics.AX} y1={metrics.TP - 10} x2={metrics.AX} y2={svgH - metrics.BG}
              stroke="currentColor" strokeOpacity={0.15} strokeWidth={1.5}
            />
            {/* Row ticks + date labels */}
            {rows.map(row => (
              <g key={row.idx}>
                <line
                  x1={metrics.AX - 3} y1={ry(row.idx)} x2={metrics.AX + 3} y2={ry(row.idx)}
                  stroke="currentColor" strokeOpacity={0.1} strokeWidth={1}
                />
                <text
                  x={metrics.AX - 5} y={ry(row.idx) + 3}
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
                  <line
                    x1={x} y1={ry(minR)} x2={x} y2={ry(maxR)}
                    stroke={thread.color} strokeWidth={1.5} strokeOpacity={0.7}
                  />
                  <line
                    x1={x - 8} y1={ry(maxR) + 18}
                    x2={x + 8} y2={ry(maxR) + 18}
                    stroke={thread.color} strokeWidth={1} strokeOpacity={0.5}
                  />
                  <line
                    x1={metrics.AX + 3} y1={ry(maxR) + 18}
                    x2={x - 8} y2={ry(maxR) + 18}
                    stroke={thread.color}
                    strokeDasharray="3 2" strokeWidth={1}
                    strokeOpacity={isHov ? 0.6 : 0.15}
                  />
                  {thread.events.map(ev => {
                    const y = ry(erm[ev.id] ?? 0)
                    return (
                      <g key={ev.id}>
                        {isHov && (
                          <circle cx={x} cy={y} r={metrics.NR * 2} fill={thread.color} fillOpacity={0.08} />
                        )}
                        <circle
                          cx={x} cy={y}
                          r={isHov ? metrics.NR * 1.3 : metrics.NR}
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

          {/* Hover zones */}
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
                  left: x - (metrics.TW + metrics.TG) / 2,
                  top: ry(minR) - 20,
                  width: metrics.TW + metrics.TG,
                  height: ry(maxR) - ry(minR) + 40,
                  zIndex: 10,
                }}
                onMouseEnter={() => enterHover(thread.id)}
                onMouseLeave={leaveHover}
              />
            )
          })}

          {/* Bubble cards */}
          {hoveredThreadId && (() => {
            const ti = threads.findIndex(t => t.id === hoveredThreadId)
            const thread = threads[ti]
            if (!thread) return null
            const x = tx(ti)
            return thread.events.map(ev => {
              const rowIdx = erm[ev.id]
              if (rowIdx === undefined) return null
              return (
                <div
                  key={ev.id}
                  className="group absolute z-20 min-w-36 max-w-56 cursor-default rounded-lg border bg-card p-2 shadow-md transition-all hover:z-50 hover:shadow-lg"
                  style={{
                    top: ry(rowIdx) - 24,
                    left: x + metrics.NR + metrics.BG,
                    borderLeftColor: thread.color,
                    borderLeftWidth: 2,
                    animation: 'tlBubbleIn 0.13s ease',
                  }}
                  onMouseEnter={keepHover}
                  onMouseLeave={leaveHover}
                  onClick={() => onEventClick(ev)}
                >
                  <div
                    className="absolute -left-2 top-1/2 h-px w-2 -translate-y-1/2 opacity-50"
                    style={{ background: thread.color }}
                  />
                  <p className="mb-1 truncate text-sm font-semibold leading-snug flex items-center gap-1">
                    {ev.content || ev.topic || ev.id}
                    {ev.is_locked && <Lock className="size-3 text-amber-500 shrink-0" />}
                  </p>
                  <p className="mb-1.5 font-mono text-[10px] text-muted-foreground">
                    {fmtTime(ev.start)}
                  </p>
                  <div className="flex flex-wrap items-center gap-1">
                    {(ev.tags ?? []).slice(0, 3).map(tag => (
                      <Badge
                        key={tag}
                        variant="secondary"
                        className="rounded px-1.5 py-0 font-medium text-[10px] hover:bg-opacity-80"
                        style={{ 
                          background: `color-mix(in srgb, ${thread.color} 15%, transparent)`, 
                          color: thread.color 
                        }}
                      >
                        {tag}
                      </Badge>
                    ))}
                    <span
                      className="ml-auto rounded px-1 py-0.5 font-mono text-[10px]"
                      style={{
                        color: ev.salience >= 0.85 ? 'var(--color-chart-2)'
                          : ev.salience >= 0.70 ? 'var(--color-chart-1)'
                          : undefined,
                      }}
                    >
                      {(ev.salience * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="mt-1.5 flex justify-end gap-1" onClick={e => e.stopPropagation()}>
                    <Button variant="ghost" size="icon" onClick={() => onEdit(ev)}>
                      <Pencil className="size-3" />
                    </Button>
                    <Button variant="destructive" size="icon" onClick={() => onDelete(ev)}>
                      <Trash2 className="size-3" />
                    </Button>
                  </div>
                </div>
              )
            })
          })()}
        </div>
      </ScrollArea>
    </div>
  )
}
