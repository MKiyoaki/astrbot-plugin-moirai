'use client'

import { useEffect, useState } from 'react'
import { Loader2, CheckCircle2, XCircle, X } from 'lucide-react'
import { useApp } from '@/lib/store'
import { cn } from '@/lib/utils'

/**
 * Bottom-right dock that surfaces long-running manual LLM operations
 * (re-extract / regenerate summary / reanalyze impressions / merge personas).
 * Each task shows an indeterminate bar while running, then flips to a
 * success (auto-dismiss) or error (sticky) state.
 */
export function TaskDock() {
  const { tasks, dismissTask, i18n } = useApp()
  const [now, setNow] = useState(() => Date.now())

  const hasRunning = tasks.some(t => t.status === 'running')
  useEffect(() => {
    if (!hasRunning) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [hasRunning])

  if (!tasks.length) return null

  return (
    <div className="pointer-events-none fixed bottom-6 right-6 z-50 flex w-72 flex-col gap-2">
      {tasks.map(task => {
        const elapsed = Math.max(
          0,
          Math.round(((task.finishedAt ?? now) - task.startedAt) / 1000),
        )
        const statusText =
          task.status === 'running' ? i18n.tasks.running
          : task.status === 'success' ? i18n.tasks.success
          : i18n.tasks.failed

        return (
          <div
            key={task.id}
            className={cn(
              'pointer-events-auto overflow-hidden rounded-lg border bg-popover text-popover-foreground shadow-lg ring-1 animate-in fade-in-0 slide-in-from-bottom-4',
              task.status === 'error' ? 'ring-destructive/20' : 'ring-foreground/10',
            )}
          >
            <div className="flex items-start gap-2.5 px-3 py-2.5">
              <div className="mt-0.5 shrink-0">
                {task.status === 'running' && (
                  <Loader2 className="size-4 animate-spin text-primary" />
                )}
                {task.status === 'success' && (
                  <CheckCircle2 className="size-4 text-emerald-500" />
                )}
                {task.status === 'error' && (
                  <XCircle className="size-4 text-destructive" />
                )}
              </div>

              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium">{task.label}</span>
                  <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
                    {elapsed}s
                  </span>
                </div>
                <span
                  className={cn(
                    'text-[11px]',
                    task.status === 'error' ? 'text-destructive' : 'text-muted-foreground',
                  )}
                >
                  {statusText}
                </span>
                {task.status === 'error' && task.detail && (
                  <p className="mt-1 break-words text-[11px] leading-snug text-destructive/80">
                    {task.detail}
                  </p>
                )}
              </div>

              {task.status !== 'running' && (
                <button
                  onClick={() => dismissTask(task.id)}
                  className="-mr-1 mt-0.5 shrink-0 rounded opacity-50 hover:opacity-100"
                  aria-label="close"
                >
                  <X className="size-3.5" />
                </button>
              )}
            </div>

            {/* Progress bar: indeterminate while running, solid when done */}
            <div className="relative h-1 w-full bg-muted">
              {task.status === 'running' ? (
                <span className="task-bar-indeterminate bg-primary" />
              ) : (
                <span
                  className={cn(
                    'absolute inset-0',
                    task.status === 'success' ? 'bg-emerald-500' : 'bg-destructive',
                  )}
                />
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
