'use client'

import { Card, CardContent } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { useApp } from '@/lib/store'

export function TokenStats() {
  const { i18n, stats, lang } = useApp()
  const llm = stats.llm_stats

  const total = (llm?.total_prompt_tokens ?? 0) + (llm?.total_completion_tokens ?? 0)
  const promptPct = total > 0 ? ((llm?.total_prompt_tokens ?? 0) / total) * 100 : 0
  const callTotal = llm?.total_calls ?? 0
  const okCalls = llm?.successful_calls ?? Math.max(0, callTotal - (llm?.failed_calls ?? 0))
  const failedCalls = llm?.failed_calls ?? 0
  const recentCalls = llm?.recent_calls ?? []

  const tasks = [
    { id: 'extraction', label: i18n.stats.stageExtraction },
    { id: 'synthesis', label: i18n.stats.stageSynthesis },
    { id: 'summary', label: i18n.stats.stageSummary },
  ]

  return (
    <Card className="border-border/50 h-full flex flex-col">
      <div className="px-6 pt-5 pb-3 border-b border-border/40">
        <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground font-mono">
          {i18n.stats.llmTokens}
        </p>
        <p className="text-xs text-muted-foreground mt-0.5">
          {lang === 'zh' ? '认知引擎模型消耗' : 'Cognitive engine token usage'}
        </p>
      </div>
      
      <CardContent className="px-6 py-4 flex-1 flex flex-col justify-between overflow-hidden">
        {(!llm || (total === 0 && callTotal === 0)) ? (
          <div className="flex-1 flex items-center justify-center text-xs text-muted-foreground/40 italic min-h-[120px]">
            {i18n.stats.noData}
          </div>
        ) : (
          <>
            <div className="space-y-3">
              <div className="flex flex-col">
                <div className="flex justify-between items-baseline">
                  <span className="text-3xl font-bold tracking-tighter tabular-nums leading-none">
                    {total.toLocaleString()}
                  </span>
                  <span className="text-[10px] uppercase font-mono text-muted-foreground">Tokens</span>
                </div>

                <div className="grid grid-cols-3 gap-2 mt-3 text-[10px]">
                  <div className="rounded border border-border/50 px-2 py-1.5">
                    <div className="text-muted-foreground uppercase font-mono">Calls</div>
                    <div className="text-sm font-bold tabular-nums">{callTotal}</div>
                  </div>
                  <div className="rounded border border-emerald-500/20 bg-emerald-500/5 px-2 py-1.5">
                    <div className="text-muted-foreground uppercase font-mono">OK</div>
                    <div className="text-sm font-bold tabular-nums text-emerald-600">{okCalls}</div>
                  </div>
                  <div className="rounded border border-red-500/20 bg-red-500/5 px-2 py-1.5">
                    <div className="text-muted-foreground uppercase font-mono">Fail</div>
                    <div className="text-sm font-bold tabular-nums text-red-600">{failedCalls}</div>
                  </div>
                </div>
                
                <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden flex mt-3">
                  <div 
                    className="h-full bg-primary" 
                    style={{ width: `${promptPct}%` }} 
                    title={`${i18n.stats.promptTokens}: ${llm.total_prompt_tokens}`}
                  />
                  <div 
                    className="h-full bg-primary/30" 
                    style={{ width: `${100 - promptPct}%` }} 
                    title={`${i18n.stats.completionTokens}: ${llm.total_completion_tokens}`}
                  />
                </div>
                
                <div className="flex justify-between text-[9px] uppercase tracking-wider text-muted-foreground/80 font-medium mt-2">
                  <div className="flex items-center gap-1.5">
                    <div className="w-1.5 h-1.5 rounded-full bg-primary" />
                    {i18n.stats.promptTokens}
                  </div>
                  <div className="flex items-center gap-1.5 text-right">
                    {i18n.stats.completionTokens}
                    <div className="w-1.5 h-1.5 rounded-full bg-primary/30" />
                  </div>
                </div>
              </div>

              <div className="pt-4 space-y-4">
                {tasks.map(task => {
                  const usage = llm.token_usage_by_task?.[task.id]
                  const taskTotal = (usage?.prompt || 0) + (usage?.completion || 0)
                  if (taskTotal === 0) return null

                  return (
                    <div key={task.id} className="space-y-1.5">
                      <div className="flex justify-between text-[10px] uppercase tracking-wide">
                        <span className="text-muted-foreground">— {task.label}</span>
                        <span className="font-mono font-bold text-accent-foreground">
                          {taskTotal.toLocaleString()}
                        </span>
                      </div>
                      <Progress value={(taskTotal / total) * 100} className="h-1 opacity-80" />
                    </div>
                  )
                })}
              </div>

              {recentCalls.length > 0 && (
                <div className="pt-4 space-y-2">
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-mono">
                    Recent LLM calls
                  </div>
                  <div className="space-y-1 max-h-36 overflow-y-auto pr-1">
                    {recentCalls.slice(0, 8).map(call => (
                      <div key={call.id} className="rounded border border-border/40 px-2 py-1.5 text-[10px]">
                        <div className="flex items-center justify-between gap-2">
                          <span className="truncate font-medium" title={call.task_name}>
                            {call.task_name}
                          </span>
                          <span className={call.success ? 'text-emerald-600 font-mono' : 'text-red-600 font-mono'}>
                            {call.success ? 'OK' : 'FAIL'} · {Math.round(call.duration_ms)}ms
                          </span>
                        </div>
                        <div className="mt-0.5 text-muted-foreground font-mono">
                          in {call.prompt_tokens} / out {call.completion_tokens}
                        </div>
                        {!call.success && call.error && (
                          <div className="mt-1 text-red-600/80 truncate" title={call.error}>
                            {call.error}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
            
            <div className="mt-4 pt-3 border-t border-border/30 flex justify-between items-center text-[10px] text-muted-foreground/60 font-mono italic">
              <span>{callTotal} calls total</span>
              <span>v{stats.version}</span>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
