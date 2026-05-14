'use client'

import { useEffect, useState, useMemo, useRef } from 'react'
import { Save, Info, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Slider } from '@/components/ui/slider'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { PageHeader } from '@/components/layout/page-header'
import { RefreshButton } from '@/components/shared/refresh-button'
import { OnThisPage } from '@/components/shared/on-this-page'
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
  
  // Retrieval
  'retrieval_sampling_temperature': 'retrieval_weighted_random',

  // Soul Layer
  'soul_decay_rate': 'soul_enabled',
  'soul_recall_depth_init': 'soul_enabled',
  'soul_impression_depth_init': 'soul_enabled',
  'soul_expression_desire_init': 'soul_enabled',
  'soul_creativity_init': 'soul_enabled',

  // Cleanup
  'memory_cleanup_threshold': 'memory_cleanup_enabled',
  'memory_cleanup_interval_days': 'memory_cleanup_enabled',
  'memory_cleanup_retention_days': 'memory_cleanup_enabled',
  
  // Relation
  'persona_isolation_enabled': 'relation_enabled',
  'impression_event_trigger_enabled': 'relation_enabled',
  'impression_event_trigger_threshold': 'relation_enabled',
  'impression_trigger_debounce_hours': 'relation_enabled',
  'impression_update_alpha': 'relation_enabled',

  // Boundary / Extraction
  'semantic_clustering_eps': 'extraction_strategy',
  'semantic_clustering_min_samples': 'extraction_strategy',
  'boundary_topic_drift_threshold': 'boundary_topic_drift_enabled',
  'boundary_topic_drift_min_messages': 'boundary_topic_drift_enabled',
  'boundary_topic_drift_interval': 'boundary_topic_drift_enabled',

  // Tasks
  'decay_interval_hours': 'decay_enabled',
  'summary_interval_hours': 'summary_enabled',
  'summary_word_limit': 'summary_enabled',
  'summary_mood_source': 'summary_enabled',
  'persona_synthesis_interval_hours': 'persona_synthesis_enabled',
}

