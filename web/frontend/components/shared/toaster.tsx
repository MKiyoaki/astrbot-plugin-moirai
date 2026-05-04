'use client'

import { X } from 'lucide-react'
import { useApp } from '@/lib/store'
import { cn } from '@/lib/utils'

export function Toaster() {
  const { toasts, dismissToast } = useApp()

  if (!toasts.length) return null

  return (
    <div className="pointer-events-none fixed bottom-6 left-1/2 z-50 flex -translate-x-1/2 flex-col items-center gap-2">
      {toasts.map(t => (
        <div
          key={t.id}
          className={cn(
            'pointer-events-auto flex items-center gap-3 rounded-lg px-4 py-2.5 text-sm shadow-lg ring-1 animate-in fade-in-0 slide-in-from-bottom-4',
            t.variant === 'destructive'
              ? 'bg-destructive/10 text-destructive ring-destructive/20'
              : 'bg-popover text-popover-foreground ring-foreground/10',
          )}
        >
          <span>{t.message}</span>
          <button
            onClick={() => dismissToast(t.id)}
            className="ml-1 rounded opacity-60 hover:opacity-100"
          >
            <X className="size-3.5" />
          </button>
        </div>
      ))}
    </div>
  )
}
