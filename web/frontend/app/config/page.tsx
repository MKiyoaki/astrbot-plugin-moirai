'use client'

import { useEffect, useState, useMemo } from 'react'
import { Save, RefreshCw, Info } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Slider } from '@/components/ui/slider'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { PageHeader } from '@/components/layout/page-header'
import { useApp } from '@/lib/store'
import * as api from '@/lib/api'
import { cn } from '@/lib/utils'

const FIELD_DEPENDENCIES: Record<string, string> = {
  // Embedding
  'embedding_provider': 'embedding_enabled',
  'embedding_model': 'embedding_enabled',
  'embedding_api_url': 'embedding_enabled',
  'embedding_api_key': 'embedding_enabled',
  'embedding_batch_size': 'embedding_enabled',
  'embedding_concurrency': 'embedding_enabled',
  'embedding_batch_interval_ms': 'embedding_enabled',
  'embedding_request_interval_ms': 'embedding_enabled',
  'embedding_failure_tolerance_ratio': 'embedding_enabled',
  'embedding_retry_max': 'embedding_enabled',
  'embedding_retry_delay_ms': 'embedding_enabled',
  
  // VCM
  'context_max_sessions': 'vcm_enabled',
  'context_session_idle_seconds': 'vcm_enabled',
  'context_window_size': 'vcm_enabled',
  
  // Cleanup
  'memory_cleanup_threshold': 'memory_cleanup_enabled',
  'memory_cleanup_interval_days': 'memory_cleanup_enabled',
  
  // Relation
  'persona_isolation_enabled': 'relation_enabled',
  'impression_event_trigger_enabled': 'relation_enabled',
  'impression_event_trigger_threshold': 'relation_enabled',
  'impression_trigger_debounce_hours': 'relation_enabled',
  'impression_update_alpha': 'relation_enabled',
}

