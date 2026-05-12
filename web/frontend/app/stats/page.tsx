'use client'

import { useEffect, useState, useMemo } from 'react'
import {
  Activity, Users, Share2, Lock,
  TrendingUp, Hash, Zap, BarChart3, Search, Clock,
  FileText, Database, Layers
} from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { PageHeader } from '@/components/layout/page-header'
import { RefreshButton } from '@/components/shared/refresh-button'
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from '@/components/ui/chart'
import {
  Bar,
  BarChart,
  CartesianGrid,
  XAxis,
  YAxis,
  PieChart, 
  Pie, 
  Cell, 
  ResponsiveContainer, 
  Tooltip as RechartsTooltip,
} from 'recharts'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { useApp } from '@/lib/store'
import * as api from '@/lib/api'
import { cn } from '@/lib/utils'

export default function StatsPage() {
  const { i18n, stats, lang, refreshStats } = useApp()
  const [events, setEvents] = useState<api.ApiEvent[]>([])
  const [graph, setGraph] = useState<api.GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)

  const loadData = async () => {
    setIsRefreshing(true)
    refreshStats()
    try {
      const [evs, g] = await Promise.all([
        api.events.list(2000),
        api.graph.get()
      ])
      setEvents(evs.items)
      setGraph(g)
      setLoading(false)
    } finally {
      setTimeout(() => setIsRefreshing(false), 600)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  // ── Data Processing ──────────────────────────────────────────────────────

  const timeData = useMemo(() => {
    if (!events.length) return []
    const counts: Record<string, number> = {}
    
    const sorted = [...events].sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime())
    sorted.forEach(ev => {
      const date = new Date(ev.start).toISOString().split('T')[0]
      counts[date] = (counts[date] || 0) + 1
    })

    return Object.entries(counts).map(([date, count]) => ({
      date,
      count,
    })).slice(-30)
  }, [events])

  const averages = useMemo(() => {
    if (!events.length) return { participants: '0', tags: '0', salience: '0%', edges: '0' }
    const total = events.length
    const sumParticipants = events.reduce((acc, ev) => acc + (ev.participants?.length || 0), 0)
    const sumTags = events.reduce((acc, ev) => acc + (ev.tags?.length || 0), 0)
    const sumSalience = events.reduce((acc, ev) => acc + ev.salience, 0)

    let totalCitations = 0
    if (graph) {
      graph.edges.forEach(edge => {
        totalCitations += (edge.data.evidence_event_ids?.length || 0)
      })
    }

    return {
      participants: (sumParticipants / total).toFixed(1),
      tags: (sumTags / total).toFixed(1),
      salience: ((sumSalience / total) * 100).toFixed(0) + '%',
      edges: (totalCitations / total).toFixed(2),
    }
  }, [events, graph])

  // ── Performance Data Preparation ──────────────────────────────────────────

  const COLORS = [
    'hsl(var(--primary))',
    '#3b82f6', // blue
    '#10b981', // green
    '#f59e0b', // amber
    '#ef4444', // red
    '#8b5cf6', // violet
    '#ec4899', // pink
    '#06b6d4', // cyan
    '#84cc16', // lime
    '#6366f1', // indigo
  ]

  const perfData = useMemo(() => {
    if (!stats.perf) return []
    
    const phases = [
      { id: 'response', label: lang === 'zh' ? '总响应 (Response)' : 'Response' },
      { id: 'recall', label: i18n.stats.avgRecall },
      { id: 'retrieval', label: i18n.stats.avgRetrieval },
      { id: 'partition', label: i18n.stats.avgPartition },
      { id: 'extraction', label: i18n.stats.avgExtraction },
      { id: 'distill', label: i18n.stats.avgDistill },
      { id: 'task_synthesis', label: lang === 'zh' ? '人格合成 (Synthesis)' : 'Synthesis' },
      { id: 'task_summary', label: lang === 'zh' ? '叙事摘要 (Summary)' : 'Summary' },
      { id: 'task_cleanup', label: lang === 'zh' ? '记忆清理 (Cleanup)' : 'Cleanup' },
      { id: 'task_reindex', label: lang === 'zh' ? '重索引 (Reindex)' : 'Reindex' },
    ]

    return phases
      .map(p => ({
        name: p.label,
        value: stats.perf?.[p.id]?.avg_ms ? stats.perf[p.id].avg_ms / 1000 : 0,
        fullInfo: stats.perf?.[p.id]
      }))
      .filter(p => p.value > 0)
  }, [stats.perf, lang, i18n])

  const totalTime = perfData.reduce((acc, p) => acc + p.value, 0)

  const chartConfig = {
    count: {
      label: i18n.stats.events,
      color: "var(--primary)",
    },
  }

  const globalActions = (
    <RefreshButton 
      onClick={loadData} 
      loading={isRefreshing} 
    />
  )

  return (
    <div className="flex h-full flex-col overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-500 ease-out fill-mode-both">
      <PageHeader
        title={i18n.page.stats.title}
        description={i18n.page.stats.description}
        globalActions={globalActions}
      />

      <div className="flex-1 overflow-y-auto p-6 pt-2">
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-6 mb-6">
          <StatCard icon={Users} title={i18n.stats.personas} value={stats.personas} sub={lang === 'zh' ? '网络中的活跃人格' : 'Active personas'} />
          <StatCard icon={Activity} title={i18n.stats.events} value={stats.events} sub={lang === 'zh' ? '总情节记忆数量' : 'Total episodes'} />
          <StatCard icon={FileText} title={i18n.stats.summaries} value={stats.summaries} sub={lang === 'zh' ? `平均 ${stats.avg_summary_chars ?? 0} 字符` : `Avg ${stats.avg_summary_chars ?? 0} chars`} />
          <StatCard icon={Share2} title={i18n.stats.impressions} value={stats.impressions} sub={lang === 'zh' ? '已推断的人际关系' : 'Inferred relations'} />
          <StatCard icon={Clock} title={i18n.stats.avgResponse} value={`${(stats.perf?.response?.avg_ms ? (stats.perf.response.avg_ms / 1000).toFixed(3) : (stats.perf?.avg_response_time ?? '0.000'))}s`} sub={lang === 'zh' ? '处理延迟' : 'Response latency'} />
          <StatCard icon={Lock} title={i18n.stats.locked} value={stats.locked_count} sub={lang === 'zh' ? '受保护记忆' : 'Protected memories'} primary />
        </div>

        {/* Performance Comparison (Donut Chart) */}
        <Card className="mb-6 overflow-hidden">
          <CardHeader className="pb-2 border-b bg-muted/20">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Zap className="h-5 w-5 text-primary" />
                  {i18n.stats.perf}
                </CardTitle>
                <CardDescription className="text-xs">
                  {lang === 'zh' ? '系统各阶段执行耗时占比（秒）' : 'Execution time distribution across system phases (seconds)'}
                </CardDescription>
              </div>
              <Badge variant="secondary" className="font-mono text-[10px]">
                {lang === 'zh' ? '累计平均' : 'Total Avg'}: {totalTime.toFixed(3)}s
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <div className="grid grid-cols-1 lg:grid-cols-5 min-h-[400px]">
              {/* Donut Chart */}
              <div className="lg:col-span-3 p-6 flex items-center justify-center relative min-h-[300px]">
                {perfData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={perfData}
                        cx="50%"
                        cy="50%"
                        innerRadius={80}
                        outerRadius={120}
                        paddingAngle={5}
                        dataKey="value"
                        animationBegin={0}
                        animationDuration={1000}
                      >
                        {perfData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                        ))}
                      </Pie>
                      <RechartsTooltip 
                        content={({ active, payload }) => {
                          if (active && payload && payload.length) {
                            const data = payload[0].payload;
                            return (
                              <div className="bg-background/95 border p-2 rounded-lg shadow-xl text-xs backdrop-blur-sm">
                                <p className="font-bold">{data.name}</p>
                                <p className="text-primary font-mono">{data.value.toFixed(3)}s</p>
                                <p className="text-muted-foreground text-[10px] uppercase mt-1">
                                  {lang === 'zh' ? '占比' : 'Ratio'}: {((data.value / totalTime) * 100).toFixed(1)}%
                                </p>
                              </div>
                            );
                          }
                          return null;
                        }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="text-muted-foreground text-sm flex flex-col items-center gap-2">
                    <Database className="h-8 w-8 opacity-20" />
                    {lang === 'zh' ? '暂无性能数据' : 'No performance data'}
                  </div>
                )}
                {perfData.length > 0 && (
                  <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                    <span className="text-3xl font-bold tabular-nums">{(perfData.reduce((max, p) => p.value > max.value ? p : max, perfData[0])).value.toFixed(2)}s</span>
                    <span className="text-[10px] text-muted-foreground uppercase">{lang === 'zh' ? '峰值耗时' : 'Max Latency'}</span>
                  </div>
                )}
              </div>

              {/* Legend & Details */}
              <div className="lg:col-span-2 border-l bg-muted/5 flex flex-col overflow-hidden">
                <div className="p-4 border-b bg-muted/20 text-[10px] font-bold text-muted-foreground uppercase flex items-center justify-between">
                  <span>{lang === 'zh' ? '环节明细' : 'Phase Details'}</span>
                  <span>{lang === 'zh' ? '平均耗时' : 'Duration'}</span>
                </div>
                <div className="flex-1 overflow-y-auto p-4 space-y-3">
                  {perfData.map((p, index) => (
                    <div key={p.name} className="flex items-center justify-between group">
                      <div className="flex items-center gap-2 overflow-hidden">
                        <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: COLORS[index % COLORS.length] }} />
                        <span className="text-xs font-medium truncate">{p.name}</span>
                      </div>
                      <div className="flex items-center gap-3 shrink-0">
                        <div className="w-16 h-1 bg-muted rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-primary/60" 
                            style={{ width: `${(p.value / totalTime) * 100}%` }} 
                          />
                        </div>
                        <span className="text-xs font-mono font-bold w-12 text-right">{p.value.toFixed(3)}s</span>
                      </div>
                    </div>
                  ))}
                  {perfData.length === 0 && (
                    <div className="h-full flex items-center justify-center text-xs text-muted-foreground opacity-50 italic py-10">
                       {lang === 'zh' ? '运行插件以记录性能' : 'Run plugin to record stats'}
                    </div>
                  )}
                </div>
                <div className="p-4 border-t bg-muted/20">
                   <p className="text-[9px] text-muted-foreground leading-relaxed">
                     {lang === 'zh' 
                       ? '提示：此表反映各模块的平均执行开销。核心路径任务（响应、召回）通常在对话时触发；后台任务（合成、总结）则在闲置或周期性触发。' 
                       : 'Note: Average overhead per module. Core path tasks trigger during chat; background tasks trigger periodically.'}
                   </p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7 mb-6">
          {/* Main Chart */}
          <Card className="col-span-4">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <TrendingUp className="h-5 w-5 text-primary" />
                {i18n.stats.activity30d}
              </CardTitle>
            </CardHeader>
            <CardContent className="px-2 pb-4">
              <ChartContainer config={chartConfig} className="h-[300px] w-full">
                <BarChart data={timeData} margin={{ top: 20, right: 20, left: 10, bottom: 0 }}>
                  <CartesianGrid vertical={false} strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis 
                    dataKey="date" 
                    tickLine={false} 
                    axisLine={false} 
                    tickFormatter={(v) => v.split('-').slice(1).join('/')}
                    minTickGap={32}
                    className="fill-muted-foreground text-[10px]"
                  />
                  <YAxis hide />
                  <ChartTooltip 
                    cursor={false} 
                    content={<ChartTooltipContent hideLabel />} 
                  />
                  <Bar 
                    dataKey="count" 
                    fill="var(--color-count)" 
                    radius={[4, 4, 0, 0]} 
                    barSize={24}
                  />
                </BarChart>
              </ChartContainer>
            </CardContent>
          </Card>

          {/* Average Metrics */}
          <Card className="col-span-3">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <BarChart3 className="h-5 w-5 text-primary" />
                {i18n.stats.avgMetrics}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-5 mt-2">
                <MetricRow icon={Users} label={i18n.stats.avgNodes} value={averages.participants} />
                <MetricRow icon={Hash} label={i18n.stats.avgTags} value={averages.tags} />
                <MetricRow icon={Share2} label={i18n.stats.avgEdges} value={averages.edges} />
                <MetricRow icon={TrendingUp} label={i18n.stats.avgSalience} value={averages.salience} />
                <Separator className="my-2" />
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>{i18n.stats.summaryDays}</span>
                  <span className="font-medium text-foreground">{stats.summary_days ?? 0} Days</span>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}

function StatCard({ icon: Icon, title, value, sub, primary }: { icon: any, title: string, value: string | number, sub: string, primary?: boolean }) {
  return (
    <Card className={cn("relative overflow-hidden", primary && "border-primary/20 bg-primary/[0.02]")}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className={cn("h-4 w-4 text-muted-foreground", primary && "text-primary")} />
      </CardHeader>
      <CardContent>
        <div className={cn("text-2xl font-bold", primary && "text-primary")}>{value}</div>
        <p className="text-[10px] text-muted-foreground mt-1 opacity-80">{sub}</p>
      </CardContent>
    </Card>
  )
}

function MetricRow({ icon: Icon, label, value }: { icon: any, label: string, value: string | number }) {
  return (
    <div className="flex items-center justify-between group">
      <div className="flex items-center gap-3">
        <div className="bg-primary/10 p-2 rounded-md transition-colors group-hover:bg-primary/20">
          <Icon className="h-4 w-4 text-primary" />
        </div>
        <span className="text-sm font-medium">{label}</span>
      </div>
      <span className="text-lg font-bold tabular-nums">{value}</span>
    </div>
  )
}
