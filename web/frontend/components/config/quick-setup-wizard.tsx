'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { ShieldCheck, FlaskConical, Check, Loader2 } from 'lucide-react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { useApp } from '@/lib/store'
import * as api from '@/lib/api'
import { cn } from '@/lib/utils'

// Numeric / strategy tuning per preset. Feature on/off switches come from the
// feature step instead, so the two never conflict.
type PresetId = 'chatOnly' | 'balanced' | 'full'
const PRESETS: Record<PresetId, Record<string, unknown>> = {
  chatOnly: {
    embedding_provider: 'local',
    llm_concurrency: 1,
    extraction_strategy: 'llm',
    retrieval_top_k: 3,
    retrieval_token_budget: 600,
    boundary_topic_drift_enabled: false,
  },
  balanced: {
    embedding_provider: 'local',
    llm_concurrency: 2,
    extraction_strategy: 'llm',
    retrieval_top_k: 3,
    retrieval_token_budget: 800,
    boundary_topic_drift_enabled: true,
  },
  full: {
    embedding_provider: 'local',
    llm_concurrency: 3,
    extraction_strategy: 'semantic',
    retrieval_top_k: 5,
    retrieval_token_budget: 1200,
    retrieval_weighted_random: true,
    boundary_topic_drift_enabled: true,
  },
}

const FEATURE_KEYS = [
  'embedding_enabled',
  'relation_enabled',
  'summary_enabled',
  'impression_injection_enabled',
  'persona_influenced_summary',
  'soul_enabled',
  'webui_enabled',
] as const
type FeatureKey = (typeof FEATURE_KEYS)[number]

const DEFAULT_FEATURES: Record<FeatureKey, boolean> = {
  embedding_enabled: true,
  relation_enabled: true,
  summary_enabled: true,
  impression_injection_enabled: true,
  persona_influenced_summary: true,
  soul_enabled: false,
  webui_enabled: true,
}

// Features that change what the bot sends to the LLM / how it is visualised.
const PROMPT_FEATURES: FeatureKey[] = [
  'impression_injection_enabled', 'persona_influenced_summary', 'soul_enabled', 'webui_enabled',
]
const CORE_FEATURES: FeatureKey[] = ['embedding_enabled', 'relation_enabled', 'summary_enabled']

const TOTAL_STEPS = 4

