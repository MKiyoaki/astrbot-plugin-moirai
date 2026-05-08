'use client'

import { useEffect, useMemo } from 'react'
import Link from 'next/link'
import { Activity, Share2, BookOpen, Search, Database } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useApp } from '@/lib/store'
import { SidebarTrigger } from '@/components/ui/sidebar'
import { Separator } from '@/components/ui/separator'

export default function HomePage() {
  const { i18n, stats, refreshStats } = useApp()

  useEffect(() => {
    refreshStats()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const PANELS = useMemo(() => [
    {
      href: '/events',
      icon: Activity,
      title: i18n.nav.events,
      desc: i18n.page.events.description,
    },
    {
      href: '/graph',
      icon: Share2,
      title: i18n.nav.graph,
      desc: i18n.page.graph.description,
    },
    {
      href: '/summary',
      icon: BookOpen,
      title: i18n.nav.summary,
      desc: i18n.page.summary.description,
    },
    {
      href: '/recall',
      icon: Search,
      title: i18n.nav.recall,
      desc: i18n.page.recall.description,
    },
    {
      href: '/library',
      icon: Database,
      title: i18n.nav.library,
      desc: i18n.page.library.description,
    },
  ], [i18n])

  const STATS = [
    { label: i18n.stats.personas,    val: stats.personas    },
    { label: i18n.stats.events,      val: stats.events      },
    { label: i18n.stats.locked,      val: stats.locked_count },
    { label: i18n.stats.impressions, val: stats.impressions },
    { label: i18n.stats.groups,      val: stats.groups      },
  ]

  return (
    <div className="flex flex-col">
      <header className="bg-transparent px-6 pt-4 pb-0">
        <div className="flex items-center gap-3">
          <SidebarTrigger className="-ml-1" />
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{i18n.app.name}</h1>
            <p className="text-muted-foreground mt-0.5 text-sm">{i18n.app.description}</p>
          </div>
        </div>
      </header>
      <Separator className="mt-4" />

      <main className="flex-1 p-6">
        {/* Stats */}
        <div className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-5">
          {STATS.map(({ label, val }) => (
            <Card key={label}>
              <CardContent className="pt-3 text-center px-2">
                <div className="text-2xl font-bold sm:text-3xl">{val}</div>
                <div className="text-muted-foreground text-[10px] sm:text-xs uppercase tracking-wider">{label}</div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Navigation cards */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {PANELS.map(({ href, icon: Icon, title, desc }) => (
            <Link key={href} href={href} className="group">
              <Card className="h-full transition-all group-hover:ring-2 group-hover:ring-primary/30">
                <CardHeader>
                  <div className="bg-primary/10 text-primary mb-2 flex size-10 items-center justify-center rounded-lg">
                    <Icon className="size-5" />
                  </div>
                  <CardTitle>{title}</CardTitle>
                  <CardDescription>{desc}</CardDescription>
                </CardHeader>
              </Card>
            </Link>
          ))}
        </div>
      </main>
    </div>
  )
}
