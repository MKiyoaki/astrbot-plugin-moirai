'use client'

import { useEffect, useMemo, useState } from 'react'
import { useApp } from '@/lib/store'
import {
  HeroCard,
  FeaturedMemoryCard,
  DensityRibbon,
  UtilityNavCards,
  RecentEventsStrip,
  SoulMonitor,
} from '@/components/landing'
import * as api from '@/lib/api'

export default function HomePage() {
  const { stats, refreshStats } = useApp()
  const [events, setEvents] = useState<api.ApiEvent[]>([])
  const [graph, setGraph] = useState<api.GraphData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    refreshStats()
    Promise.all([
      api.events.list(50),
      api.graph.get().catch(() => null),
    ]).then(([evRes, g]) => {
      setEvents(evRes.items)
      setGraph(g)
      setLoading(false)
    }).catch(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Highest-salience event for the featured memory card
  const featuredEvent = useMemo(() => {
    if (!events.length) return null
    return [...events].sort((a, b) => b.salience - a.salience)[0] ?? null
  }, [events])

  // Only the 3 most recent for the strip
  const recentThree = useMemo(() => {
    return [...events]
      .sort((a, b) => new Date(b.start).getTime() - new Date(a.start).getTime())
      .slice(0, 3)
  }, [events])

  return (
    <div className="flex h-full flex-col overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-500 ease-out fill-mode-both">
      <main className="flex-1 overflow-y-auto p-6 space-y-4">
        {/* Row 1: Editorial Hero + Featured Memory */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="md:col-span-2">
            <HeroCard stats={stats} />
          </div>
          <FeaturedMemoryCard event={featuredEvent} />
        </div>

        {/* Row 2: 7-Day Density Ribbon */}
        <DensityRibbon events={events} />

        {/* Row 3: Utility Nav Cards */}
        <UtilityNavCards stats={stats} graph={graph} />

        {/* Row 4: Recent Events Strip (3-column) */}
        <RecentEventsStrip events={recentThree} loading={loading} />

        {/* Row 5: Soul Monitor (conditional) */}
        <SoulMonitor />
      </main>
    </div>
  )
}
