'use client'

import { useEffect, useState, useMemo } from 'react'
import { useApp } from '@/lib/store'
import { PageHeader } from '@/components/layout/page-header'
import { RefreshButton } from '@/components/shared/refresh-button'
import * as api from '@/lib/api'
import {
  StatMasthead,
  PerfChart,
  ActivityChart,
  AvgMetrics,
  TopTags,
  SalienceDist,
  HourlyPattern,
  WeekOverWeek,
  PersonaRank,
  TokenStats,
} from '@/components/stats'

export default function StatsPage() {
  const { i18n, stats, lang, refreshStats } = useApp()
  const [events, setEvents] = useState<api.ApiEvent[]>([])
  const [graph, setGraph] = useState<api.GraphData | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)

  const loadData = async () => {
    setIsRefreshing(true)
    refreshStats()
    try {
      const [evs, g] = await Promise.all([
        api.events.list(2000),
        api.graph.get().catch(() => null),
      ])
      setEvents(evs.items)
      setGraph(g)
    } finally {
      setTimeout(() => setIsRefreshing(false), 600)
    }
  }

  useEffect(() => { loadData() }, [])

  // ── Data derivations ─────────────────────────────────────────────────────

  const timeData = useMemo(() => {
    if (!events.length) return []
    const counts: Record<string, number> = {}
    for (const ev of events) {
      const date = new Date(ev.start).toISOString().split('T')[0]
      counts[date] = (counts[date] ?? 0) + 1
    }
    return Object.entries(counts)
      .sort((a, b) => a[0].localeCompare(b[0]))
      .slice(-30)
      .map(([date, count]) => ({ date, count }))
  }, [events])

  const averages = useMemo(() => {
    if (!events.length) return { participants: '0', tags: '0', salience: '0%', edges: '0' }
    const total = events.length
    const sumParticipants = events.reduce((acc, ev) => acc + (ev.participants?.length ?? 0), 0)
    const sumTags = events.reduce((acc, ev) => acc + (ev.tags?.length ?? 0), 0)
    const sumSalience = events.reduce((acc, ev) => acc + ev.salience, 0)
    let totalCitations = 0
    for (const edge of graph?.edges ?? []) {
      totalCitations += edge.data.evidence_event_ids?.length ?? 0
    }
    return {
      participants: (sumParticipants / total).toFixed(1),
      tags: (sumTags / total).toFixed(1),
      salience: ((sumSalience / total) * 100).toFixed(0) + '%',
      edges: (totalCitations / total).toFixed(2),
    }
  }, [events, graph])

  const perfData = useMemo(() => {
    if (!stats.perf) return []
    const phases = [
      { id: 'response', label: lang === 'zh' ? '总响应' : 'Response' },
      { id: 'recall', label: i18n.stats.avgRecall },
      { id: 'retrieval', label: i18n.stats.avgRetrieval },
      { id: 'partition', label: i18n.stats.avgPartition },
      { id: 'extraction', label: i18n.stats.avgExtraction },
      { id: 'distill', label: i18n.stats.avgDistill },
      { id: 'task_synthesis', label: lang === 'zh' ? '人格合成' : 'Synthesis' },
      { id: 'task_summary', label: lang === 'zh' ? '叙事摘要' : 'Summary' },
      { id: 'task_cleanup', label: lang === 'zh' ? '记忆清理' : 'Cleanup' },
      { id: 'task_reindex', label: lang === 'zh' ? '重索引' : 'Reindex' },
    ]
    return phases
      .map(p => ({
        name: p.label,
        value: stats.perf?.[p.id]?.avg_ms ? (stats.perf[p.id].avg_ms as number) / 1000 : 0,
      }))
      .filter(p => p.value > 0)
  }, [stats.perf, lang, i18n])

  const totalTime = perfData.reduce((acc, p) => acc + p.value, 0)

  return (
    <div className="flex h-full flex-col overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-500 ease-out fill-mode-both">
      <PageHeader
        variant="loom"
        loomIssue="ΠΑΡΑΤΗΡΗΤΗΡΙΟ"
          loomWindow={i18n.page.stats.loomWindow}
        title={i18n.page.stats.title}
        globalActions={<RefreshButton onClick={loadData} loading={isRefreshing} />}
      />

      <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
        {/* Masthead strip */}
        <StatMasthead stats={stats} totalTime={totalTime} />

        {/* Row: Perf chart (full width) */}
        <PerfChart perfData={perfData} totalTime={totalTime} />

        {/* Row: Activity chart + Tokens (Left) vs Avg metrics (Right) */}
        <div className="grid grid-cols-1 lg:grid-cols-7 gap-4 items-stretch">
          <div className="lg:col-span-4 flex flex-col gap-4">
            <ActivityChart timeData={timeData} />
            <TokenStats />
          </div>
          <div className="lg:col-span-3">
            <AvgMetrics averages={averages} stats={stats} />
          </div>
        </div>

        {/* Row: Week-over-week + Salience dist + Hourly pattern */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <WeekOverWeek events={events} />
          <SalienceDist events={events} />
          <HourlyPattern events={events} />
        </div>

        {/* Row: Top tags + Persona rank */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <TopTags events={events} />
          <PersonaRank events={events} graph={graph} />
        </div>
      </div>
    </div>
  )
}
