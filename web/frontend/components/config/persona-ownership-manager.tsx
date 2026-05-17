'use client'

import { useEffect, useMemo, useState } from 'react'
import { ArrowRight, GitMerge, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { useApp } from '@/lib/store'
import * as api from '@/lib/api'
import { cn } from '@/lib/utils'

type PersonaChoice = string

const CUSTOM = '__custom__'

export function PersonaOwnershipManager() {
  const { i18n, sudo, toast, setCurrentPersona, currentPersonaName } = useApp()
  const t = i18n.config.ownership
  const [bots, setBots] = useState<api.BotPersonaItem[]>([])
  const [source, setSource] = useState<PersonaChoice>(api.LEGACY_PERSONA_TOKEN)
  const [target, setTarget] = useState<PersonaChoice>(CUSTOM)
  const [sourceCustom, setSourceCustom] = useState('')
  const [targetCustom, setTargetCustom] = useState('')
  const [mode, setMode] = useState<api.PersonaMergeMode>('all')
  const [preview, setPreview] = useState<api.PersonaMergePreview | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [confirming, setConfirming] = useState(false)

  const loadBots = async () => {
    try {
      const res = await api.graph.listBots()
      setBots(res.items)
    } catch {
      toast(t.loadFailed, 'destructive')
    }
  }

  useEffect(() => {
    loadBots()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const options = useMemo(() => {
    const seen = new Set<string>()
    const items = [{ value: api.LEGACY_PERSONA_TOKEN, label: t.legacy }]
    seen.add(api.LEGACY_PERSONA_TOKEN)
    for (const bot of bots) {
      const value = bot.name ?? api.LEGACY_PERSONA_TOKEN
      if (seen.has(value)) continue
      seen.add(value)
      items.push({ value, label: `${bot.name} (${bot.event_count})` })
    }
    return items
  }, [bots, t.legacy])

  const resolvedSource = source === CUSTOM ? sourceCustom.trim() : source
  const resolvedTarget = target === CUSTOM ? targetCustom.trim() : target
  const sameTarget = !!resolvedSource && resolvedSource === resolvedTarget
  const canPreview = !!resolvedSource && !!resolvedTarget && !sameTarget
  const canSubmit = sudo && canPreview && !!preview && !previewLoading

  const resetPreview = () => {
    setPreview(null)
    setConfirming(false)
  }

  const handlePreview = async () => {
    if (!canPreview) return
    setPreviewLoading(true)
    setPreview(null)
    setConfirming(false)
    try {
      setPreview(await api.graph.mergePersonasPreview(resolvedSource, resolvedTarget, mode))
    } catch (e) {
      toast(`${t.previewFailed}: ${(e as api.ApiError).body || ''}`, 'destructive')
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleSubmit = async () => {
    if (!sudo) {
      toast(i18n.config.needSudo, 'destructive')
      return
    }
    if (!canSubmit) return
    setSubmitting(true)
    try {
      const result = await api.graph.mergePersonas(resolvedSource, resolvedTarget, mode)
      setPreview(result)
      toast(t.success)
      const sourceName = resolvedSource === api.LEGACY_PERSONA_TOKEN ? null : resolvedSource
      if (currentPersonaName === sourceName) {
        setCurrentPersona(resolvedTarget === api.LEGACY_PERSONA_TOKEN ? null : resolvedTarget, 'single')
      }
      await loadBots()
      setConfirming(false)
    } catch (e) {
      toast(`${t.failed}: ${(e as api.ApiError).body || ''}`, 'destructive')
    } finally {
      setSubmitting(false)
    }
  }

  const movedTotal = preview
    ? preview.events_moved + preview.impressions_moved + preview.personas_moved
    : 0

  return (
    <Card className="mt-4 overflow-hidden border-muted/60 shadow-sm">
      <CardHeader className="border-b border-border/50 pb-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2 text-lg font-bold tracking-tight">
              <GitMerge className="size-4" />
              {t.title}
            </CardTitle>
            <CardDescription className="mt-1 text-xs">{t.description}</CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={loadBots}>
            <RefreshCw className="size-3" />
            {t.refresh}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 px-6 py-4">
        <div className="grid gap-3 md:grid-cols-[1fr_auto_1fr] md:items-end">
          <PersonaPicker
            label={t.source}
            value={source}
            customValue={sourceCustom}
            options={options}
            customLabel={t.custom}
            customPlaceholder={t.customSourcePlaceholder}
            onValueChange={value => { setSource(value); resetPreview() }}
            onCustomChange={value => { setSourceCustom(value); resetPreview() }}
          />
          <ArrowRight className="mx-auto mb-2 hidden size-4 text-muted-foreground md:block" />
          <PersonaPicker
            label={t.target}
            value={target}
            customValue={targetCustom}
            options={options}
            customLabel={t.custom}
            customPlaceholder={t.customTargetPlaceholder}
            onValueChange={value => { setTarget(value); resetPreview() }}
            onCustomChange={value => { setTargetCustom(value); resetPreview() }}
          />
        </div>

        <div className="grid gap-3 md:grid-cols-[1fr_auto] md:items-end">
          <label className="flex flex-col gap-1.5 text-xs text-muted-foreground">
            {t.mode}
            <select
              value={mode}
              onChange={e => { setMode(e.target.value as api.PersonaMergeMode); resetPreview() }}
              className="border-input bg-transparent rounded-md border px-2.5 py-2 text-sm text-foreground"
            >
              <option value="all">{t.modeAll}</option>
              <option value="impressions_only">{t.modeImpressionsOnly}</option>
            </select>
          </label>
          <Button onClick={handlePreview} disabled={!canPreview || previewLoading}>
            {previewLoading && <Spinner data-icon="inline-start" />}
            {t.preview}
          </Button>
        </div>

        {sameTarget && (
          <p className="text-xs text-destructive">{t.sameTarget}</p>
        )}

        {preview && (
          <div className="rounded-md border bg-muted/20 p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">{t.previewResult}</span>
              <Badge variant={movedTotal > 0 ? 'default' : 'secondary'}>{movedTotal}</Badge>
            </div>
            <div className="grid gap-2 text-sm sm:grid-cols-2">
              <Stat label={t.eventsMoved} value={preview.events_moved} />
              <Stat label={t.impressionsMoved} value={preview.impressions_moved} />
              <Stat label={t.impressionsDropped} value={preview.impressions_dropped} destructive={preview.impressions_dropped > 0} />
              <Stat label={t.personasMoved} value={preview.personas_moved} />
            </div>
          </div>
        )}

        <div className="flex flex-wrap justify-end gap-2">
          {!confirming ? (
            <Button variant="destructive" disabled={!canSubmit} onClick={() => setConfirming(true)}>
              {t.confirm}
            </Button>
          ) : (
            <Button variant="destructive" disabled={!canSubmit || submitting} onClick={handleSubmit}>
              {submitting && <Spinner data-icon="inline-start" />}
              {t.confirmTwice}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function PersonaPicker({
  label,
  value,
  customValue,
  options,
  customLabel,
  customPlaceholder,
  onValueChange,
  onCustomChange,
}: {
  label: string
  value: string
  customValue: string
  options: { value: string; label: string }[]
  customLabel: string
  customPlaceholder: string
  onValueChange: (value: string) => void
  onCustomChange: (value: string) => void
}) {
  return (
    <label className="flex flex-col gap-1.5 text-xs text-muted-foreground">
      {label}
      <select
        value={value}
        onChange={e => onValueChange(e.target.value)}
        className="border-input bg-transparent rounded-md border px-2.5 py-2 text-sm text-foreground"
      >
        {options.map(item => (
          <option key={item.value} value={item.value}>{item.label}</option>
        ))}
        <option value={CUSTOM}>{customLabel}</option>
      </select>
      {value === CUSTOM && (
        <Input
          value={customValue}
          onChange={e => onCustomChange(e.target.value)}
          placeholder={customPlaceholder}
          className="h-9"
        />
      )}
    </label>
  )
}

function Stat({ label, value, destructive }: { label: string; value: number; destructive?: boolean }) {
  return (
    <div className="flex items-center justify-between rounded bg-background/60 px-2 py-1">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn('font-mono font-medium', destructive && 'text-destructive')}>{value}</span>
    </div>
  )
}
