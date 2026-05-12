'use client'

import { createContext, useContext, useState, useCallback, useEffect, useRef, useMemo, type ReactNode } from 'react'
import * as api from './api'
import * as i18n_lib from './i18n'

// ── Types ─────────────────────────────────────────────────────────────────
export interface ToastMessage { id: string; message: string; variant?: 'default' | 'destructive' }

interface AppState {
  // Auth — AstrBot manages authentication; sudo is always true inside the plugin page.
  sudo: boolean
  // Persona defaults (localStorage-backed)
  defaultPersonaConfidence: number
  // i18n
  lang: 'zh' | 'en' | 'ja'
  i18n: i18n_lib.I18n
  // Stats
  stats: api.Stats
  // Graph data
  rawGraph: api.GraphData
  // Events data
  rawEvents: api.ApiEvent[]
  // Toast
  toasts: ToastMessage[]
}

interface AppActions {
  setDefaultPersonaConfidence: (v: number) => void
  setLang: (l: 'zh' | 'en' | 'ja') => void
  refreshStats: () => Promise<void>
  setRawGraph: (g: api.GraphData) => void
  setRawEvents: (e: api.ApiEvent[]) => void
  toast: (msg: string, variant?: 'default' | 'destructive', ms?: number) => void
  dismissToast: (id: string) => void
}

const AppContext = createContext<(AppState & AppActions) | null>(null)

const DEFAULT_STATS: api.Stats = { personas: 0, events: 0, locked_count: 0, impressions: 0, summaries: 0, groups: 0, version: '…' }

export function AppProvider({ children }: { children: ReactNode }) {
  // Auth is managed by AstrBot — sudo is always true inside the plugin page.
  const sudo = true

  const [stats, setStats] = useState<api.Stats>(DEFAULT_STATS)
  const [rawGraph, setRawGraph] = useState<api.GraphData>({ nodes: [], edges: [] })
  const [rawEvents, setRawEvents] = useState<api.ApiEvent[]>([])
  const [toasts, setToasts] = useState<ToastMessage[]>([])

  // i18n - Initialise with 'zh' to match SSR default
  const [lang, _setLang] = useState<'zh' | 'en' | 'ja'>('zh')

  useEffect(() => {
    const v = localStorage.getItem('em_lang')
    if (v === 'en' || v === 'zh' || v === 'ja') {
      _setLang(v)
    }
  }, [])

  const setLang = useCallback((l: 'zh' | 'en' | 'ja') => {
    _setLang(l)
    localStorage.setItem('em_lang', l)
  }, [])

  const i18n = useMemo(() => {
    if (lang === 'en') return i18n_lib.en
    if (lang === 'ja') return i18n_lib.ja
    return i18n_lib.zh
  }, [lang])

  // Default persona confidence — persisted in localStorage
  const [defaultPersonaConfidence, _setDefaultPersonaConfidence] = useState(() => {
    if (typeof window === 'undefined') return 0.5
    const v = localStorage.getItem('em_default_persona_confidence')
    return v ? parseFloat(v) : 0.5
  })

  const setDefaultPersonaConfidence = useCallback((v: number) => {
    _setDefaultPersonaConfidence(v)
    localStorage.setItem('em_default_persona_confidence', String(v))
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
    const saved = localStorage.getItem('em_color_scheme')
    if (saved && saved !== 'zinc') {
      document.documentElement.dataset.scheme = saved
    }
  }, [])

  const ctx = useMemo<AppState & AppActions>(() => ({
    sudo,
    defaultPersonaConfidence,
    lang, i18n,
    stats, rawGraph, rawEvents, toasts,
    setDefaultPersonaConfidence,
    setLang,
    refreshStats,
    setRawGraph,
    setRawEvents,
    toast,
    dismissToast,
  }), [
    defaultPersonaConfidence,
    lang, i18n,
    stats, rawGraph, rawEvents, toasts,
    refreshStats, setDefaultPersonaConfidence, setLang, toast, dismissToast
  ])

  return <AppContext.Provider value={ctx}>{children}</AppContext.Provider>
}

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used within AppProvider')
  return ctx
}
