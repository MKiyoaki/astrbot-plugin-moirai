'use client'

import { useEffect, type ReactNode } from 'react'
import { SidebarProvider, SidebarInset } from '@/components/ui/sidebar'
import { AppSidebar } from './app-sidebar'
import { LoginScreen } from '@/components/shared/login-screen'
import { Toaster } from '@/components/shared/toaster'
import { useApp } from '@/lib/store'

function Shell({ children }: { children: ReactNode }) {
  const app = useApp()

  useEffect(() => {
    // Boot: refresh auth + stats
    app.refreshAuth().then(() => {
      if (app.authenticated || !app.authEnabled) {
        app.refreshStats()
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Show login if auth enabled and not authenticated
  if (app.authEnabled && !app.authenticated) {
    return (
      <>
        <LoginScreen
          setupMode={!app.passwordSet}
          onSuccess={() => app.refreshStats()}
        />
        <Toaster />
      </>
    )
  }

  return (
    <SidebarProvider>
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
