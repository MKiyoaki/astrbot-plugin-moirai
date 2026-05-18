'use client'

import { useState } from 'react'
import { Zap, Brain } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import { useApp } from '@/lib/store'

export type ReanalyzeMethod = 'heuristic' | 'llm'

interface Props {
  open: boolean
  onClose: () => void
  onConfirm: (method: ReanalyzeMethod) => void
}

export function ReanalyzeMethodDialog({ open, onClose, onConfirm }: Props) {
  const { i18n } = useApp()
  const t = i18n.graph
  const [selected, setSelected] = useState<ReanalyzeMethod>('heuristic')

  const options: { value: ReanalyzeMethod; label: string; desc: string; Icon: typeof Zap }[] = [
    {
      value: 'heuristic',
      label: t.reanalyzeMethodHeuristic,
      desc: t.reanalyzeMethodHeuristicDesc,
      Icon: Zap,
    },
    {
      value: 'llm',
      label: t.reanalyzeMethodLlm,
      desc: t.reanalyzeMethodLlmDesc,
      Icon: Brain,
    },
  ]

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) onClose() }}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{t.reanalyzeMethodDialogTitle}</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-2 py-2">
          {options.map(({ value, label, desc, Icon }) => (
            <button
              key={value}
              type="button"
              onClick={() => setSelected(value)}
              className={cn(
                'flex items-start gap-3 rounded-lg border p-3 text-left transition-colors',
                selected === value
                  ? 'border-primary bg-primary/5'
                  : 'border-border hover:border-primary/50 hover:bg-muted/50',
              )}
            >
              <Icon className={cn('mt-0.5 size-4 shrink-0', selected === value ? 'text-primary' : 'text-muted-foreground')} />
              <div className="min-w-0">
                <p className={cn('text-sm font-medium', selected === value ? 'text-primary' : '')}>{label}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">{desc}</p>
              </div>
            </button>
          ))}
        </div>

        <DialogFooter className="gap-2">
          <Button variant="ghost" size="sm" onClick={onClose}>{i18n.common.cancel}</Button>
          <Button size="sm" onClick={() => { onConfirm(selected); onClose() }}>{i18n.common.confirm}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