function ConfigField({
  fieldKey,
  schema,
  value,
  onChange,
  disabled,
}: {
  fieldKey: string
  schema: api.ConfSchemaField
  value: unknown
  onChange: (v: unknown) => void
  disabled: boolean
}) {
  const { i18n } = useApp()
  const id = `cfg-${fieldKey}`
  
  // Try to get localized label and hint
  const localized = (i18n.config as any).fields?.[fieldKey]
  const label = localized?.label || schema.description
  const hint = localized?.hint || schema.hint

  return (
    <div className={cn("transition-opacity duration-200", disabled && "opacity-40 pointer-events-none")}>
      {schema.type === 'bool' && (
        <div className="flex items-center justify-between py-2">
          <div className="flex-1 pr-4 min-w-0">
            <Label htmlFor={id} className="text-sm font-medium break-words whitespace-normal block">
              {label}
            </Label>
            {hint && (
              <p className="mt-0.5 text-xs text-muted-foreground break-words whitespace-normal">
                {hint}
              </p>
            )}
          </div>
          <Switch
            id={id}
            checked={Boolean(value)}
            onCheckedChange={(v: unknown) => onChange(v)}
            disabled={disabled}
          />
        </div>
      )}

      {schema.type === 'select' && schema.options && (
        <div className="py-2 min-w-0">
          <Label htmlFor={id} className="text-sm font-medium break-words whitespace-normal block">
            {label}
          </Label>
          {hint && (
            <p className="mt-0.5 mb-1.5 text-xs text-muted-foreground break-words whitespace-normal">
              {hint}
            </p>
          )}
          <Select
            disabled={disabled}
            value={String(value)}
            onValueChange={v => onChange(v)}
          >
            <SelectTrigger id={id} className="h-8 text-sm w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {schema.options.map(opt => (
                <SelectItem key={opt} value={opt}>
                  {opt}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {schema.type === 'float' && (
        <div className="py-2 min-w-0">
          <div className="mb-2 flex items-start justify-between gap-4">
            <Label htmlFor={id} className="text-sm font-medium break-words whitespace-normal flex-1">
              {label}
            </Label>
            <span className="w-12 shrink-0 text-right text-sm tabular-nums text-muted-foreground">
              {(typeof value === 'number' ? value : parseFloat(String(value)) || 0).toFixed(2)}
            </span>
          </div>
          {hint && (
            <p className="mb-2 text-xs text-muted-foreground break-words whitespace-normal">
              {hint}
            </p>
          )}
          <Slider
            id={id}
            value={[typeof value === 'number' ? value : parseFloat(String(value)) || 0]}
            onValueChange={(v: unknown) => onChange(Array.isArray(v) ? v[0] : v)}
            min={0} max={1} step={0.01}
            disabled={disabled}
          />
        </div>
      )}

      {(schema.type === 'int' || schema.type === 'string') && (
        <div className="py-2 min-w-0">
          <Label htmlFor={id} className="text-sm font-medium break-words whitespace-normal block">
            {label}
          </Label>
          {hint && (
            <p className="mt-0.5 mb-1.5 text-xs text-muted-foreground break-words whitespace-normal">
              {hint}
            </p>
          )}
          <Input
            id={id}
            type={schema.type === 'int' ? 'number' : 'text'}
            value={String(value ?? '')}
            onChange={e => {
              const raw = e.target.value
              onChange(schema.type === 'int' ? (parseInt(raw, 10) || 0) : raw)
            }}
            disabled={disabled}
            className="h-8 text-sm w-full"
          />
        </div>
      )}
    </div>
  )
}

export default function ConfigPage() {
  const { i18n, sudo, toast } = useApp()
  const [schema, setSchema] = useState<Record<string, api.ConfSchemaField>>({})
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [dirty, setDirty] = useState<Record<string, unknown>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const SECTIONS = useMemo(() => [
    {
      label: i18n.config.sections.webui,
      keys: ['webui_port', 'webui_auth_enabled', 'webui_session_hours', 'webui_sudo_minutes', 'webui_password'],
    },
    {
      label: i18n.config.sections.embedding,
      keys: [
        'embedding_enabled', 
        'embedding_provider', 
        'embedding_model', 
        'embedding_api_url', 
        'embedding_api_key',
        'embedding_batch_size',
        'embedding_concurrency',
        'embedding_batch_interval_ms',
        'embedding_request_interval_ms',
        'embedding_failure_tolerance_ratio',
        'embedding_retry_max',
        'embedding_retry_delay_ms'
      ],
    },
    {
      label: i18n.config.sections.retrieval,
      keys: ['retrieval_top_k', 'retrieval_token_budget', 'retrieval_active_only', 'memory_isolation_enabled'],
    },
    {
      label: i18n.config.sections.vcm,
      keys: ['vcm_enabled', 'context_max_sessions', 'context_session_idle_seconds', 'context_window_size'],
    },
    {
      label: i18n.config.sections.cleanup,
      keys: ['memory_cleanup_enabled', 'memory_cleanup_threshold', 'memory_cleanup_interval_days'],
    },
    {
      label: i18n.config.sections.summaries,
      keys: ['summary_interval_hours', 'summary_word_limit'],
    },
    {
      label: i18n.config.sections.boundary,
      keys: ['boundary_time_gap_minutes', 'boundary_max_messages', 'boundary_max_duration_minutes', 'boundary_topic_drift_threshold'],
    },
    {
      label: i18n.config.sections.relation,
      keys: ['relation_enabled', 'persona_isolation_enabled', 'impression_event_trigger_enabled', 'impression_event_trigger_threshold', 'impression_trigger_debounce_hours', 'impression_update_alpha'],
    },
    {
      label: i18n.config.sections.tasks,
      keys: ['decay_interval_hours', 'persona_synthesis_interval_hours', 'impression_aggregation_interval_hours', 'file_watcher_poll_seconds'],
    },
  ], [i18n])

  const load = async () => {
    setLoading(true)
    try {
      const data = await api.pluginConfig.get()
      setSchema(data.schema)
      setValues(data.values)
      setDirty({})
    } catch {
      toast(i18n.config.loadError, 'destructive')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { setTimeout(() => load(), 0) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleChange = (key: string, val: unknown) => {
    setDirty(prev => ({ ...prev, [key]: val }))
    setValues(prev => ({ ...prev, [key]: val }))
  }

  const handleSave = async () => {
    if (!sudo) { toast(i18n.config.needSudo, 'destructive'); return }
    if (!Object.keys(dirty).length) return
    setSaving(true)
    try {
      await api.pluginConfig.update(dirty)
      toast(i18n.config.saved)
      setDirty({})
    } catch (e: unknown) {
      toast(`${i18n.config.saveError}：${(e as api.ApiError).body}`, 'destructive', 4000)
    } finally {
      setSaving(false)
    }
  }

  const dirtyCount = Object.keys(dirty).length

  const actions = (
    <div className="flex items-center gap-2">
      {dirtyCount > 0 && (
        <Badge variant="secondary" className="text-xs">
          {i18n.config.modifiedItems.replace('{count}', String(dirtyCount))}
        </Badge>
      )}
      <Button variant="ghost" size="icon" onClick={load} title={i18n.common.refresh}>
        <RefreshCw className={loading ? 'animate-spin' : ''} />
      </Button>
      <Button
        size="sm"
        onClick={handleSave}
        disabled={!sudo || saving || dirtyCount === 0}
      >
        <Save className="mr-1 size-3.5" />{i18n.config.save}
      </Button>
    </div>
  )

  return (
    <div className="flex w-full flex-1 h-full flex-col min-w-0 overflow-hidden">
      <PageHeader
        title={i18n.page.config.title}
        description={i18n.page.config.description}
        actions={actions}
      />

      <div className="flex-1 overflow-y-auto min-w-0">
        <div className="mx-auto w-full max-w-2xl space-y-6 p-6">
          <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/40 px-4 py-3">
            <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">{i18n.config.restartHint}</p>
          </div>

          {loading ? (
            <p className="py-8 text-center text-sm text-muted-foreground">{i18n.config.loading}</p>
          ) : (
            SECTIONS.map(section => {
              const fields = section.keys.filter(k => schema[k])
              if (!fields.length) return null
              return (
                <Card key={section.label} className="overflow-hidden">
                  <CardHeader>
                    <CardTitle>{section.label}</CardTitle>
                    <CardDescription>
                      {i18n.config.configCount.replace('{count}', String(fields.length))}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="divide-y">
                    {fields.map(key => {
                      const parentKey = FIELD_DEPENDENCIES[key]
                      const isParentOff = parentKey && !values[parentKey]
                      const fieldDisabled = !sudo || saving || Boolean(isParentOff)
                      
                      return (
                        <ConfigField
                          key={key}
                          fieldKey={key}
                          schema={schema[key]}
                          value={values[key] ?? schema[key].default}
                          onChange={val => handleChange(key, val)}
                          disabled={fieldDisabled}
                        />
                      )
                    })}
                  </CardContent>
                </Card>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}