export function QuickSetupWizard({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter()
  const { i18n, sudo, setSudo, setQuickSetupDone, toast } = useApp()
  const w = (i18n.config as any).wizard

  const [step, setStep] = useState(0)
  const [sudoPw, setSudoPw] = useState('')
  const [sudoLoading, setSudoLoading] = useState(false)
  const [features, setFeatures] = useState<Record<FeatureKey, boolean>>(DEFAULT_FEATURES)
  const [preset, setPreset] = useState<PresetId>('balanced')
  const [applying, setApplying] = useState(false)
  const [restarting, setRestarting] = useState(false)

  // After an auto-restart save: wait for the WebUI to drop then recover,
  // then land on the config page with fresh state.
  const waitForRestart = () => {
    let sawDown = false
    let attempts = 0
    const tick = async () => {
      attempts++
      try {
        await api.auth.status()
        if (sawDown) { window.location.assign('/config'); return }
      } catch {
        sawDown = true
      }
      if (attempts > 60) { window.location.assign('/config'); return }
      window.setTimeout(tick, 1000)
    }
    window.setTimeout(tick, 1000)
  }

  // Entering the wizard: jump straight past the sudo step if already elevated.
  useEffect(() => {
    if (open) {
      setStep(sudo ? 1 : 0)
      setSudoPw('')
      setFeatures(DEFAULT_FEATURES)
      setPreset('balanced')
    }
  }, [open, sudo])

  const enterSudo = async () => {
    setSudoLoading(true)
    try {
      await api.auth.sudo(sudoPw)
      setSudo(true)
      toast(i18n.auth.enterSudo)
      setStep(1)
    } catch (e: unknown) {
      toast(`${i18n.auth.sudoMode}${i18n.common.error}：${(e as api.ApiError).body || (e as api.ApiError).status}`, 'destructive', 4000)
    } finally {
      setSudoLoading(false)
    }
  }

  const apply = async () => {
    setApplying(true)
    try {
      const payload: Record<string, unknown> = { ...PRESETS[preset], ...features }
      const res = await api.pluginConfig.update(payload)
      setQuickSetupDone(true)
      toast(w.applied)
      if (res.restarting) {
        // Keep the dialog up showing a restart notice; reload when back.
        setRestarting(true)
        waitForRestart()
      } else {
        onClose()
        router.push('/config')
      }
    } catch (e: unknown) {
      toast(`${w.applyError}：${(e as api.ApiError).body || (e as api.ApiError).status}`, 'destructive', 4000)
    } finally {
      setApplying(false)
    }
  }

  const featLabel = (k: FeatureKey) => w.feat[k] ?? { label: k, desc: '' }

  const renderFeatureRow = (k: FeatureKey) => {
    const meta = featLabel(k)
    return (
      <div key={k} className="flex items-start justify-between gap-4 py-2.5">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-medium">{meta.label}</span>
            {k === 'soul_enabled' && (
              <Badge variant="outline" className="h-4 gap-0.5 px-1 text-[9px] border-amber-500/40 text-amber-600 dark:text-amber-400">
                <FlaskConical className="size-2.5" />
                {(i18n.config as any).experimental}
              </Badge>
            )}
          </div>
          <p className="text-xs text-muted-foreground leading-normal">{meta.desc}</p>
        </div>
        <Switch
          checked={features[k]}
          onCheckedChange={v => setFeatures(prev => ({ ...prev, [k]: Boolean(v) }))}
          className="data-[state=checked]:bg-primary mt-0.5"
        />
      </div>
    )
  }

  return (
    <Dialog open={open} onOpenChange={o => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-[520px] max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{w.title}</DialogTitle>
          <DialogDescription>
            {w.stepOf.replace('{n}', String(step + 1)).replace('{total}', String(TOTAL_STEPS))}
          </DialogDescription>
        </DialogHeader>

        {/* Restarting — shown after an auto-restart save */}
        {restarting && (
          <div className="flex flex-col items-center justify-center gap-4 py-10">
            <div className="size-7 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            <div className="max-w-sm space-y-1.5 px-4 text-center">
              <p className="text-sm font-semibold">{(i18n.config as any).restarting.title}</p>
              <p className="text-xs text-muted-foreground leading-relaxed">{(i18n.config as any).restarting.desc}</p>
            </div>
          </div>
        )}

        {/* Step 0 — Sudo */}
        {!restarting && step === 0 && (
          <div className="space-y-3 py-2">
            <div className="flex items-start gap-2.5 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2.5">
              <ShieldCheck className="mt-0.5 size-4 shrink-0 text-primary" />
              <p className="text-xs text-muted-foreground leading-relaxed">{w.sudoDesc}</p>
            </div>
            {sudo ? (
              <p className="flex items-center gap-1.5 text-sm text-primary">
                <Check className="size-4" /> {w.sudoActive}
              </p>
            ) : (
              <div className="grid gap-2">
                <Label htmlFor="wizard-sudo-pw">{i18n.auth.password}</Label>
                <Input
                  id="wizard-sudo-pw"
                  type="password"
                  autoFocus
                  value={sudoPw}
                  onChange={e => setSudoPw(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && sudoPw) enterSudo() }}
                />
              </div>
            )}
          </div>
        )}

        {/* Step 1 — Feature selection */}
        {step === 1 && (
          <div className="space-y-3 py-1">
            <p className="text-xs text-muted-foreground">{w.featuresDesc}</p>
            <div className="divide-y divide-muted/50">
              {CORE_FEATURES.map(renderFeatureRow)}
            </div>
            <p className="pt-1 text-xs font-semibold text-primary">{w.featAdvanced}</p>
            <div className="divide-y divide-muted/50">
              {PROMPT_FEATURES.map(renderFeatureRow)}
            </div>
          </div>
        )}

        {/* Step 2 — Preset pack */}
        {step === 2 && (
          <div className="space-y-2 py-1">
            <p className="text-xs text-muted-foreground">{w.presetDesc}</p>
            {(['chatOnly', 'balanced', 'full'] as PresetId[]).map(p => {
              const meta = w.presets[p]
              const active = preset === p
              return (
                <button
                  key={p}
                  onClick={() => setPreset(p)}
                  className={cn(
                    'w-full rounded-lg border px-3 py-2.5 text-left transition-all',
                    active
                      ? 'border-primary bg-primary/5 ring-1 ring-primary/30'
                      : 'border-muted hover:border-primary/40'
                  )}
                >
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm font-medium">{meta.label}</span>
                    {active && <Check className="size-3.5 text-primary" />}
                  </div>
                  <p className="text-xs text-muted-foreground leading-normal">{meta.desc}</p>
                </button>
              )
            })}
          </div>
        )}

        {/* Step 3 — Review & apply */}
        {!restarting && step === 3 && (
          <div className="space-y-3 py-1">
            <p className="text-xs text-muted-foreground">{w.reviewDesc}</p>
            <div className="rounded-lg border border-muted bg-muted/30 px-3 py-2.5 space-y-1.5">
              <p className="text-xs font-semibold">{w.presets[preset].label}</p>
              <div className="flex flex-wrap gap-1">
                {FEATURE_KEYS.filter(k => features[k]).map(k => (
                  <Badge key={k} variant="secondary" className="text-[10px]">
                    {featLabel(k).label}
                  </Badge>
                ))}
              </div>
            </div>
          </div>
        )}

        {!restarting && (
        <DialogFooter className="gap-2 sm:gap-2">
          {step > (sudo ? 1 : 0) && (
            <Button variant="outline" onClick={() => setStep(step - 1)} disabled={applying}>
              {w.back}
            </Button>
          )}
          {step === 0 && (
            <Button onClick={enterSudo} disabled={sudoLoading || (!sudo && !sudoPw)}>
              {sudoLoading ? <Loader2 className="size-4 animate-spin" /> : null}
              {sudo ? w.next : w.sudoEnter}
            </Button>
          )}
          {step > 0 && step < 3 && (
            <Button onClick={() => setStep(step + 1)}>{w.next}</Button>
          )}
          {step === 3 && (
            <Button onClick={apply} disabled={applying || !sudo}>
              {applying ? <Loader2 className="size-4 animate-spin" /> : null}
              {w.finish}
            </Button>
          )}
        </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  )
}
