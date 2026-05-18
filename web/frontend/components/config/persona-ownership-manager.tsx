'use client'

import { useEffect, useMemo, useState } from 'react'
import { ArrowRight, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { useApp } from '@/lib/store'
import * as api from '@/lib/api'
import { cn } from '@/lib/utils'

type PersonaChoice = string

const CUSTOM = '__custom__'

export function PersonaOwnershipManager({ embedded = false }: { embedded?: boolean }) {
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
  const submitBlockedReason = !sudo
    ? i18n.config.needSudo
    : !preview
      ? t.previewRequired
      : sameTarget
        ? t.sameTarget
        : ''

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
    if (!sudo) { toast(i18n.config.needSudo, 'destructive'); return }
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

  const header = (
    <CardHeader className="border-b border-border/50 pb-4">
      <div className="flex items-center justify-between">
        <CardTitle className="text-lg font-bold tracking-tight">{t.title}</CardTitle>
        <Button variant="ghost" size="sm" onClick={loadBots} className="h-7 gap-1.5 px-2 text-xs text-muted-foreground hover:text-foreground">
          <RefreshCw className="size-3" />
          <span className="hidden sm:inline">{t.refresh}</span>
        </Button>
      </div>
      <CardDescription className="text-xs">{t.description}</CardDescription>
    </CardHeader>
  )

  const content = (
    <CardContent className="flex flex-col gap-5 px-6 py-5">
      {/* Source → Target row */}
      <div className="grid grid-cols-[1fr_32px_1fr] items-end gap-2">
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
        <div className="flex items-center justify-center pb-0.5">
          <ArrowRight className="size-4 text-muted-foreground/60" />
        </div>
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

      {/* Mode + actions row */}
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-1 flex-col gap-1.5 min-w-[180px]">
          <span className="text-xs text-muted-foreground">{t.mode}</span>
          <Select value={mode} onValueChange={v => { setMode(v as api.PersonaMergeMode); resetPreview() }}>
            <SelectTrigger className="h-9 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t.modeAll}</SelectItem>
              <SelectItem value="impressions_only">{t.modeImpressionsOnly}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex shrink-0 flex-col items-end gap-1.5">
          <Button onClick={handlePreview} disabled={!canPreview || previewLoading} className="h-9">
            {previewLoading && <Spinner data-icon="inline-start" />}
            {t.preview}
          </Button>
        </div>
      </div>

      {sameTarget && (
        <p className="text-xs text-destructive">{t.sameTarget}</p>
      )}

      {/* Preview result */}
      {preview && (
        <div className="rounded-lg border bg-muted/20 p-3">
          <div className="mb-2.5 flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">{t.previewResult}</span>
            <Badge variant={movedTotal > 0 ? 'default' : 'secondary'} className="font-mono text-[10px]">
              {movedTotal}
            </Badge>
          </div>
          <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
            <Stat label={t.eventsMoved} value={preview.events_moved} />
            <Stat label={t.impressionsMoved} value={preview.impressions_moved} />
            <Stat label={t.impressionsDropped} value={preview.impressions_dropped} destructive={preview.impressions_dropped > 0} />
            <Stat label={t.personasMoved} value={preview.personas_moved} />
          </div>
        </div>
      )}

      {/* Submit row */}
      <div className="flex justify-end gap-2">
        {!confirming ? (
          <div className="flex flex-col items-end gap-1">
            <Button variant="destructive" size="sm" disabled={!canSubmit} onClick={() => setConfirming(true)}>
              {t.confirm}
            </Button>
            {!canSubmit && submitBlockedReason && (
              <p className="text-[10px] text-muted-foreground">{submitBlockedReason}</p>
            )}
          </div>
        ) : (
          <Button variant="destructive" size="sm" disabled={!canSubmit || submitting} onClick={handleSubmit}>
            {submitting && <Spinner data-icon="inline-start" />}
            {t.confirmTwice}
          </Button>
        )}
      </div>
    </CardContent>
  )

  if (embedded) {
    return (
      <div id="persona-ownership" className="border-t border-border/50 bg-muted/10">
        {header}
        {content}
      </div>
    )
  }

  return (
    <Card id="persona-ownership" className="mt-4 overflow-hidden border-muted/60 shadow-sm">
      {header}
      {content}
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
    <div className="flex flex-col gap-1.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <Select value={value} onValueChange={onValueChange}>
        <SelectTrigger className="h-9 text-sm">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map(item => (
            <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>
          ))}
          <SelectItem value={CUSTOM}>{customLabel}</SelectItem>
        </SelectContent>
      </Select>
      {value === CUSTOM && (
        <Input
          value={customValue}
          onChange={e => onCustomChange(e.target.value)}
          placeholder={customPlaceholder}
          className="h-9 text-sm"
        />
      )}
    </div>
  )
}

function Stat({ label, value, destructive }: { label: string; value: number; destructive?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-md bg-background/60 px-2.5 py-2">
      <span className="text-[10px] text-muted-foreground leading-none">{label}</span>
      <span className={cn('font-mono text-sm font-semibold', destructive ? 'text-destructive' : 'text-foreground')}>
        {value}
      </span>
    </div>
  )
}
