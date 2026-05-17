'use client'

import { createContext, useContext, useState, useCallback, useEffect, useRef, useMemo, type ReactNode } from 'react'
import * as api from './api'
import * as i18n_lib from './i18n'
import { getStored, setStored } from './safe-storage'

// ── Types ─────────────────────────────────────────────────────────────────
export interface ToastMessage { id: string; message: string; variant?: 'default' | 'destructive' }

export type PersonaViewMode = 'remember' | 'all' | 'force_pick'

export interface PersonaConfig {
  isolationEnabled: boolean       // persona_isolation_enabled master switch
  legacyVisible: boolean          // persona_isolation_legacy_visible (info only on frontend)
  defaultViewMode: PersonaViewMode // persona_default_view_mode
  loaded: boolean                  // false until /api/config fetched
}

interface AppState {
  sudo: boolean
  authEnabled: boolean
  authenticated: boolean
  authLoading: boolean
  preAuthVersion: string
  // Persona defaults (localStorage-backed)
  defaultPersonaConfidence: number
  // Bot persona scope (localStorage-backed)
  currentPersonaName: string | null   // null only when scopeMode='all'
  scopeMode: 'single' | 'all'
  firstLaunchDone: boolean
  // Persona-related plugin config values (fetched from /api/config)
  personaConfig: PersonaConfig
  // i18n
  lang: 'zh' | 'en' | 'ja'
  i18n: i18n_lib.I18n
  // Stats
  stats: api.Stats
  // Graph data
  rawGraph: api.GraphData
  // Events data
  rawEvents: api.ApiEvent[]
  // Dirty state for navigation guard
  isDirty: boolean
  // Toast
  toasts: ToastMessage[]
}

interface AppActions {
  setSudo: (v: boolean) => void
  setAuthenticated: (v: boolean) => void
  setDefaultPersonaConfidence: (v: number) => void
  setCurrentPersona: (name: string | null, mode: 'single' | 'all') => void
  setFirstLaunchDone: (done: boolean) => void
  setLang: (l: 'zh' | 'en' | 'ja') => void
  refreshStats: () => Promise<void>
  setRawGraph: (g: api.GraphData) => void
  setRawEvents: (e: api.ApiEvent[]) => void
  setIsDirty: (v: boolean) => void
  toast: (msg: string, variant?: 'default' | 'destructive', ms?: number) => void
  dismissToast: (id: string) => void
}

const AppContext = createContext<(AppState & AppActions) | null>(null)

const DEFAULT_STATS: api.Stats = { personas: 0, events: 0, locked_count: 0, impressions: 0, summaries: 0, groups: 0, version: '…' }

