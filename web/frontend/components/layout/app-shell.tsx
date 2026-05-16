'use client'

import { useCallback, useEffect, useState, type ReactNode } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { Activity, Search, Settings } from 'lucide-react'
import { SidebarProvider, SidebarInset } from '@/components/ui/sidebar'
import { AppSidebar } from './app-sidebar'
import { Toaster } from '@/components/shared/toaster'
import { LoginScreen } from '@/components/shared/login-screen'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { useApp } from '@/lib/store'
import { getStored } from '@/lib/safe-storage'
import { routeIsActive } from '@/lib/navigation'
import { cn } from '@/lib/utils'

const SHADCN_THEMES = [
  'zinc',
  'red', 'rose', 'orange', 'green', 'blue', 'yellow', 'violet'
]

/** Bottom navigation tabs shown on mobile (< md breakpoint) */
const MOBILE_TABS = [
  { href: '/events',   icon: Activity, labelZh: '织机', labelEn: 'Loom',   labelJa: '織機' },
  { href: '/recall',   icon: Search,   labelZh: '检索', labelEn: 'Recall', labelJa: '検索' },
  { href: '/settings', icon: Settings, labelZh: '设置', labelEn: 'Me',     labelJa: '設定' },
]

function MobileTabBar() {
  const pathname = usePathname()
  const router = useRouter()
  const app = useApp()
  const { lang, i18n } = app

  const [showExitDialog, setShowExitDialog] = useState(false)
  const [pendingUrl, setPendingUrl] = useState('')

  const label = (tab: typeof MOBILE_TABS[number]) => {
    if (lang === 'en') return tab.labelEn
    if (lang === 'ja') return tab.labelJa
    return tab.labelZh
  }

  const handleNavClick = (e: React.MouseEvent, href: string) => {
    if (app.isDirty) {
      e.preventDefault()
      setPendingUrl(href)
      setShowExitDialog(true)
    }
  }

  const confirmExit = () => {
    app.setIsDirty(false)
    setShowExitDialog(false)
    router.push(pendingUrl)
  }

  return (
    <>
    <nav
      data-testid="mobile-tab-bar"
      className="md:hidden fixed bottom-0 left-0 right-0 z-50 flex items-stretch border-t bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80"
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      {MOBILE_TABS.map(tab => {
        const active = routeIsActive(pathname, tab.href)
        return (
          <Link
            key={tab.href}
            href={tab.href}
            onClick={e => handleNavClick(e, tab.href)}
            className={cn(
              'flex flex-1 flex-col items-center justify-center gap-0.5 py-2 text-[10px] font-mono uppercase tracking-[0.12em] transition-colors',
              active ? 'text-primary' : 'text-muted-foreground hover:text-foreground'
            )}
          >
            <tab.icon className={cn('size-5', active && 'stroke-[2.2]')} />
            <span>{label(tab)}</span>
          </Link>
        )
      })}
    </nav>

    <AlertDialog open={showExitDialog} onOpenChange={setShowExitDialog}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{i18n.summary.regenerateConfirmTitle}</AlertDialogTitle>
          <AlertDialogDescription>
            {lang === 'zh' ? '您有未保存的更改。确定要离开吗？' : lang === 'ja' ? '未保存の変更があります。退出してもよろしいですか？' : 'You have unsaved changes. Are you sure you want to leave?'}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{i18n.common.cancel}</AlertDialogCancel>
          <AlertDialogAction onClick={confirmExit}>{i18n.common.confirm}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
    </>
  )
}

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
      {/* Sidebar is hidden on mobile — navigation handled by MobileTabBar */}
      <div className="hidden md:contents">
        <AppSidebar />
      </div>
      <SidebarInset>
        {/* Extra bottom padding on mobile so content clears the tab bar (~56px) */}
        <div className="flex flex-col h-full md:h-auto pb-14 md:pb-0">
          {children}
        </div>
      </SidebarInset>
      <MobileTabBar />
      <Toaster />
    </SidebarProvider>
  )
}

export function AppShell({ children }: { children: ReactNode }) {
  return <Shell>{children}</Shell>
}
