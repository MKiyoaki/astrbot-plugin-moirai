'use client'

import { Card, CardContent } from '@/components/ui/card'
import { useApp } from '@/lib/store'
import type { PluginStats } from '@/lib/api'

interface HeroCardProps {
  stats: PluginStats
}

export function HeroCard({ stats }: HeroCardProps) {
  const { i18n, lang } = useApp()

  const today = new Date()
  const dateStr = today.toLocaleDateString(
    lang === 'zh' ? 'zh-CN' : lang === 'ja' ? 'ja-JP' : 'en-US',
    { year: 'numeric', month: '2-digit', day: '2-digit' }
  ).replace(/\//g, '.')

  // Use version minor+patch as a loose "issue number"
  const versionParts = (stats.version ?? '0.0.0').split('.')
  const issueNum = String((parseInt(versionParts[1] ?? '0') * 100) + parseInt(versionParts[2] ?? '0')).padStart(3, '0')

  const totalCorpus = (stats.events ?? 0) + (stats.archived_events ?? 0)

  return (
    <Card className="flex flex-col justify-between p-8 bg-background border-border/60 min-h-[260px]">
      <div className="space-y-1">
        <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-mono">
          {i18n.landing.issueLabel} {issueNum} · {dateStr}
        </p>
        <h1 className="text-4xl font-serif font-bold leading-tight tracking-tight text-foreground">
          {i18n.landing.heroTitleLine1}
          <br />
          <span className="text-primary">{i18n.landing.heroTitleLine2}</span>
        </h1>
        <p className="text-muted-foreground text-sm font-serif italic leading-snug max-w-sm">
          {i18n.landing.heroSubtitle
            .replace('{n}', String(stats.events ?? 0))
            .replace('{p}', String(stats.personas ?? 0))
            .replace('{i}', String(stats.impressions ?? 0))}
        </p>
      </div>

      <CardContent className="p-0 mt-6">
        <div className="flex gap-8 items-end">
          <StatItem value={stats.events ?? 0} label={i18n.stats.events} large />
          <StatItem value={stats.personas ?? 0} label={i18n.stats.personas} />
          <StatItem value={stats.impressions ?? 0} label={i18n.stats.impressions} />
          <StatItem value={stats.locked_count ?? 0} label={i18n.stats.locked} />
          {totalCorpus > (stats.events ?? 0) && (
            <StatItem value={totalCorpus} label={i18n.landing.totalCorpus} />
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function StatItem({ value, label, large }: { value: number; label: string; large?: boolean }) {
  return (
    <div className="flex flex-col">
      <span className={large ? 'text-5xl font-bold tracking-tight tabular-nums' : 'text-2xl font-semibold tabular-nums'}>
        {value}
      </span>
      <span className="text-[9px] uppercase tracking-widest text-muted-foreground mt-0.5">
        {label}
      </span>
    </div>
  )
}