export function AppProvider({ children }: { children: ReactNode }) {
  const [sudo, setSudo] = useState(false)
  const [authEnabled, setAuthEnabled] = useState(true)
  const [authenticated, setAuthenticated] = useState(false)
  const [authLoading, setAuthLoading] = useState(true)
  const [preAuthVersion, setPreAuthVersion] = useState('…')

  useEffect(() => {
    api.auth.status().then(s => {
      setAuthEnabled(s.auth_enabled)
      setAuthenticated(!s.auth_enabled || s.authenticated)
      setSudo(!s.auth_enabled || s.sudo)
      if (s.version) setPreAuthVersion(s.version)
    }).catch(() => {
      setAuthEnabled(false)
      setAuthenticated(true)
      setSudo(true)
    }).finally(() => {
      setAuthLoading(false)
    })
  }, [])

  const [stats, setStats] = useState<api.Stats>(DEFAULT_STATS)
  const [rawGraph, setRawGraph] = useState<api.GraphData>({ nodes: [], edges: [] })
  const [rawEvents, setRawEvents] = useState<api.ApiEvent[]>([])
  const [isDirty, setIsDirty] = useState(false)
  const [toasts, setToasts] = useState<ToastMessage[]>([])

  // i18n - Initialise with 'zh' to match SSR default
  const [lang, _setLang] = useState<'zh' | 'en' | 'ja'>('zh')

  useEffect(() => {
    const v = getStored('em_lang')
    if (v === 'en' || v === 'zh' || v === 'ja') {
      _setLang(v)
    }
  }, [])

  const setLang = useCallback((l: 'zh' | 'en' | 'ja') => {
    _setLang(l)
    setStored('em_lang', l)
  }, [])

  const i18n = useMemo(() => {
    if (lang === 'en') return i18n_lib.en
    if (lang === 'ja') return i18n_lib.ja
    return i18n_lib.zh
  }, [lang])

  // Default persona confidence — persisted in localStorage
  const [defaultPersonaConfidence, _setDefaultPersonaConfidence] = useState(() => {
    if (typeof window === 'undefined') return 0.5
    const v = getStored('em_default_persona_confidence')
    return v ? parseFloat(v) : 0.5
  })

  const setDefaultPersonaConfidence = useCallback((v: number) => {
    _setDefaultPersonaConfidence(v)
    setStored('em_default_persona_confidence', String(v))
  }, [])

  // Bot persona scope — persisted in localStorage
  const [currentPersonaName, _setCurrentPersonaName] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null
    const v = getStored('em_current_persona_name')
    return v || null
  })
  const [scopeMode, _setScopeMode] = useState<'single' | 'all'>(() => {
    if (typeof window === 'undefined') return 'all'
    return (getStored('em_persona_scope_mode') as 'single' | 'all') || 'all'
  })
  const [firstLaunchDone, _setFirstLaunchDone] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false
    return getStored('em_first_launch_done') === '1'
  })

  // Persona-related plugin config — fetched after auth resolves
  const [personaConfig, setPersonaConfig] = useState<PersonaConfig>({
    isolationEnabled: true,
    legacyVisible: true,
    defaultViewMode: 'remember',
    loaded: false,
  })

  useEffect(() => {
    if (!authenticated || authLoading) return
    let cancelled = false
    api.pluginConfig.get().then(r => {
      if (cancelled) return
      const v = r.values || {}
      const mode = v.persona_default_view_mode
      const validMode: PersonaViewMode =
        mode === 'all' || mode === 'force_pick' ? mode : 'remember'
      setPersonaConfig({
        isolationEnabled: v.persona_isolation_enabled !== false,
        legacyVisible: v.persona_isolation_legacy_visible !== false,
        defaultViewMode: validMode,
        loaded: true,
      })
    }).catch(() => {
      // Fall back to defaults on error — still mark loaded so picker can fire
      if (!cancelled) setPersonaConfig(s => ({ ...s, loaded: true }))
    })
    return () => { cancelled = true }
  }, [authenticated, authLoading])

  const setCurrentPersona = useCallback((name: string | null, mode: 'single' | 'all') => {
    _setCurrentPersonaName(name)
    _setScopeMode(mode)
    setStored('em_current_persona_name', name ?? '')
    setStored('em_persona_scope_mode', mode)
  }, [])

  const setFirstLaunchDone = useCallback((done: boolean) => {
    _setFirstLaunchDone(done)
    setStored('em_first_launch_done', done ? '1' : '')
  }, [])

  const refreshStats = useCallback(async () => {
    try {
      const s = await api.stats.get()
      setStats(s)
    } catch {}
  }, [])

  const toastTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())

  const toast = useCallback((msg: string, variant: 'default' | 'destructive' = 'default', ms = 2800) => {
    const id = Math.random().toString(36).slice(2)
    setToasts(prev => [...prev, { id, message: msg, variant }])
    const timer = setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id))
      toastTimers.current.delete(id)
    }, ms)
    toastTimers.current.set(id, timer)
  }, [])

  const dismissToast = useCallback((id: string) => {
    const timer = toastTimers.current.get(id)
    if (timer) { clearTimeout(timer); toastTimers.current.delete(id) }
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  // Apply saved color scheme on mount
  useEffect(() => {
    const saved = getStored('em_color_scheme') ?? 'moirai'
    const classList = document.documentElement.classList
    Array.from(classList).filter(c => c.startsWith('theme-')).forEach(c => classList.remove(c))
    if (saved !== 'zinc') {
      classList.add(`theme-${saved}`)
    }
  }, [])

  const ctx = useMemo<AppState & AppActions>(() => ({
    sudo,
    authEnabled,
    authenticated,
    authLoading,
    preAuthVersion,
    setSudo,
    setAuthenticated,
    defaultPersonaConfidence,
    currentPersonaName,
    scopeMode,
    firstLaunchDone,
    personaConfig,
    lang, i18n,
    stats, rawGraph, rawEvents, isDirty, toasts,
    setDefaultPersonaConfidence,
    setCurrentPersona,
    setFirstLaunchDone,
    setLang,
    refreshStats,
    setRawGraph,
    setRawEvents,
    setIsDirty,
    toast,
    dismissToast,
  }), [
    sudo, authEnabled, authenticated, authLoading, preAuthVersion,
    defaultPersonaConfidence,
    currentPersonaName, scopeMode, firstLaunchDone,
    personaConfig,
    lang, i18n,
    stats, rawGraph, rawEvents, isDirty, toasts,
    refreshStats, setDefaultPersonaConfidence, setCurrentPersona, setFirstLaunchDone,
    setLang, setIsDirty, toast, dismissToast
  ])

  return <AppContext.Provider value={ctx}>{children}</AppContext.Provider>
}

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used within AppProvider')
  return ctx
}
