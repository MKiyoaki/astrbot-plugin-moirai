'use client'

import { useEffect, useState } from 'react'
import { Activity, MessageSquare } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useApp } from '@/lib/store'
import * as api from '@/lib/api'
import { cn } from '@/lib/utils'

export function SoulMonitor() {
  const { i18n, stats } = useApp()
  const [states, setStates] = useState<Record<string, api.SoulState>>({})

  useEffect(() => {
    if (!stats?.soul_enabled) return
    const fetchStates = () => {
      api.soul.getStates().then(res => setStates(res.states)).catch(() => {})
    }
    fetchStates()
    const timer = setInterval(fetchStates, 5000)
    return () => clearInterval(timer)
  }, [stats?.soul_enabled])

  if (!stats?.soul_enabled) return null

  const activeSessions = Object.entries(states)

  return (
    <Card className="border-accent-foreground/10 bg-accent/5">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs uppercase tracking-widest font-mono text-muted-foreground">
            {i18n.landing.soulMonitor}
          </CardTitle>
          <div className="flex items-center gap-1.5">
            <div className="size-1.5 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-[9px] text-muted-foreground uppercase tracking-wider font-mono">Realtime</span>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {activeSessions.length === 0 ? (
          <div className="h-16 flex flex-col items-center justify-center border rounded border-dashed border-border/50">
            <MessageSquare className="size-4 text-muted-foreground/20 mb-1" />
            <p className="text-[10px] text-muted-foreground/50 italic">{i18n.landing.soulNoActive}</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
            {activeSessions.map(([sid, s]) => (
              <div key={sid} className="space-y-2.5 p-3 rounded border bg-background/60 shadow-sm">
                <div className="flex items-center gap-1.5 border-b border-border/40 pb-1.5">
                  <Activity className="size-3 text-muted-foreground/40" />
                  <span className="text-[10px] font-mono truncate" title={sid}>{sid}</span>
                </div>
                <div className="grid grid-cols-2 gap-x-3 gap-y-2">
                  <SoulBar label={i18n.landing.recallDepth} value={s.recall_depth} color="bg-sky-500" />
                  <SoulBar label={i18n.landing.expressionDesire} value={s.expression_desire} color="bg-emerald-500" />
                  <SoulBar label={i18n.landing.impressionDepth} value={s.impression_depth} color="bg-violet-500" />
                  <SoulBar label={i18n.landing.creativity} value={s.creativity} color="bg-rose-500" />
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function SoulBar({ label, value, color }: { label: string; value: number; color: string }) {
  const percentage = ((value + 20) / 40) * 100
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[9px] uppercase tracking-tighter">
        <span className="text-muted-foreground truncate">{label}</span>
        <span className="font-mono font-bold ml-1 shrink-0">{value > 0 ? '+' : ''}{value.toFixed(1)}</span>
      </div>
      <div className="h-1 w-full bg-muted rounded-full overflow-hidden">
        <div
          className={cn('h-full transition-all duration-1000 ease-out', color)}
          style={{ width: `${Math.max(2, Math.min(100, percentage))}%` }}
        />
      </div>
    </div>
  )
}
