'use client'

import { useEffect, useState, useMemo, useRef } from 'react'
import { Save, Info, AlertTriangle, FlaskConical, Search, X, Wand2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Slider } from '@/components/ui/slider'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { PageHeader } from '@/components/layout/page-header'
import { RefreshButton } from '@/components/shared/refresh-button'
import { OnThisPage } from '@/components/shared/on-this-page'
import { PersonaOwnershipManager } from '@/components/config/persona-ownership-manager'
import { QuickSetupWizard } from '@/components/config/quick-setup-wizard'
import { useApp } from '@/lib/store'
import * as api from '@/lib/api'
import { cn } from '@/lib/utils'
import { getStored, setStored } from '@/lib/safe-storage'

const FIELD_DEPENDENCIES: Record<string, string> = {
  // Embedding
  'embedding_provider': 'embedding_enabled',
  'embedding_model': 'embedding_enabled',
  'embedding_api_url': 'embedding_provider',
  'embedding_api_key': 'embedding_provider',
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
  'persona_isolation_legacy_visible': 'persona_isolation_enabled',
  'persona_merge_audit_enabled': 'persona_isolation_enabled',
  'persona_default_view_mode': 'persona_isolation_enabled',
  'impression_injection_enabled': 'relation_enabled',
  'impression_injection_max_items': 'impression_injection_enabled',
  'impression_injection_min_confidence': 'impression_injection_enabled',
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
  'periodic_flush_minutes': 'periodic_flush_enabled',
  'periodic_flush_tail_keep': 'periodic_flush_enabled',

  // Tasks
  'decay_interval_hours': 'decay_enabled',
  'summary_interval_hours': 'summary_enabled',
  'summary_mood_source': 'summary_enabled',
  'persona_synthesis_interval_hours': 'persona_synthesis_enabled',
  'persona_synthesis_trigger_messages': 'persona_synthesis_enabled',
  'persona_synthesis_min_events': 'persona_synthesis_enabled',
  'persona_synthesis_cooldown_hours': 'persona_synthesis_enabled',
}

// Progressive-disclosure tiers. A field shows when its level rank is <= the
// selected tier rank. Fields with no explicit level default to "basic".
type ConfigLevel = 'basic' | 'advanced' | 'expert'
const LEVEL_RANK: Record<ConfigLevel, number> = { basic: 0, advanced: 1, expert: 2 }

