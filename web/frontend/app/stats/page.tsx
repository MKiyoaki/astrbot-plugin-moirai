'use client'

import { useEffect, useState, useMemo } from 'react'
import {
  Activity, Users, Share2, Lock,
  TrendingUp, Hash, Zap, BarChart3, Search, Clock
} from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { PageHeader } from '@/components/layout/page-header'
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
import { useApp } from '@/lib/store'
import * as api from '@/lib/api'
import { cn } from '@/lib/utils'

export default function StatsPage() {
  const { i18n, stats, lang, refreshStats } = useApp()
  const [events, setEvents] = useState<api.ApiEvent[]>([])
  const [graph, setGraph] = useState<api.GraphData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    refreshStats()
    Promise.all([
      api.events.list(2000),
      api.graph.get()
    ]).then(([evs, g]) => {
      setEvents(evs.items)
      setGraph(g)
      setLoading(false)
    })
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
    // An impression has evidence_event_ids. We count how many times an event is cited as evidence.
    let totalCitations = 0
    if (graph) {
      graph.edges.forEach(edge => {
        totalCitations += (edge.data.evidence_event_ids?.length || 0)
      })
    }

    return {
      participants: (sumParticipants / total).toFixed(1),
      tags: (sumParticipants / total).toFixed(1), // Simplified
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

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <PageHeader
        title={i18n.page.stats.title}
        description={i18n.page.stats.description}
      />

      <div className="flex-1 overflow-y-auto p-6 pt-2">
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5 mb-6">
          <Card className="relative overflow-hidden">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{i18n.stats.personas}</CardTitle>
              <Users className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.personas}</div>
              <p className="text-xs text-muted-foreground mt-1 opacity-80">
                {lang === 'zh' ? '网络中的活跃人格' : (lang === 'ja' ? 'ネットワーク内の有効なパーソナ' : 'Active personas in network')}
              </p>
            </CardContent>
          </Card>
          <Card className="relative overflow-hidden">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{i18n.stats.events}</CardTitle>
              <Activity className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.events}</div>
              <p className="text-xs text-muted-foreground mt-1 opacity-80">
                {lang === 'zh' ? '总情节记忆数量' : (lang === 'ja' ? 'エピソード記憶の総数' : 'Total episodic memories')}
              </p>
            </CardContent>
          </Card>
          <Card className="relative overflow-hidden">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{i18n.stats.impressions}</CardTitle>
              <Share2 className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.impressions}</div>
              <p className="text-xs text-muted-foreground mt-1 opacity-80">
                {lang === 'zh' ? '已推断的人际关系' : (lang === 'ja' ? '推論された対人関係' : 'Interpersonal relations')}
              </p>
            </CardContent>
          </Card>
          <Card className="relative overflow-hidden">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{i18n.stats.avgResponse}</CardTitle>
              <Clock className="h-4 w-4 text-amber-500" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.perf?.avg_response_time ?? '0.000'}s</div>
              <p className="text-xs text-muted-foreground mt-1 opacity-80">
                {lang === 'zh' ? '核心任务平均耗时' : (lang === 'ja' ? 'コアタスク平均時間' : 'Avg core task duration')}
              </p>
            </CardContent>
          </Card>
          <Card className="relative overflow-hidden border-primary/20 bg-primary/[0.02]">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{i18n.stats.locked}</CardTitle>
              <Lock className="h-4 w-4 text-primary" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-primary">{stats.locked_count}</div>
              <p className="text-xs text-muted-foreground mt-1 opacity-80">
                {lang === 'zh' ? '受保护不被清理' : (lang === 'ja' ? 'クリーンアップから保護' : 'Protected from cleanup')}
              </p>
            </CardContent>
          </Card>
        </div>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
          {/* Main Chart */}
          <Card className="col-span-4">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <TrendingUp className="h-5 w-5 text-primary" />
                {i18n.stats.activity30d}
              </CardTitle>
              <CardDescription>
                {lang === 'zh' ? '最近活跃月份的事件频率分布' : 'Event frequency over the last active month'}
              </CardDescription>
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
                    className="fill-muted-foreground"
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
              <CardTitle className="flex items-center gap-2">
                <BarChart3 className="h-5 w-5 text-primary" />
                {i18n.stats.avgMetrics}
              </CardTitle>
              <CardDescription>
                {lang === 'zh' ? '记忆结构的定性分析' : (lang === 'ja' ? '記憶構造の定性的分析' : 'Qualitative analysis of memory structure')}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-6 mt-4">
                <MetricItem 
                  icon={Users} 
                  label={i18n.stats.avgNodes} 
                  value={averages.participants} 
                  sub={lang === 'zh' ? '平均每次互动的角色规模' : (lang === 'ja' ? '平均的なやり取りの参加者数' : 'Average size of interaction groups')}
                />
                <MetricItem 
                  icon={Share2} 
                  label={i18n.stats.avgEdges} 
                  value={averages.edges} 
                  sub={lang === 'zh' ? '每事件触发的关系推断数' : (lang === 'ja' ? 'イベントごとの推論された関係数' : 'Inferred relations per event')}
                />
                <MetricItem 
                  icon={TrendingUp} 
                  label={i18n.stats.avgSalience} 
                  value={averages.salience} 
                  sub={lang === 'zh' ? '库中记忆的平均重要程度' : (lang === 'ja' ? 'メモリ内の平均重要度' : 'Mean importance across storage')}
                />
                <MetricItem 
                  icon={Zap} 
                  label={lang === 'zh' ? '处理负荷' : (lang === 'ja' ? '処理負荷' : 'Processing Load')} 
                  value={events.reduce((acc, ev) => acc + (ev.participants?.length || 0) * 2, 0)} 
                  sub={lang === 'zh' ? '已处理的历史消息估算总量' : (lang === 'ja' ? '処理された履歴メッセージの推定総数' : 'Total estimated messages processed')}
                />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Performance Metrics */}
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="h-5 w-5 text-amber-500" />
              {i18n.stats.perf}
            </CardTitle>
            <CardDescription>
              {lang === 'zh' ? '核心引擎任务执行耗时分析' : (lang === 'ja' ? 'コアエンジンのタスク実行時間分析' : 'Execution time analysis for core engine tasks')}
            </CardDescription>
          </CardHeader>
          <CardContent>
             <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-6 mt-2">
                <MetricItem 
                  icon={Clock} 
                  label={i18n.stats.avgResponse} 
                  value={(stats.perf?.avg_response_time ?? 0) + 's'} 
                  sub={lang === 'zh' ? '总平均处理时长' : (lang === 'ja' ? '総平均処理時間' : 'Total avg duration')}
                />
                <MetricItem 
                  icon={Activity} 
                  label={i18n.stats.avgExtraction} 
                  value={(stats.perf?.avg_extraction_time ?? 0) + 's'} 
                  sub={lang === 'zh' ? '从消息中提取情节' : (lang === 'ja' ? 'メッセージからの抽出' : 'Extracting episodes')}
                />
                <MetricItem 
                  icon={Zap} 
                  label={i18n.stats.avgPartition} 
                  value={(stats.perf?.avg_partition_time ?? 0) + 's'} 
                  sub={lang === 'zh' ? '自动对话边界检测' : (lang === 'ja' ? '会話境界の検出' : 'Boundary detection')}
                />
                <MetricItem 
                  icon={TrendingUp} 
                  label={i18n.stats.avgDistill} 
                  value={(stats.perf?.avg_distill_time ?? 0) + 's'} 
                  sub={lang === 'zh' ? '长对话精简提炼' : (lang === 'ja' ? '要約と精緻化' : 'Condensing dialogues')}
                />
                <MetricItem 
                  icon={Share2} 
                  label={i18n.stats.avgRetrieval} 
                  value={(stats.perf?.avg_retrieval_time ?? 0) + 's'} 
                  sub={lang === 'zh' ? 'Prompt 记忆注入' : (lang === 'ja' ? 'プロンプト注入' : 'Context injection')}
                />
                <MetricItem 
                  icon={Search} 
                  label={i18n.stats.avgRecall} 
                  value={(stats.perf?.avg_recall_time ?? 0) + 's'} 
                  sub={lang === 'zh' ? '全文与向量混合搜索' : (lang === 'ja' ? 'ハイブリッド検索' : 'Hybrid search')}
                />
             </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function MetricItem({ icon: Icon, label, value, sub }: { icon: any, label: string, value: string | number, subTextText?: string, sub: string }) {
  return (
    <div className="flex items-center">
      <div className="bg-primary/10 p-2 rounded-lg mr-4">
        <Icon className="h-5 w-5 text-primary" />
      </div>
      <div className="flex-1 space-y-0.5">
        <p className="text-sm font-medium leading-none">{label}</p>
        <p className="text-xs text-muted-foreground">{sub}</p>
      </div>
      <div className="ml-auto font-bold text-xl tabular-nums">{value}</div>
    </div>
  )
}
