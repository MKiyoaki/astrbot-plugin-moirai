'use client'

import { createContext, useContext, useState, useCallback, useEffect, useRef, type ReactNode } from 'react'
import * as api from './api'

// ── Types ─────────────────────────────────────────────────────────────────
export interface ToastMessage { id: string; message: string; variant?: 'default' | 'destructive' }

interface AppState {
  // Auth
  authEnabled: boolean
  authenticated: boolean
  sudo: boolean
  passwordSet: boolean
  // Sudo guard settings (localStorage-backed)
  sudoGuardEnabled: boolean
  sudoGuardMinutes: number
  // Persona defaults (localStorage-backed)
  defaultPersonaConfidence: number
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
  refreshAuth: () => Promise<void>
  setSudo: (v: boolean) => void
  setAuthEnabled: (v: boolean) => void
  setAuthenticated: (v: boolean) => void
  setPasswordSet: (v: boolean) => void
  setSudoGuardEnabled: (v: boolean) => void
  setSudoGuardMinutes: (v: number) => void
  setDefaultPersonaConfidence: (v: number) => void
  refreshStats: () => Promise<void>
  setRawGraph: (g: api.GraphData) => void
  setRawEvents: (e: api.ApiEvent[]) => void
  toast: (msg: string, variant?: 'default' | 'destructive', ms?: number) => void
  dismissToast: (id: string) => void
}

const AppContext = createContext<(AppState & AppActions) | null>(null)

const DEFAULT_STATS: api.Stats = { personas: 0, events: 0, locked_count: 0, impressions: 0, groups: 0, version: '…' }

export function AppProvider({ children }: { children: ReactNode }) {
  const [authEnabled, setAuthEnabled] = useState(true)
  const [authenticated, setAuthenticated] = useState(false)
  const [sudo, setSudo] = useState(false)
  const [passwordSet, setPasswordSet] = useState(false)
  const [stats, setStats] = useState<api.Stats>(DEFAULT_STATS)
  const [rawGraph, setRawGraph] = useState<api.GraphData>({ nodes: [], edges: [] })
  const [rawEvents, setRawEvents] = useState<api.ApiEvent[]>([])
  const [toasts, setToasts] = useState<ToastMessage[]>([])

  // Sudo guard settings — persisted in localStorage
  const [sudoGuardEnabled, _setSudoGuardEnabled] = useState(() => {
    if (typeof window === 'undefined') return true
    const v = localStorage.getItem('em_sudo_guard_enabled')
    return v === null ? true : v === 'true'
  })
  const [sudoGuardMinutes, _setSudoGuardMinutes] = useState(() => {
    if (typeof window === 'undefined') return 30
    const v = localStorage.getItem('em_sudo_guard_minutes')
    return v ? parseInt(v, 10) : 30
  })

  const setSudoGuardEnabled = useCallback((v: boolean) => {
    _setSudoGuardEnabled(v)
    localStorage.setItem('em_sudo_guard_enabled', String(v))
  }, [])
  const setSudoGuardMinutes = useCallback((v: number) => {
    _setSudoGuardMinutes(v)
    localStorage.setItem('em_sudo_guard_minutes', String(v))
  }, [])

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

  // If sudo guard is disabled or minutes=0, always keep sudo=true when authenticated
  const effectiveSudoAlways = !sudoGuardEnabled || sudoGuardMinutes === 0

  const refreshAuth = useCallback(async () => {
    try {
      const s = await api.auth.status()
      setAuthEnabled(s.auth_enabled)
      setAuthenticated(s.authenticated)
      setPasswordSet(s.password_set)
      if (effectiveSudoAlways && s.authenticated) {
        setSudo(true)
      } else {
        setSudo(s.sudo)
      }
    } catch {}
  }, [effectiveSudoAlways])

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

  // Poll auth status every 30s to track sudo expiry
  useEffect(() => {
    if (!authenticated || effectiveSudoAlways) return
    const interval = setInterval(async () => {
      try {
        const s = await api.auth.status()
        setSudo(s.sudo)
      } catch {}
    }, 30_000)
    return () => clearInterval(interval)
  }, [authenticated, effectiveSudoAlways])

  const ctx: AppState & AppActions = {
    authEnabled, authenticated, sudo, passwordSet,
    sudoGuardEnabled, sudoGuardMinutes,
    defaultPersonaConfidence,
    stats, rawGraph, rawEvents, toasts,
    refreshAuth,
    setSudo,
    setAuthEnabled,
    setAuthenticated,
    setPasswordSet,
    setSudoGuardEnabled,
    setSudoGuardMinutes,
    setDefaultPersonaConfidence,
    refreshStats,
    setRawGraph,
    setRawEvents,
    toast,
    dismissToast,
  }

  return <AppContext.Provider value={ctx}>{children}</AppContext.Provider>
}

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used within AppProvider')
  return ctx
}
