'use client'

import { useEffect, type ReactNode } from 'react'
import { SidebarProvider, SidebarInset } from '@/components/ui/sidebar'
import { AppSidebar } from './app-sidebar'
import { LoginScreen } from '@/components/shared/login-screen'
import { Toaster } from '@/components/shared/toaster'
import { useApp } from '@/lib/store'

const SHADCN_THEMES = [
  'zinc', 
  'red', 'rose', 'orange', 'green', 'blue', 'yellow', 'violet'
]

function Shell({ children }: { children: ReactNode }) {
  const app = useApp()

  useEffect(() => {
    const scheme = localStorage.getItem('em_color_scheme') || 'zinc'
    const root = document.documentElement
    
    root.classList.remove(...SHADCN_THEMES.map(t => `theme-${t}`))
    
    if (scheme !== 'zinc') {
      root.classList.add(`theme-${scheme}`)
    }

    app.refreshAuth().then(() => {
      if (app.authenticated || !app.authEnabled) {
        app.refreshStats()
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (app.authEnabled && !app.authenticated) {
    return (
      <>
        <LoginScreen
          onSuccess={() => app.refreshStats()}
        />
        <Toaster />
      </>
    )
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