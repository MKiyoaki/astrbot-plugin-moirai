'use client'

import { useEffect, type ReactNode } from 'react'
import { SidebarProvider, SidebarInset } from '@/components/ui/sidebar'
import { AppSidebar } from './app-sidebar'
import { Toaster } from '@/components/shared/toaster'
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

    // Auth is managed by AstrBot — just load stats on mount.
    app.refreshStats()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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