function fieldLevel(schema: api.ConfSchemaField | undefined): ConfigLevel {
  const lvl = schema?.level
  if (lvl === 'advanced' || lvl === 'expert') return lvl
  return 'basic'
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
  // Strip leading cluster markers — the local WebUI already shows them via
  // the group divider, so duplicating in the label adds visual noise. We strip
  // 【...】 tags and the cluster emojis (including 🧪, which is replaced by an
  // explicit "experimental" badge). 🟢 is kept as the basic-field indicator.
  const rawLabel = localized?.label || schema.description || ''
  const label = String(rawLabel)
    .replace(/^【[^】]+】\s*/u, '')
    .replace(/^(?:🎯|⏱️|🌊|🔄|🔒|💭|🧪)\s*/u, '')
  const hint = localized?.hint || schema.hint
  const tooltip = localized?.tooltip

  const isSelectProvider = (schema as any)._special === 'select_provider'
  const hasOptions = !!(schema.options && schema.options.length > 0)
  const isSelect = schema.type === 'select' || isSelectProvider || hasOptions

  const labelNode = (
    <div className="flex items-center gap-1.5 flex-wrap">
      <Label htmlFor={id} className="text-sm font-medium break-words whitespace-normal cursor-pointer hover:text-primary transition-colors">
        {label}
      </Label>
      {schema.experimental && (
        <Badge variant="outline" className="h-4 gap-0.5 px-1 text-[9px] font-medium border-amber-500/40 text-amber-600 dark:text-amber-400">
          <FlaskConical className="size-2.5" />
          {(i18n.config as any).experimental}
        </Badge>
      )}
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
  )

  return (
    <div className={cn("transition-all duration-300", disabled && "opacity-40 grayscale-[0.5] pointer-events-none")}>
      {schema.type === 'bool' && (
        <div className="flex items-center justify-between py-3">
          <div className="flex-1 pr-4 min-w-0">
            <div className="mb-0.5">{labelNode}</div>
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

      {isSelect && (
        <div className="py-3 min-w-0">
          <div className="mb-1.5">{labelNode}</div>
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
              <div className="mb-0.5">{labelNode}</div>
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

      {(schema.type === 'int' || schema.type === 'string') && !isSelectProvider && !hasOptions && (
        <div className="py-3 min-w-0">
          <div className="mb-1.5">{labelNode}</div>
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
  const { i18n, sudo, toast, setIsDirty } = useApp()
  const [schema, setSchema] = useState<Record<string, api.ConfSchemaField>>({})
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [dirty, setDirty] = useState<Record<string, unknown>>({})
  const [providers, setProviders] = useState<{ id: string; name: string }[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [activeSection, setActiveSection] = useState<string>('')
  const [search, setSearch] = useState<string>('')
  const [wizardOpen, setWizardOpen] = useState(false)
  const [restarting, setRestarting] = useState(false)
  const [configLevel, setConfigLevel] = useState<ConfigLevel>(() => {
    const stored = getStored('em_config_level')
    if (stored === 'basic' || stored === 'advanced' || stored === 'expert') return stored
    // Migrate from the legacy binary "show advanced" flag.
    return (getStored('em_show_advanced_config') ?? '1') === '0' ? 'basic' : 'advanced'
  })

  const handleLevelChange = (v: string) => {
    if (v !== 'basic' && v !== 'advanced' && v !== 'expert') return
    setConfigLevel(v)
    setStored('em_config_level', v)
  }

  const scrollAreaRef = useRef<HTMLDivElement>(null)

  // The 12 logical sub-sections. Kept flat; grouped into 6 categories below.
  const SECTIONS = useMemo(() => [
    {
      id: 'webui',
      label: i18n.config.sections.webui,
      keys: [
        'llm_provider',
        'llm_concurrency',
        'webui_enabled',
        'webui_port',
        'webui_auth_enabled',
        'webui_session_hours',
        'webui_sudo_minutes',
        'webui_auto_restart_on_save',
        'webui_password',
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
        'embedding_request_batch_size',
        'embedding_concurrency',
        'embedding_batch_interval_ms',
        'embedding_request_interval_ms',
        'embedding_failure_tolerance_ratio',
        'embedding_retry_max',
        'embedding_retry_delay_ms',
      ],
    },
    {
      id: 'retrieval',
      label: i18n.config.sections.retrieval,
      keys: [
        'retrieval_top_k',
        'retrieval_active_top_k',
        'retrieval_token_budget',
        'retrieval_salience_weight',
        'retrieval_rrf_k',
        'retrieval_active_only',
        'memory_isolation_enabled',
        'retrieval_weighted_random',
        'retrieval_sampling_temperature',
        'injection_position',
        'injection_auto_clear',
      ],
    },
    {
      id: 'vcm',
      label: i18n.config.sections.vcm,
      keys: [
        'vcm_enabled',
        'context_max_sessions',
        'context_session_idle_seconds',
        'context_window_size',
        'context_max_history_messages',
        'context_cleanup_batch_size',
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
        'soul_creativity_init',
      ],
    },
    {
      id: 'cleanup',
      label: i18n.config.sections.cleanup,
      keys: [
        'memory_cleanup_enabled',
        'memory_cleanup_threshold',
        'memory_cleanup_interval_days',
        'memory_cleanup_retention_days',
        'raw_message_retention_days',
      ],
    },
    {
      id: 'summaries',
      label: i18n.config.sections.summaries,
      keys: [
        'summary_enabled',
        'summary_interval_hours',
        'summary_mood_source',
      ],
    },
    {
      id: 'boundary',
      label: i18n.config.sections.boundary,
      // 5 logical clusters rendered with visual dividers inside one card.
      groups: [
        {
          label: (i18n.config as any).boundaryGroups?.basic?.label ?? '基础',
          hint: (i18n.config as any).boundaryGroups?.basic?.hint,
          keys: ['persona_influenced_summary', 'tag_seeds'],
        },
        {
          label: (i18n.config as any).boundaryGroups?.extraction?.label ?? '提取策略',
          hint: (i18n.config as any).boundaryGroups?.extraction?.hint,
          keys: [
            'extraction_strategy',
            'semantic_clustering_eps',
            'semantic_clustering_min_samples',
            'tag_normalization_threshold',
          ],
        },
        {
          label: (i18n.config as any).boundaryGroups?.hardBoundary?.label ?? '硬边界',
          hint: (i18n.config as any).boundaryGroups?.hardBoundary?.hint,
          keys: [
            'boundary_time_gap_minutes',
            'boundary_max_messages',
            'boundary_max_duration_minutes',
            'summary_trigger_rounds',
          ],
        },
        {
          label: (i18n.config as any).boundaryGroups?.topicDrift?.label ?? '话题漂移',
          hint: (i18n.config as any).boundaryGroups?.topicDrift?.hint,
          keys: [
            'boundary_topic_drift_enabled',
            'boundary_topic_drift_threshold',
            'boundary_topic_drift_min_messages',
            'boundary_topic_drift_interval',
          ],
        },
        {
          label: (i18n.config as any).boundaryGroups?.periodicFlush?.label ?? '周期扫描',
          hint: (i18n.config as any).boundaryGroups?.periodicFlush?.hint,
          keys: [
            'periodic_flush_enabled',
            'periodic_flush_minutes',
            'periodic_flush_tail_keep',
          ],
        },
      ],
      keys: [
        'persona_influenced_summary', 'tag_seeds',
        'extraction_strategy', 'semantic_clustering_eps', 'semantic_clustering_min_samples', 'tag_normalization_threshold',
        'boundary_time_gap_minutes', 'boundary_max_messages', 'boundary_max_duration_minutes', 'summary_trigger_rounds',
        'boundary_topic_drift_enabled', 'boundary_topic_drift_threshold', 'boundary_topic_drift_min_messages', 'boundary_topic_drift_interval',
        'periodic_flush_enabled', 'periodic_flush_minutes', 'periodic_flush_tail_keep',
      ],
    },
    {
      id: 'relation',
      label: i18n.config.sections.relation,
      keys: [
        'relation_enabled',
        'impression_injection_enabled',
        'impression_injection_max_items',
        'impression_injection_min_confidence',
        'persona_default_confidence',
        'bot_persona_name_override',
        'persona_isolation_enabled',
        'persona_isolation_legacy_visible',
        'persona_merge_audit_enabled',
        'persona_default_view_mode',
        'impression_event_trigger_enabled',
        'impression_event_trigger_threshold',
        'impression_trigger_debounce_hours',
        'impression_update_alpha',
        'impression_aggregation_interval_hours',
      ],
    },
    {
      id: 'tasks',
      label: i18n.config.sections.tasks,
      keys: [
        'decay_enabled',
        'decay_lambda',
        'decay_interval_hours',
        'persona_synthesis_enabled',
        'persona_synthesis_interval_hours',
        'persona_synthesis_trigger_messages',
        'persona_synthesis_min_events',
        'persona_synthesis_cooldown_hours',
        'markdown_projection_enabled',
        'file_watcher_poll_seconds',
        'migration_auto_backup',
      ],
    },
    {
      id: 'debug_display',
      label: i18n.config.sections.debug_display,
      keys: [
        'show_thinking_process',
        'show_system_prompt',
        'show_injection_summary',
        'show_llm_call_details',
      ],
    },
    {
      id: 'backup',
      label: i18n.config.sections.backup,
      keys: [
        'backup_enabled',
        'backup_retention_days',
      ],
    },
  ], [i18n])

  // 6 top-level categories aligned with the WebUI "three memory axes" model.
  const CATEGORIES = useMemo(() => [
    { id: 'cat-general', label: (i18n.config as any).categories.general, sectionIds: ['webui', 'backup', 'debug_display'] },
    { id: 'cat-info', label: (i18n.config as any).categories.infoFlow, sectionIds: ['retrieval', 'embedding'] },
    { id: 'cat-event', label: (i18n.config as any).categories.eventFlow, sectionIds: ['boundary', 'vcm'] },
    { id: 'cat-relation', label: (i18n.config as any).categories.relations, sectionIds: ['relation', 'soul'] },
    { id: 'cat-summary', label: (i18n.config as any).categories.summary, sectionIds: ['summaries'] },
    { id: 'cat-database', label: (i18n.config as any).categories.database, sectionIds: ['cleanup', 'tasks'] },
  ], [i18n])

  const sectionById = useMemo(() => {
    const m: Record<string, (typeof SECTIONS)[number]> = {}
    SECTIONS.forEach(s => { m[s.id] = s })
    return m
  }, [SECTIONS])

  const load = async () => {
    setLoading(true)
    try {
      const confData = await api.pluginConfig.get()
      setSchema(confData.schema)
      setValues(confData.values)
      setDirty({})
      setIsDirty(false)

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

  useEffect(() => {
    return () => setIsDirty(false)
  }, [setIsDirty])

  // Localized label/hint lookup, used by the level filter and search.
  const fieldText = useMemo(() => {
    return (key: string): string => {
      const localized = (i18n.config as any).fields?.[key]
      const s = schema[key]
      const label = localized?.label || s?.description || ''
      const hint = localized?.hint || s?.hint || ''
      return `${key} ${label} ${hint}`.toLowerCase()
    }
  }, [i18n, schema])

  // Whether a field passes the current tier filter.
  const passesLevel = useMemo(() => {
    return (key: string): boolean => {
      const s = schema[key]
      if (!s) return false
      return LEVEL_RANK[fieldLevel(s)] <= LEVEL_RANK[configLevel]
    }
  }, [schema, configLevel])

  const searchActive = search.trim().length > 0

  // Flat search results across every category/section, ignoring tier filter.
  const searchResults = useMemo(() => {
    if (!searchActive) return []
    const q = search.trim().toLowerCase()
    const out: { key: string; categoryLabel: string; sectionLabel: string }[] = []
    const seen = new Set<string>()
    CATEGORIES.forEach(cat => {
      cat.sectionIds.forEach(sid => {
        const section = sectionById[sid]
        if (!section) return
        section.keys.forEach(key => {
          if (seen.has(key)) return
          if (!schema[key]) return
          if (!fieldText(key).includes(q)) return
          seen.add(key)
          out.push({ key, categoryLabel: cat.label, sectionLabel: section.label })
        })
      })
    })
    return out
  }, [searchActive, search, CATEGORIES, sectionById, schema, fieldText])

  // Intersection Observer for Scroll Spy (disabled while searching)
  useEffect(() => {
    if (loading || searchActive) return
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter(entry => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)
        if (visible.length > 0) {
          setActiveSection(visible[0].target.id)
        }
      },
      { root: null, threshold: [0, 0.1, 0.5, 1.0], rootMargin: '-80px 0px -50% 0px' }
    )

    SECTIONS.forEach((section) => {
      const el = document.getElementById(section.id)
      if (el) observer.observe(el)
    })
    CATEGORIES.forEach((cat) => {
      const el = document.getElementById(cat.id)
      if (el) observer.observe(el)
    })

    return () => observer.disconnect()
  }, [loading, searchActive, SECTIONS, CATEGORIES])

  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (Object.keys(dirty).length > 0) {
        e.preventDefault()
        e.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [dirty])

  useEffect(() => {
    if (loading) return
    let timer: number | null = null
    const scrollToTarget = (target: string) => {
      sessionStorage.removeItem('em_config_scroll_target')
      timer = window.setTimeout(() => {
        document.getElementById(target)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }, 120)
    }
    const handleScrollTarget = (event: Event) => {
      const target = (event as CustomEvent<string>).detail || 'persona-ownership'
      scrollToTarget(target)
    }
    window.addEventListener('em_config_scroll_target', handleScrollTarget)

    const hashTarget = window.location.hash === '#persona-ownership' ? 'persona-ownership' : null
    const storedTarget = sessionStorage.getItem('em_config_scroll_target')
    const target = storedTarget || hashTarget
    if (target) {
      scrollToTarget(target)
    }

    return () => {
      window.removeEventListener('em_config_scroll_target', handleScrollTarget)
      if (timer !== null) window.clearTimeout(timer)
    }
  }, [loading])

  const handleChange = (key: string, val: unknown) => {
    setDirty(prev => ({ ...prev, [key]: val }))
    setValues(prev => ({ ...prev, [key]: val }))
    setIsDirty(true)
  }

  // After an auto-restart save, the WebUI server goes down then comes back.
  // Wait until we observe it drop, then recover, then reload for fresh state.
  const waitForRestart = () => {
    let sawDown = false
    let attempts = 0
    const tick = async () => {
      attempts++
      try {
        await api.auth.status()
        if (sawDown) { window.location.reload(); return }
      } catch {
        sawDown = true
      }
      if (attempts > 60) { setRestarting(false); return }
      window.setTimeout(tick, 1000)
    }
    window.setTimeout(tick, 1000)
  }

  const handleSave = async () => {
    if (!sudo) { toast(i18n.config.needSudo, 'destructive'); return }
    if (!Object.keys(dirty).length) return
    setSaving(true)
    try {
      const res = await api.pluginConfig.update(dirty)
      toast(i18n.config.saved)
      setDirty({})
      setIsDirty(false)
      if (res.restarting) {
        setRestarting(true)
        waitForRestart()
      }
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
  const autoRestart = Boolean(
    values['webui_auto_restart_on_save'] ?? schema['webui_auto_restart_on_save']?.default ?? true
  )

  // Resolve whether a field should be rendered disabled because its parent
  // toggle/select is off.
  const isParentOff = (key: string): boolean => {
    const parentKey = FIELD_DEPENDENCIES[key]
    if (!parentKey) return false
    const parentVal = values[parentKey]
    const parentSchema = schema[parentKey]
    if (parentSchema?.type === 'bool') return !parentVal
    if (parentKey === 'extraction_strategy') return parentVal !== 'semantic'
    if (parentKey === 'embedding_provider') return parentVal !== 'api' || !values['embedding_enabled']
    return false
  }

  const renderField = (key: string) => {
    const fieldDisabled = !sudo || saving || isParentOff(key)
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
  }

  // Visible field keys for a section under the current tier filter.
  const visibleKeys = (section: (typeof SECTIONS)[number]) =>
    section.keys.filter(k => schema[k] && passesLevel(k))

  const renderSectionCard = (section: (typeof SECTIONS)[number]) => {
    const fields = visibleKeys(section)
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
            {(() => {
              const sectionAny = section as any
              if (Array.isArray(sectionAny.groups)) {
                return sectionAny.groups.map((g: { label: string; hint?: string; keys: string[] }, gi: number) => {
                  const gFields = g.keys.filter(k => schema[k] && passesLevel(k))
                  if (!gFields.length) return null
                  return (
                    <div key={`grp-${gi}-${g.label}`} className="py-1 first:pt-0">
                      <div className="flex items-center gap-2 px-1 pt-3 pb-2 -mx-1">
                        <div className="h-px flex-1 bg-gradient-to-r from-primary/40 via-primary/15 to-transparent" />
                        <span className="text-xs font-semibold text-primary tracking-wide whitespace-nowrap">
                          {g.label}
                        </span>
                        {g.hint && (
                          <span className="text-[10px] text-muted-foreground/70 whitespace-nowrap">
                            · {g.hint}
                          </span>
                        )}
                        <div className="h-px flex-1 bg-gradient-to-l from-primary/40 via-primary/15 to-transparent" />
                      </div>
                      <div className="divide-y divide-muted/40">
                        {gFields.map(renderField)}
                      </div>
                    </div>
                  )
                })
              }
              return fields.map(renderField)
            })()}
          </CardContent>
          {section.id === 'relation' && <PersonaOwnershipManager embedded />}
        </Card>
      </div>
    )
  }

  // TOC: 2-level — categories with their visible sub-sections.
  const tocItems = useMemo(() => {
    return CATEGORIES.map(cat => {
      const children = cat.sectionIds
        .map(sid => sectionById[sid])
        .filter(s => s && s.keys.some(k => schema[k] && passesLevel(k)))
        .map(s => ({ id: s!.id, label: s!.label }))
      return { id: cat.id, label: cat.label, children }
    }).filter(c => c.children.length > 0)
  }, [CATEGORIES, sectionById, schema, passesLevel])

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

  return (
    <div className="flex w-full flex-1 flex-col min-w-0 animate-in fade-in slide-in-from-bottom-4 duration-500 ease-out fill-mode-both">
      <PageHeader
        variant="loom"
        loomIssue="ΡΥΘΜΙΣΗ"
        loomWindow={i18n.page.config.loomWindow}
        title={i18n.page.config.title}
        externalToolbar
      />

      {/* Sticky toolbar — outside PageHeader so it sticks within the document scroll */}
      <div className="sticky top-0 z-20 flex flex-wrap items-center gap-2 px-4 py-2 border-b bg-background/95 backdrop-blur-sm">
        <div className="flex items-center gap-2 flex-wrap">{actions}</div>
        {dirtyCount > 0 && (
          <div className="flex items-center gap-1.5 rounded-lg border border-primary/20 bg-primary/5 px-3 py-1.5 text-xs text-primary">
            <AlertTriangle className="size-3 shrink-0" />
            <span className="hidden sm:inline">{(i18n.config as any).unsavedHint}</span>
          </div>
        )}

        {/* Search box — filters every config field across all categories */}
        <div className="relative ml-auto w-full sm:w-56 order-last sm:order-none">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground/60" />
          <Input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder={(i18n.config as any).search.placeholder}
            className="h-8 pl-8 pr-7 text-xs bg-background"
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground/60 hover:text-foreground"
            >
              <X className="size-3.5" />
            </button>
          )}
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="h-8 gap-1.5 px-3 transition-all"
            onClick={() => setWizardOpen(true)}
          >
            <Wand2 className="size-3.5" />
            <span className="hidden sm:inline">{(i18n.config as any).wizard?.open ?? '快速设置'}</span>
          </Button>

          {/* 3-tier progressive disclosure */}
          <ToggleGroup
            type="single"
            value={configLevel}
            onValueChange={handleLevelChange}
            variant="outline"
            size="sm"
            className="gap-0"
          >
            <ToggleGroupItem value="basic" className="h-8 px-2.5 text-xs rounded-r-none">
              {(i18n.config as any).levels.basic}
            </ToggleGroupItem>
            <ToggleGroupItem value="advanced" className="h-8 px-2.5 text-xs rounded-none border-x-0">
              {(i18n.config as any).levels.advanced}
            </ToggleGroupItem>
            <ToggleGroupItem value="expert" className="h-8 px-2.5 text-xs rounded-l-none">
              {(i18n.config as any).levels.expert}
            </ToggleGroupItem>
          </ToggleGroup>

          <RefreshButton onClick={load} loading={loading} />
        </div>
      </div>

      <TooltipProvider delayDuration={0}>
      <div className="flex flex-1 justify-center gap-8 px-6 pb-24 pt-6">
        <div ref={scrollAreaRef} className="flex-1 max-w-3xl min-w-0 space-y-8">
          <div className="flex items-start gap-3 rounded-xl border border-primary/20 bg-primary/5 px-4 py-3.5 transition-all hover:bg-primary/10">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-primary" />
            <div className="space-y-1">
              <p className="text-sm font-medium text-primary leading-none">{i18n.config.restartHint}</p>
              <p className="text-xs text-primary/70 leading-relaxed">
                {autoRestart
                  ? (i18n.config as any).restartAutoHint
                  : (i18n.config as any).restartManualHint}
              </p>
            </div>
          </div>

          {configLevel !== 'expert' && !loading && !searchActive && (
            <div className="flex items-center gap-3 rounded-xl border border-muted-foreground/20 bg-muted/40 px-4 py-3 transition-all">
              <Info className="size-4 shrink-0 text-muted-foreground" />
              <p className="text-xs text-muted-foreground leading-relaxed">
                {(i18n.config as any).levels.hint}
              </p>
            </div>
          )}

          {loading ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3">
              <div className="size-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
              <p className="text-sm text-muted-foreground animate-pulse">{i18n.config.loading}</p>
            </div>
          ) : searchActive ? (
            /* ---- Search results: flat list with breadcrumbs ---- */
            <div className="space-y-4">
              <p className="text-xs text-muted-foreground">
                {(i18n.config as any).search.resultCount.replace('{count}', String(searchResults.length))}
              </p>
              {searchResults.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 gap-2 text-muted-foreground">
                  <Search className="size-6 opacity-40" />
                  <p className="text-sm">{(i18n.config as any).search.noResult}</p>
                </div>
              ) : (
                <Card className="border-muted/60 shadow-sm">
                  <CardContent className="divide-y divide-muted/50 pt-2 px-6">
                    {searchResults.map(r => (
                      <div key={r.key} className="py-1">
                        <p className="pt-2 text-[10px] font-medium uppercase tracking-wide text-muted-foreground/60">
                          {r.categoryLabel} / {r.sectionLabel}
                        </p>
                        {renderField(r.key)}
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}
            </div>
          ) : (
            /* ---- Normal view: 6 categories, each with its sub-section cards ---- */
            CATEGORIES.map(cat => {
              const cards = cat.sectionIds
                .map(sid => sectionById[sid])
                .filter((s): s is (typeof SECTIONS)[number] => !!s)
                .map(renderSectionCard)
                .filter(Boolean)
              if (!cards.length) return null
              return (
                <section key={cat.id} id={cat.id} className="scroll-mt-20 space-y-5">
                  <div className="flex items-center gap-3">
                    <h2 className="text-xl font-bold tracking-tight">{cat.label}</h2>
                    <div className="h-px flex-1 bg-gradient-to-r from-border to-transparent" />
                  </div>
                  {cards}
                </section>
              )
            })
          )}
        </div>

        {/* TOC — sticky, 2-level (categories → sub-sections) */}
        {!loading && !searchActive && (
          <aside className="hidden lg:block w-[220px] shrink-0">
            <div className="sticky top-6">
              <OnThisPage
                items={tocItems}
                activeId={activeSection}
                onItemClick={scrollTo}
                title={i18n.common.onThisPage}
              />
            </div>
          </aside>
        )}
      </div>
      </TooltipProvider>

      <QuickSetupWizard open={wizardOpen} onClose={() => setWizardOpen(false)} />

      {/* Full-screen overlay while the plugin reloads after an auto-restart save */}
      {restarting && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-4 bg-background/90 backdrop-blur-sm">
          <div className="size-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <div className="max-w-sm space-y-1.5 px-6 text-center">
            <p className="text-sm font-semibold text-foreground">{(i18n.config as any).restarting.title}</p>
            <p className="text-xs text-muted-foreground leading-relaxed">{(i18n.config as any).restarting.desc}</p>
          </div>
        </div>
      )}
    </div>
  )
}
