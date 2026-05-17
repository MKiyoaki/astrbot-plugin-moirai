'use client'

import { useEffect, useState } from 'react'
import { GitMerge, AlertTriangle } from 'lucide-react'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { useApp } from '@/lib/store'
import * as api from '@/lib/api'
import { cn } from '@/lib/utils'

interface Props {
  open: boolean
  src: string                          // bot_persona_name of the persona being merged FROM
  bots: api.BotPersonaItem[]           // candidate targets
  onClose: () => void
  onMerged: (target: string, counts: api.PersonaMergePreview) => void
}

export function MergePersonaDialog({ open, src, bots, onClose, onMerged }: Props) {
  const { i18n, sudo, toast } = useApp()
  const t = i18n.personaSelector

  const [target, setTarget] = useState<string>('')
  const [preview, setPreview] = useState<api.PersonaMergePreview | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  // Reset state on open/close
  useEffect(() => {
    if (open) {
      setTarget('')
      setPreview(null)
      setConfirming(false)
      setSubmitting(false)
    }
  }, [open])

  // Auto-fetch preview when target changes
  useEffect(() => {
    if (!open || !target || target === src) {
      setPreview(null)
      return
    }
    let cancelled = false
    setPreviewLoading(true)
    api.graph.mergePersonasPreview(src, target)
      .then(r => { if (!cancelled) setPreview(r) })
      .catch(() => { if (!cancelled) setPreview(null) })
      .finally(() => { if (!cancelled) setPreviewLoading(false) })
    return () => { cancelled = true }
  }, [open, src, target])

  const candidates = bots.filter(b => b.name && b.name !== src)

  const handleSubmit = async () => {
    if (!sudo) {
      toast(t.mergeSudoRequired, 'destructive')
      return
    }
    if (target === src) {
      toast(t.mergeSelfDenied, 'destructive')
      return
    }
    setSubmitting(true)
    try {
      const r = await api.graph.mergePersonas(src, target)
      toast(t.mergeSuccess)
      onMerged(target, r)
      onClose()
    } catch (e) {
      const msg = (e as api.ApiError)?.body || t.mergeFailed
      toast(`${t.mergeFailed}: ${msg}`, 'destructive')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) onClose() }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <GitMerge className="size-4" />
            {t.mergeTitle}
          </DialogTitle>
          <DialogDescription>
            {t.mergeDesc.replace('{src}', src).replace('{target}', target || '?')}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3 py-2">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs text-muted-foreground">{t.mergeTargetLabel}</label>
            <select
              value={target}
              onChange={e => setTarget(e.target.value)}
              className="border-input bg-transparent rounded-md border px-2.5 py-1.5 text-sm"
            >
              <option value="">{t.mergeTargetPlaceholder}</option>
              {candidates.map(b => (
                <option key={b.name!} value={b.name!}>
                  {b.name} ({b.event_count})
                </option>
              ))}
            </select>
          </div>

          {previewLoading && (
            <p className="text-xs text-muted-foreground flex items-center gap-1.5">
              <Spinner data-icon="inline-start" />
              {t.mergePreviewLoading}
            </p>
          )}

          {preview && !previewLoading && (
            <div className="rounded-lg border bg-muted/30 p-3 text-sm space-y-1.5">
              <StatRow label={t.mergeStatEvents} value={preview.events_moved} />
              <StatRow label={t.mergeStatImpressionsMoved} value={preview.impressions_moved} />
              {preview.impressions_dropped > 0 && (
                <StatRow
                  label={t.mergeStatImpressionsDropped}
                  value={preview.impressions_dropped}
                  destructive
                />
              )}
              <StatRow label={t.mergeStatPersonas} value={preview.personas_moved} />
            </div>
          )}

          {preview && preview.impressions_dropped > 0 && (
            <p className="text-xs text-destructive/80 flex items-start gap-1.5">
              <AlertTriangle className="size-3 mt-0.5 shrink-0" />
              <span className="leading-snug">
                {preview.impressions_dropped} {t.mergeStatImpressionsDropped} — target wins
              </span>
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            {i18n.common.cancel}
          </Button>
          {!confirming ? (
            <Button
              variant="destructive"
              onClick={() => setConfirming(true)}
              disabled={!target || target === src || !preview || previewLoading}
            >
              {t.mergeConfirm}
            </Button>
          ) : (
            <Button
              variant="destructive"
              onClick={handleSubmit}
              disabled={submitting}
              className={cn('animate-pulse')}
            >
              {submitting && <Spinner data-icon="inline-start" />}
              {t.mergeConfirmTwice}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function StatRow({ label, value, destructive }: { label: string; value: number; destructive?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn('font-mono font-medium', destructive && 'text-destructive')}>{value}</span>
    </div>
  )
}
