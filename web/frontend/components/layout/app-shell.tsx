'use client'

import { useCallback, useEffect, type ReactNode } from 'react'
import { SidebarProvider, SidebarInset } from '@/components/ui/sidebar'
import { AppSidebar } from './app-sidebar'
import { Toaster } from '@/components/shared/toaster'
import { LoginScreen } from '@/components/shared/login-screen'
import { useApp } from '@/lib/store'
import { getStored } from '@/lib/safe-storage'

const SHADCN_THEMES = [
  'zinc',
  'red', 'rose', 'orange', 'green', 'blue', 'yellow', 'violet'
]

function Shell({ children }: { children: ReactNode }) {
  const app = useApp()

  useEffect(() => {
    const scheme = getStored('em_color_scheme', 'zinc') || 'zinc'
    const root = document.documentElement

    root.classList.remove(...SHADCN_THEMES.map(t => `theme-${t}`))

    if (scheme !== 'zinc') {
      root.classList.add(`theme-${scheme}`)
    }
  }, [])

  useEffect(() => {
    if (app.authenticated) {
      app.refreshStats()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [app.authenticated])

  const handleLoginSuccess = useCallback(() => {
    app.setAuthenticated(true)
    app.setSudo(false)
    // Re-fetch auth status to sync sudo state
    import('@/lib/api').then(({ auth }) =>
      auth.status().then(s => {
        app.setSudo(!s.auth_enabled || s.sudo)
      }).catch(() => {})
    )
  }, [app])

  // Wait for auth status to resolve before making any decision.
  if (app.authLoading) return null

  // Show login screen when auth is enabled and not yet authenticated.
  if (app.authEnabled && !app.authenticated) {
    return <LoginScreen onSuccess={handleLoginSuccess} />
  }

  return (
    <SidebarProvider defaultOpen={true}>
      <AppSidebar />
      <SidebarInset>
        {children}
      </SidebarInset>
      <Toaster />
    </SidebarProvider>
  )
}

export function AppShell({ children }: { children: ReactNode }) {
  return <Shell>{children}</Shell>
}
