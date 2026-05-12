'use client'

import { useEffect, useState, useMemo } from 'react'
import {
  Activity, Users, Share2, Lock,
  TrendingUp, Hash, Zap, BarChart3, Search, Clock,
  FileText, Database, Layers
} from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
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
} from 'recharts'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
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

    // Calculate edge pairs per event
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

        {/* Enhanced Performance Section */}
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-1">
           <Card>
             <CardHeader className="pb-3">
               <div className="flex items-center justify-between">
                 <div className="space-y-1">
                   <CardTitle className="flex items-center gap-2 text-base">
                     <Zap className="h-5 w-5 text-primary" />
                     {i18n.stats.perf}
                   </CardTitle>
                   <CardDescription className="text-xs">
                     {lang === 'zh' ? '系统各阶段执行效率深度洞察' : 'Deep insights into system execution efficiency'}
                   </CardDescription>
                 </div>
               </div>
             </CardHeader>
             <CardContent>
               <Tabs defaultValue="pipeline" className="w-full">
                 <TabsList className="mb-4">
                   <TabsTrigger value="pipeline" className="text-xs">{i18n.stats.corePipeline}</TabsTrigger>
                   <TabsTrigger value="background" className="text-xs">{i18n.stats.backgroundTasks}</TabsTrigger>
                 </TabsList>
                 
                 <TabsContent value="pipeline" className="space-y-4 animate-in fade-in zoom-in-95 duration-200">
                    <div className="grid gap-4 grid-cols-1 md:grid-cols-3">
                      <PerfDetailCard 
                        title={i18n.stats.avgResponse} 
                        info={stats.perf?.response} 
                        icon={Clock} 
                        description={lang === 'zh' ? '总响应时长' : 'Total Response'}
                      />
                      <PerfDetailCard 
                        title={i18n.stats.avgRecall} 
                        info={stats.perf?.recall} 
                        icon={Search} 
                        description={lang === 'zh' ? '记忆检索召回' : 'Memory Recall'}
                        subPhases={[
                          { label: i18n.stats.recallSearch, info: stats.perf?.recall_search },
                          { label: i18n.stats.recallRerank, info: stats.perf?.recall_rerank },
                          { label: i18n.stats.recallExpand, info: stats.perf?.recall_expand },
                          { label: i18n.stats.recallInject, info: stats.perf?.recall_inject },
                        ]}
                      />
                      <PerfDetailCard 
                        title={i18n.stats.avgRetrieval} 
                        info={stats.perf?.retrieval} 
                        icon={Layers} 
                        description={lang === 'zh' ? 'Context 注入准备' : 'Context Preparation'}
                      />
                    </div>
                 </TabsContent>

                 <TabsContent value="background" className="space-y-4 animate-in fade-in zoom-in-95 duration-200">
                    <div className="grid gap-4 grid-cols-1 md:grid-cols-3">
                      <PerfDetailCard 
                        title={i18n.stats.avgPartition} 
                        info={stats.perf?.partition} 
                        icon={Hash} 
                        description={lang === 'zh' ? '对话边界检测' : 'Boundary Detection'}
                      />
                      <PerfDetailCard 
                        title={i18n.stats.avgExtraction} 
                        info={stats.perf?.extraction} 
                        icon={Activity} 
                        description={lang === 'zh' ? '情节结构提取' : 'Episode Extraction'}
                      />
                      <PerfDetailCard 
                        title={i18n.stats.avgDistill} 
                        info={stats.perf?.distill} 
                        icon={TrendingUp} 
                        description={lang === 'zh' ? '长文本精简' : 'Text Distillation'}
                      />
                    </div>
                 </TabsContent>
               </Tabs>
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

function PerfDetailCard({ 
  title, info, icon: Icon, description, subPhases 
}: { 
  title: string, info?: api.PerfPhaseInfo, icon: any, description: string, subPhases?: { label: string, info?: api.PerfPhaseInfo }[]
}) {
  return (
    <div className="flex flex-col p-4 rounded-xl border bg-card/50">
      <div className="flex items-center justify-between mb-3">
        <div className="bg-primary/10 p-2 rounded-lg">
          <Icon className="h-4 w-4 text-primary" />
        </div>
        <Badge variant="outline" className="text-[10px] font-mono px-1.5 py-0 h-5">
          {info?.avg_ms ? `${info.avg_ms}ms` : '0ms'}
        </Badge>
      </div>
      
      <div className="space-y-0.5 mb-3">
        <h4 className="text-xs font-bold">{title}</h4>
        <p className="text-[10px] text-muted-foreground">{description}</p>
      </div>

      <div className="grid grid-cols-2 gap-2 mb-3">
        <div className="bg-muted/30 p-2 rounded-md">
          <p className="text-[9px] text-muted-foreground uppercase mb-0.5">Last</p>
          <p className="text-xs font-mono font-bold">{info?.last_ms ?? 0}ms</p>
        </div>
        <div className="bg-muted/30 p-2 rounded-md">
          <p className="text-[9px] text-muted-foreground uppercase mb-0.5">Hits</p>
          <p className="text-xs font-mono font-bold">{info?.last_hits ?? 0}</p>
        </div>
      </div>

      {subPhases && subPhases.length > 0 && (
        <div className="mt-auto pt-3 border-t border-muted/50 space-y-2">
           <p className="text-[9px] font-bold text-muted-foreground uppercase mb-1">Breakdown</p>
           {subPhases.map((p, i) => p.info && (
             <div key={i} className="flex items-center justify-between">
               <span className="text-[10px] text-muted-foreground">{p.label}</span>
               <div className="flex items-center gap-2">
                 <div className="w-12 h-1 bg-muted rounded-full overflow-hidden">
                   <div 
                    className="h-full bg-primary/60" 
                    style={{ width: `${Math.min(100, (p.info.avg_ms / (info?.avg_ms || 1)) * 100)}%` }} 
                   />
                 </div>
                 <span className="text-[10px] font-mono w-10 text-right">{p.info.avg_ms}ms</span>
               </div>
             </div>
           ))}
        </div>
      )}
    </div>
  )
}

