'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { 
  Activity, Share2, BookOpen, Search, Database, 
  ArrowRight, Clock, ShieldCheck, Zap, MessageSquare,
  ChevronRight, ExternalLink, Users
} from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card'
import { useApp } from '@/lib/store'
import { PageHeader } from '@/components/layout/page-header'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import * as api from '@/lib/api'
import { cn, parseSummaryTopics } from '@/lib/utils'

export default function HomePage() {
  const { i18n, stats, refreshStats, lang } = useApp()
  const [recentEvents, setRecentEvents] = useState<api.ApiEvent[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    refreshStats()
    api.events.list(5).then(res => {
      setRecentEvents(res.items)
      setLoading(false)
    }).catch(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const QUICK_ACTIONS = useMemo(() => [
    {
      href: '/recall',
      icon: Search,
      title: i18n.nav.recall,
      color: 'text-blue-500',
      bg: 'bg-blue-500/10',
    },
    {
      href: '/graph',
      icon: Share2,
      title: i18n.nav.graph,
      color: 'text-purple-500',
      bg: 'bg-purple-500/10',
    },
    {
      href: '/summary',
      icon: BookOpen,
      title: i18n.nav.summary,
      color: 'text-amber-500',
      bg: 'bg-amber-500/10',
    },
  ], [i18n])

  return (
    <div className="flex h-full flex-col overflow-hidden bg-muted/5">
      <PageHeader 
        title={i18n.app.name} 
        description={i18n.app.description}
        actions={
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="bg-background/50 font-normal py-1 pr-3 flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
              </span>
              {i18n.landing.engineActive}
            </Badge>
          </div>
        }
      />

      <main className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Row 1: Key Stats Bento */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card className="md:col-span-2 relative overflow-hidden group">
            <div className="absolute top-0 right-0 p-8 opacity-[0.03] group-hover:scale-110 transition-transform duration-500 pointer-events-none">
              <Database size={120} />
            </div>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
                {i18n.nav.visualization}{i18n.landing.overview}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-end gap-2">
                <span className="text-4xl font-bold tracking-tight">{stats.events}</span>
                <span className="text-muted-foreground pb-1 text-sm">{i18n.stats.events}</span>
              </div>
              <div className="mt-4 flex gap-4">
                <div className="flex flex-col">
                  <span className="text-lg font-semibold">{stats.personas}</span>
                  <span className="text-[10px] text-muted-foreground uppercase">{i18n.stats.personas}</span>
                </div>
                <Separator orientation="vertical" className="h-8" />
                <div className="flex flex-col">
                  <span className="text-lg font-semibold">{stats.impressions}</span>
                  <span className="text-[10px] text-muted-foreground uppercase">{i18n.stats.impressions}</span>
                </div>
                <Separator orientation="vertical" className="h-8" />
                <div className="flex flex-col">
                  <span className="text-lg font-semibold">{stats.locked_count}</span>
                  <span className="text-[10px] text-muted-foreground uppercase">{i18n.stats.locked}</span>
                </div>
              </div>
            </CardContent>
          </Card>

          {QUICK_ACTIONS.map((action) => (
            <Link key={action.href} href={action.href}>
              <Card className="h-full hover:bg-accent/50 transition-colors cursor-pointer group relative overflow-hidden">
                <CardContent className="p-6 flex flex-col justify-between h-full">
                  <div className={cn("p-2 w-fit rounded-lg mb-4 transition-transform group-hover:scale-110", action.bg, action.color)}>
                    <action.icon size={20} />
                  </div>
                  <div>
                    <h3 className="font-semibold text-lg">{action.title}</h3>
                    <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1 group-hover:text-primary transition-colors">
                      {i18n.landing.enter} <ArrowRight size={12} />
                    </p>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>

        {/* Row 2: Recent Activity & System Health */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-stretch">
          {/* Recent Events */}
          <Card className="lg:col-span-2 flex flex-col">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <div>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Clock size={18} className="text-primary" />
                  {i18n.landing.recentEvents}
                </CardTitle>
                <CardDescription>
                  {i18n.landing.recentEventsDesc}
                </CardDescription>
              </div>
              <Link href="/events">
                <Button variant="ghost" size="sm" className="text-xs gap-1">
                  {i18n.common.all} <ChevronRight size={14} />
                </Button>
              </Link>
            </CardHeader>
            <CardContent className="flex-1 overflow-hidden p-0">
              <ScrollArea className="h-full px-6">
                <div className="space-y-4 pb-6">
                  {loading ? (
                    Array(3).fill(0).map((_, i) => (
                      <div key={i} className="animate-pulse flex gap-4 py-2 border-b border-border/50">
                        <div className="size-10 rounded-full bg-muted shrink-0" />
                        <div className="flex-1 space-y-2">
                          <div className="h-4 bg-muted rounded w-1/3" />
                          <div className="h-3 bg-muted rounded w-full" />
                        </div>
                      </div>
                    ))
                  ) : recentEvents.length === 0 ? (
                    <div className="py-12 text-center text-muted-foreground text-sm">
                      {i18n.common.noData}
                    </div>
                  ) : (
                    recentEvents.map((ev) => (
                      <div key={ev.id} className="group py-3 flex gap-4 border-b border-border/50 last:border-0 items-start">
                        <div className="bg-muted size-9 rounded-full flex items-center justify-center shrink-0 text-muted-foreground group-hover:bg-primary/10 group-hover:text-primary transition-colors">
                          <MessageSquare size={16} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between mb-0.5">
                            <h4 className="font-medium text-sm truncate">{ev.topic || ev.summary}</h4>
                            <span className="text-[10px] text-muted-foreground whitespace-nowrap ml-2">
                              {new Date(ev.start).toLocaleString(lang === 'zh' ? 'zh-CN' : 'en-US', { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' })}
                            </span>
                          </div>
                          {(() => {
                            const topics = parseSummaryTopics(ev.summary)
                            if (!topics || topics.length === 0) {
                              return <p className="text-xs text-muted-foreground line-clamp-1">{ev.summary}</p>
                            }
                            const t = topics[0] // 首页只显示第一条核心议题
                            return (
                              <div className="space-y-1">
                                <p className="text-xs text-muted-foreground line-clamp-1">
                                  {t.what}
                                </p>
                                <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground opacity-80">
                                  <Users size={10} />
                                  <span className="truncate">{t.who}</span>
                                </div>
                              </div>
                            )
                          })()}
                          <div className="flex gap-2 mt-2">
                            {ev.tags.slice(0, 3).map(tag => (
                              <Badge key={tag} variant="secondary" className="text-[9px] px-1.5 py-0 h-4 font-normal">
                                #{tag}
                              </Badge>
                            ))}
                            {ev.salience > 0.7 && (
                              <Badge variant="destructive" className="text-[9px] px-1.5 py-0 h-4 font-normal bg-red-500/10 text-red-500 hover:bg-red-500/20 border-0">
                                High Salience
                              </Badge>
                            )}
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>

          {/* System Health / Performance */}
          <div className="flex flex-col gap-6">
            <Card className="flex-1">
              <CardHeader className="pb-2">
                <CardTitle className="text-lg flex items-center gap-2">
                  <Zap size={18} className="text-amber-500" />
                  {i18n.landing.cognitiveEngine}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-col gap-1">
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-muted-foreground">{i18n.landing.latency} (Avg)</span>
                    <span className="font-medium">{stats.perf?.avg_response_time ?? '0.000'}s</span>
                  </div>
                  <div className="w-full bg-muted rounded-full h-1.5 overflow-hidden">
                    <div 
                      className={cn(
                        "h-full transition-all duration-1000",
                        (stats.perf?.avg_response_time ?? 0) > 2 ? "bg-amber-500" : "bg-green-500"
                      )} 
                      style={{ width: `${Math.min(100, (stats.perf?.avg_response_time ?? 0) * 10)}%` }} 
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 mt-4">
                  <div className="bg-muted/50 p-3 rounded-lg border border-border/50">
                    <div className="text-[10px] text-muted-foreground uppercase mb-1">{i18n.landing.extraction}</div>
                    <div className="text-lg font-bold tabular-nums">{stats.perf?.avg_extraction_time ?? '0.000'}s</div>
                  </div>
                  <div className="bg-muted/50 p-3 rounded-lg border border-border/50">
                    <div className="text-[10px] text-muted-foreground uppercase mb-1">{i18n.landing.recall}</div>
                    <div className="text-lg font-bold tabular-nums">{stats.perf?.avg_recall_time ?? '0.000'}s</div>
                  </div>
                </div>
              </CardContent>
              <CardFooter className="pt-0 pb-4">
                <Link href="/stats" className="w-full">
                  <Button variant="outline" size="sm" className="w-full text-xs gap-2">
                    {i18n.nav.stats} <ExternalLink size={12} />
                  </Button>
                </Link>
              </CardFooter>
            </Card>

            <Card className="bg-primary text-primary-foreground border-0 shadow-lg relative overflow-hidden shrink-0">
              <div className="absolute top-0 right-0 p-4 opacity-10 pointer-events-none">
                <ShieldCheck size={80} />
              </div>
              <CardHeader className="pb-0">
                <CardTitle className="text-sm font-normal opacity-90">{i18n.stats.locked}</CardTitle>
              </CardHeader>
              <CardContent className="pt-2">
                <div className="text-3xl font-bold">{stats.locked_count}</div>
                <p className="text-[10px] opacity-70 mt-1 uppercase tracking-wider">
                  {i18n.landing.coreProtected}
                </p>
                <Link href="/library">
                  <Button variant="secondary" size="sm" className="w-full mt-4 h-8 text-[11px]">
                    {i18n.landing.manageLibrary}
                  </Button>
                </Link>
              </CardContent>
            </Card>
          </div>
        </div>
      </main>
    </div>
  )
}