function ConfigField({
  fieldKey,
  schema,
  value,
  onChange,
  disabled,
  providers = [],
}: {
  fieldKey: string
  schema: api.ConfSchemaField
  value: unknown
  onChange: (v: unknown) => void
  disabled: boolean
  providers?: { id: string; name: string }[]
}) {
  const { i18n } = useApp()
  const id = `cfg-${fieldKey}`
  
  const localized = (i18n.config as any).fields?.[fieldKey]
  const label = localized?.label || schema.description
  const hint = localized?.hint || schema.hint
  const tooltip = localized?.tooltip

  const isSelectProvider = (schema as any)._special === 'select_provider'

  return (
    <div className={cn("transition-all duration-300", disabled && "opacity-40 grayscale-[0.5] pointer-events-none")}>
      {schema.type === 'bool' && (
        <div className="flex items-center justify-between py-3">
          <div className="flex-1 pr-4 min-w-0">
            <div className="flex items-center gap-1.5 mb-0.5">
              <Label htmlFor={id} className="text-sm font-medium break-words whitespace-normal cursor-pointer hover:text-primary transition-colors">
                {label}
              </Label>
              {tooltip && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Info className="size-3.5 text-muted-foreground/60 hover:text-muted-foreground cursor-help" />
                  </TooltipTrigger>
                  <TooltipContent className="max-w-[280px] text-xs leading-relaxed">
                    {tooltip}
                  </TooltipContent>
                </Tooltip>
              )}
            </div>
            {hint && (
              <p className="text-xs text-muted-foreground/80 break-words whitespace-normal leading-normal">
                {hint}
              </p>
            )}
          </div>
          <Switch
            id={id}
            checked={Boolean(value)}
            onCheckedChange={(v: unknown) => onChange(v)}
            disabled={disabled}
            className="data-[state=checked]:bg-primary"
          />
        </div>
      )}

      {(schema.type === 'select' || isSelectProvider) && (
        <div className="py-3 min-w-0">
          <div className="flex items-center gap-1.5 mb-1.5">
            <Label htmlFor={id} className="text-sm font-medium break-words whitespace-normal">
              {label}
            </Label>
            {tooltip && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Info className="size-3.5 text-muted-foreground/60 hover:text-muted-foreground cursor-help" />
                </TooltipTrigger>
                <TooltipContent className="max-w-[280px] text-xs leading-relaxed">
                  {tooltip}
                </TooltipContent>
              </Tooltip>
            )}
          </div>
          {hint && (
            <p className="mt-0.5 mb-2 text-xs text-muted-foreground/80 break-words whitespace-normal leading-normal">
              {hint}
            </p>
          )}
          <Select
            disabled={disabled}
            value={isSelectProvider && !value ? '__default__' : String(value ?? '')}
            onValueChange={v => onChange(v === '__default__' ? '' : v)}
          >
            <SelectTrigger id={id} className="h-9 text-sm w-full bg-background border-muted-foreground/20 hover:border-primary/50 transition-colors">
              <SelectValue placeholder={localized?.selectPlaceholder} />
            </SelectTrigger>
            <SelectContent>
              {isSelectProvider && (
                <SelectItem value="__default__" className="text-primary font-medium">
                  {i18n.common.none} (AstrBot Default)
                </SelectItem>
              )}
              {isSelectProvider ? (
                providers.map(p => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name}
                  </SelectItem>
                ))
              ) : (
                schema.options?.map(opt => {
                  const isObj = typeof opt === 'object' && opt !== null
                  const val = isObj ? (opt as any).value : String(opt)
                  const lab = isObj ? (opt as any).label : String(opt)
                  return (
                    <SelectItem key={val} value={val}>
                      {lab}
                    </SelectItem>
                  )
                })
              )}
            </SelectContent>
          </Select>
          {isSelectProvider && !value && (
            <p className="mt-1.5 text-[10px] text-primary/80 font-medium px-1 flex items-center gap-1">
              <Info className="size-2.5" />
              {localized?.defaultHint}
            </p>
          )}
        </div>
      )}

      {schema.type === 'float' && (
        <div className="py-3 min-w-0">
          <div className="mb-2.5 flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5 mb-0.5">
                <Label htmlFor={id} className="text-sm font-medium break-words whitespace-normal">
                  {label}
                </Label>
                {tooltip && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Info className="size-3.5 text-muted-foreground/60 hover:text-muted-foreground cursor-help" />
                    </TooltipTrigger>
                    <TooltipContent className="max-w-[280px] text-xs leading-relaxed">
                      {tooltip}
                    </TooltipContent>
                  </Tooltip>
                )}
              </div>
              {hint && (
                <p className="text-xs text-muted-foreground/80 break-words whitespace-normal leading-normal">
                  {hint}
                </p>
              )}
            </div>
            <Badge variant="outline" className="h-5 px-1.5 font-mono text-[10px] tabular-nums bg-muted/50 border-none shrink-0">
              {(typeof value === 'number' ? value : parseFloat(String(value)) || 0).toFixed(2)}
            </Badge>
          </div>
          <Slider
            id={id}
            value={[typeof value === 'number' ? value : parseFloat(String(value)) || 0]}
            onValueChange={(v: number[]) => onChange(v[0])}
            min={schema.min ?? 0} 
            max={schema.max ?? 1} 
            step={schema.step ?? 0.01}
            disabled={disabled}
            className="py-2"
          />
        </div>
      )}

      {(schema.type === 'int' || schema.type === 'string') && !isSelectProvider && (
        <div className="py-3 min-w-0">
          <div className="flex items-center gap-1.5 mb-1.5">
            <Label htmlFor={id} className="text-sm font-medium break-words whitespace-normal">
              {label}
            </Label>
            {tooltip && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Info className="size-3.5 text-muted-foreground/60 hover:text-muted-foreground cursor-help" />
                </TooltipTrigger>
                <TooltipContent className="max-w-[280px] text-xs leading-relaxed">
                  {tooltip}
                </TooltipContent>
              </Tooltip>
            )}
          </div>
          {hint && (
            <p className="mt-0.5 mb-2 text-xs text-muted-foreground/80 break-words whitespace-normal leading-normal">
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
            className="h-9 text-sm w-full bg-background border-muted-foreground/20 focus-visible:ring-primary/30 transition-all"
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
  const [providers, setProviders] = useState<{ id: string; name: string }[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [activeSection, setActiveSection] = useState<string>('')
  
  const scrollAreaRef = useRef<HTMLDivElement>(null)

  const SECTIONS = useMemo(() => [
    {
      id: 'webui',
      label: i18n.config.sections.webui,
      keys: [
        'llm_provider', 
        'webui_enabled',
        'webui_port', 
        'webui_auth_enabled', 
        'webui_session_hours', 
        'webui_sudo_minutes', 
        'webui_password'
      ],
    },
    {
      id: 'embedding',
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
      id: 'retrieval',
      label: i18n.config.sections.retrieval,
      keys: [
        'retrieval_top_k', 
        'retrieval_token_budget', 
        'retrieval_active_only', 
        'memory_isolation_enabled', 
        'retrieval_weighted_random', 
        'retrieval_sampling_temperature'
      ],
    },
    {
      id: 'vcm',
      label: i18n.config.sections.vcm,
      keys: [
        'vcm_enabled', 
        'context_max_sessions', 
        'context_session_idle_seconds', 
        'context_window_size'
      ],
    },
    {
      id: 'soul',
      label: i18n.config.sections.soul,
      keys: [
        'soul_enabled', 
        'soul_decay_rate', 
        'soul_recall_depth_init', 
        'soul_impression_depth_init', 
        'soul_expression_desire_init', 
        'soul_creativity_init'
      ],
    },
    {
      id: 'cleanup',
      label: i18n.config.sections.cleanup,
      keys: [
        'memory_cleanup_enabled', 
        'memory_cleanup_threshold', 
        'memory_cleanup_interval_days', 
        'memory_cleanup_retention_days'
      ],
    },
    {
      id: 'summaries',
      label: i18n.config.sections.summaries,
      keys: [
        'summary_enabled',
        'summary_interval_hours', 
        'summary_word_limit', 
        'summary_mood_source'
      ],
    },
    {
      id: 'boundary',
      label: i18n.config.sections.boundary,
      keys: [
        'persona_influenced_summary', 
        'extraction_strategy',
        'semantic_clustering_eps',
        'semantic_clustering_min_samples',
        'tag_normalization_threshold',
        'tag_seeds',
        'boundary_time_gap_minutes', 
        'boundary_max_messages', 
        'boundary_max_duration_minutes', 
        'boundary_topic_drift_enabled',
        'boundary_topic_drift_threshold',
        'boundary_topic_drift_min_messages',
        'boundary_topic_drift_interval'
      ],
    },
    {
      id: 'relation',
      label: i18n.config.sections.relation,
      keys: [
        'relation_enabled', 
        'persona_default_confidence', 
        'persona_isolation_enabled', 
        'impression_event_trigger_enabled', 
        'impression_event_trigger_threshold', 
        'impression_trigger_debounce_hours', 
        'impression_update_alpha'
      ],
    },
    {
      id: 'tasks',
      label: i18n.config.sections.tasks,
      keys: [
        'show_thinking_process',
        'show_system_prompt',
        'show_injection_summary',
        'decay_enabled',
        'decay_interval_hours',
        'persona_synthesis_enabled',
        'persona_synthesis_interval_hours', 
        'markdown_projection_enabled',
        'impression_aggregation_interval_hours', 
        'file_watcher_poll_seconds',
        'migration_auto_backup'
      ],
    },
  ], [i18n])

  const load = async () => {
    setLoading(true)
    try {
      const confData = await api.pluginConfig.get()
      setSchema(confData.schema)
      setValues(confData.values)
      setDirty({})
      
      try {
        const provData = await api.pluginConfig.providers()
        setProviders(provData.providers || [])
      } catch (e) {
        console.warn('Failed to fetch providers:', e)
        setProviders([])
      }
    } catch {
      toast(i18n.config.loadError, 'destructive')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Intersection Observer for Scroll Spy
  useEffect(() => {
    if (loading) return
    const observer = new IntersectionObserver(
      (entries) => {
        // Find the section that is most prominent in the viewport
        const visibleSections = entries
          .filter(entry => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)
        
        if (visibleSections.length > 0) {
          setActiveSection(visibleSections[0].target.id)
        }
      },
      { 
        root: null,
        threshold: [0, 0.1, 0.5, 1.0],
        rootMargin: '-80px 0px -50% 0px' 
      }
    )

    SECTIONS.forEach((section) => {
      const el = document.getElementById(section.id)
      if (el) observer.observe(el)
    })

    return () => observer.disconnect()
  }, [loading, SECTIONS])

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

  const scrollTo = (id: string) => {
    const el = document.getElementById(id)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }

  const dirtyCount = Object.keys(dirty).length

  const actions = (
    <div className="flex items-center gap-2">
      {dirtyCount > 0 && (
        <Badge variant="secondary" className="text-[10px] h-5 px-1.5 flex items-center bg-primary/10 text-primary border-primary/20 animate-pulse">
          {i18n.config.modifiedItems.replace('{count}', String(dirtyCount))}
        </Badge>
      )}
      <Button
        size="sm"
        className="h-8 gap-1.5 px-3 shadow-md transition-all hover:shadow-lg active:scale-95"
        onClick={handleSave}
        disabled={!sudo || saving || dirtyCount === 0}
      >
        <Save className="size-3.5" />
        <span className="hidden sm:inline">{i18n.config.save}</span>
      </Button>
    </div>
  )

  const globalActions = (
    <RefreshButton 
      onClick={load} 
      loading={loading} 
    />
  )

  return (
    <div className="flex w-full flex-1 flex-col min-w-0 animate-in fade-in slide-in-from-bottom-4 duration-500 ease-out fill-mode-both">
      <PageHeader
        title={i18n.page.config.title}
        description={i18n.page.config.description}
        actions={actions}
        globalActions={globalActions}
      />

      <TooltipProvider delayDuration={0}>
      <div className="flex flex-1 justify-center gap-8 px-6 pb-24 pt-6">
        {/* Main content — document scrolls naturally */}
        <div ref={scrollAreaRef} className="flex-1 max-w-3xl min-w-0 space-y-8">
          <div className="flex items-start gap-3 rounded-xl border border-primary/20 bg-primary/5 px-4 py-3.5 transition-all hover:bg-primary/10">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-primary" />
            <div className="space-y-1">
              <p className="text-sm font-medium text-primary leading-none">{i18n.config.restartHint}</p>
              <p className="text-xs text-primary/70 leading-relaxed">配置修改后不会立即对运行中的引擎生效，请确保在保存后重新启动 AstrBot 插件。</p>
            </div>
          </div>

          {loading ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3">
              <div className="size-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
              <p className="text-sm text-muted-foreground animate-pulse">{i18n.config.loading}</p>
            </div>
          ) : (
            SECTIONS.map(section => {
              const fields = section.keys.filter(k => schema[k])
              if (!fields.length) return null
              return (
                <div key={section.id} id={section.id} className="scroll-mt-20 transition-all">
                  <Card className="overflow-hidden border-muted/60 shadow-sm hover:shadow-md transition-shadow">
                    <CardHeader className="border-b border-border/50 pb-4">
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-lg font-bold tracking-tight">{section.label}</CardTitle>
                        <Badge variant="outline" className="font-mono text-[10px] opacity-70">
                          {section.id.toUpperCase()}
                        </Badge>
                      </div>
                      <CardDescription className="text-xs">
                        {i18n.config.configCount.replace('{count}', String(fields.length))}
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="divide-y divide-muted/50 pt-2 px-6">
                      {fields.map(key => {
                        const parentKey = FIELD_DEPENDENCIES[key]
                        let isParentOff = false
                        if (parentKey) {
                          const parentVal = values[parentKey]
                          const parentSchema = schema[parentKey]
                          if (parentSchema?.type === 'bool') {
                            isParentOff = !parentVal
                          } else if (parentKey === 'extraction_strategy') {
                            isParentOff = parentVal !== 'semantic'
                          }
                        }

                        const fieldDisabled = !sudo || saving || isParentOff

                        return (
                          <ConfigField
                            key={key}
                            fieldKey={key}
                            schema={schema[key]}
                            value={values[key] ?? schema[key].default}
                            onChange={val => handleChange(key, val)}
                            disabled={fieldDisabled}
                            providers={providers}
                          />
                        )
                      })}
                    </CardContent>
                  </Card>
                </div>
              )
            })
          )}
        </div>

        {/* TOC — sticky in document flow, no overflow-hidden ancestors */}
        {!loading && (
          <aside className="hidden lg:block w-[220px] shrink-0">
            <div className="sticky top-6">
              <OnThisPage
                items={SECTIONS.filter(s => s.keys.some(k => schema[k]))}
                activeId={activeSection}
                onItemClick={scrollTo}
                title={i18n.common.onThisPage}
              />
            </div>
          </aside>
        )}
      </div>
      </TooltipProvider>
    </div>
  )
}
