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
    <Card className="relative flex flex-col justify-between p-8 bg-background border-border/60 min-h-[260px] overflow-hidden">
      {/* Silk thread background */}
      <svg className="absolute inset-0 w-full h-full pointer-events-none" aria-hidden preserveAspectRatio="none" viewBox="0 0 700 280">
        <defs>
          <style>{`
            @keyframes hero-silk-flow {
              0%   { stroke-dashoffset: 0; }
              100% { stroke-dashoffset: -700; }
            }
            @keyframes hero-silk-shimmer {
              0%, 100% { opacity: 0.50; }
              50%       { opacity: 0.80; }
            }
            .hero-thread-accent {
              stroke-dasharray: 380 160;
              animation: hero-silk-flow 10s linear infinite, hero-silk-shimmer 5s ease-in-out infinite;
            }
            .hero-thread-accent-2 {
              stroke-dasharray: 260 200;
              animation: hero-silk-flow 14s linear infinite reverse, hero-silk-shimmer 6s ease-in-out infinite 1.5s;
            }
          `}</style>
        </defs>

        {/* Background threads — lower half only */}
        <path d="M-10,180 Q120,172 260,185 Q400,198 560,178 Q640,172 710,184" fill="none" stroke="currentColor" strokeWidth="0.45" opacity="0.12" />
        <path d="M-10,230 Q100,240 240,228 Q380,216 520,236 Q630,244 710,228" fill="none" stroke="currentColor" strokeWidth="0.35" opacity="0.10" />
        <path d="M-10,258 Q130,250 280,263 Q420,276 570,253 Q650,246 710,260" fill="none" stroke="currentColor" strokeWidth="0.30" opacity="0.08" />

        {/* Accent silk threads — sit below text, in lower third */}
        <path
          className="hero-thread-accent"
          d="M-10,210 Q80,198 200,214 Q330,228 460,202 Q560,188 640,216 Q680,228 710,218"
          fill="none"
          stroke="var(--color-primary, oklch(0.53 0.130 295))"
          strokeWidth="0.70"
          strokeLinecap="round"
          opacity="0.7"
        />
        <path
          className="hero-thread-accent-2"
          d="M-10,248 Q90,258 210,244 Q350,228 480,256 Q580,270 710,248"
          fill="none"
          stroke="var(--color-primary, oklch(0.53 0.130 295))"
          strokeWidth="0.50"
          strokeLinecap="round"
          opacity="0.55"
        />

        {/* Knot nodes */}
        <circle cx="200" cy="214" r="1.6" fill="var(--color-primary, oklch(0.53 0.130 295))" opacity="0.22" />
        <circle cx="460" cy="202" r="1.3" fill="var(--color-primary, oklch(0.53 0.130 295))" opacity="0.18" />
        <circle cx="390" cy="263" r="1.2" fill="currentColor" opacity="0.12" />
        <circle cx="560" cy="236" r="1.4" fill="currentColor" opacity="0.10" />
      </svg>

      <div className="relative z-10 space-y-1">
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

      <CardContent className="relative z-10 p-0 mt-6">
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
