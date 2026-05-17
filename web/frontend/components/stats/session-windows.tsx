'use client'

import { Card, CardContent } from '@/components/ui/card'
import { useApp } from '@/lib/store'
import type { PluginStats, SessionWindowInfo } from '@/lib/api'

interface SessionWindowsProps {
  stats: PluginStats
}

function SessionRow({ session, lang, i18n }: { session: SessionWindowInfo; lang: string; i18n: any }) {
  const { current_rounds, trigger_rounds, message_count, session_id, group_id } = session
  const pct = Math.min(100, Math.round((current_rounds / trigger_rounds) * 100))

  const scopeLabel = group_id
    ? `${i18n.stats.sessionGroup} ${group_id.slice(0, 12)}${group_id.length > 12 ? '…' : ''}`
    : i18n.stats.sessionPrivate

  // Shorten session_id for display: last segment or truncate
  const shortId = session_id.includes(':')
    ? session_id.split(':').pop()?.slice(0, 16) ?? session_id.slice(0, 16)
    : session_id.slice(0, 16)

  const barColor =
    pct >= 90 ? 'bg-destructive/70' : pct >= 60 ? 'bg-amber-500/70' : 'bg-primary/60'

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="font-mono text-muted-foreground truncate max-w-[55%]" title={session_id}>
          {shortId}
        </span>
        <span className="text-muted-foreground text-[10px]">{scopeLabel}</span>
      </div>
      <div className="flex items-center gap-3">
        <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${barColor}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="text-xs tabular-nums font-medium whitespace-nowrap">
          {current_rounds}
          <span className="text-muted-foreground font-normal">/{trigger_rounds} {i18n.stats.sessionRounds}</span>
        </span>
        <span className="text-[10px] text-muted-foreground tabular-nums whitespace-nowrap">
          {message_count} {i18n.stats.sessionMessages}
        </span>
      </div>
    </div>
  )
}

export function SessionWindows({ stats }: SessionWindowsProps) {
  const { i18n, lang } = useApp()
  const sessions = stats.active_sessions ?? []

  return (
    <Card className="border-border/50">
      <div className="px-6 pt-5 pb-3 border-b border-border/40">
        <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground font-mono">
          {i18n.stats.sessionWindows}
        </p>
        <p className="text-xs text-muted-foreground mt-0.5">{i18n.stats.sessionWindowsDesc}</p>
      </div>
      <CardContent className="py-4 px-6">
        {sessions.length === 0 ? (
          <p className="text-xs text-muted-foreground text-center py-4">
            {i18n.stats.sessionWindowsEmpty}
          </p>
        ) : (
          <div className="space-y-4">
            {sessions.map((s) => (
              <SessionRow key={s.session_id} session={s} lang={lang} i18n={i18n} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
