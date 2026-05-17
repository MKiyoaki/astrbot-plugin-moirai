'use client'

import { useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useTheme } from 'next-themes'
import {
  Activity, Share2, BookOpen, Search, Database, Settings, SlidersHorizontal,
  Moon, Sun, BarChart3, Lock, Unlock, LogOut,
} from 'lucide-react'
import {
  Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent,
  SidebarGroupLabel, SidebarHeader, SidebarMenu, SidebarMenuButton,
  SidebarMenuItem, SidebarSeparator,
} from '@/components/ui/sidebar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { useApp } from '@/lib/store'
import * as api from '@/lib/api'
import { routeIsActive } from '@/lib/navigation'

const NAV_VISUALIZATION = [
  { href: '/events',  icon: Activity,          labelKey: 'events' as const },
  { href: '/graph',   icon: Share2,             labelKey: 'graph' as const },
  { href: '/summary', icon: BookOpen,           labelKey: 'summary' as const },
]
const NAV_TOOLS = [
  { href: '/recall',  icon: Search,             labelKey: 'recall' as const },
  { href: '/stats',   icon: BarChart3,          labelKey: 'stats' as const },
]
const NAV_ADMIN = [
  { href: '/library', icon: Database,           labelKey: 'library' as const },
  { href: '/config',  icon: SlidersHorizontal,  labelKey: 'config' as const },
]

function EngineStatusBadge() {
  const { i18n, stats } = useApp()
  const sessions = stats?.active_sessions ?? []
  const triggerRounds = stats?.summary_trigger_rounds ?? 30

  const hasActive = sessions.length > 0
  const nearingTrigger = hasActive && sessions.some(s => s.current_rounds / triggerRounds >= 0.9)

  const label = !hasActive
    ? i18n.landing.engineIdle
    : nearingTrigger
      ? i18n.landing.engineSoonSummarize
      : i18n.landing.engineActive

  return (
    <div className="flex items-center gap-2 px-3 py-2">
      <span className="relative flex h-1.5 w-1.5 shrink-0">
        {hasActive && (
          <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${nearingTrigger ? 'bg-primary' : 'bg-green-400'}`} />
        )}
        <span className={`relative inline-flex rounded-full h-1.5 w-1.5 ${hasActive ? (nearingTrigger ? 'bg-primary animate-pulse' : 'bg-green-500') : 'bg-muted-foreground/40'}`} />
      </span>
      <span className="group-data-[collapsible=icon]:hidden truncate text-[9px] font-mono uppercase tracking-[0.18em] text-muted-foreground/60">
        {label}
      </span>
    </div>
  )
}

export function AppSidebar() {
  const pathname = usePathname()
  const router = useRouter()
  const app = useApp()
  const { i18n, lang } = app

  const [sudoLoading, setSudoLoading] = useState(false)
  const [sudoDialogOpen, setSudoDialogOpen] = useState(false)
  const [sudoPassword, setSudoPassword] = useState('')

  const [showExitDialog, setShowExitDialog] = useState(false)
  const [pendingUrl, setPendingUrl] = useState('')

  const effectiveSudoAlways = !app.authEnabled

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

  const handleSudoClick = async () => {
    if (app.sudo) {
      if (app.authEnabled) {
        await api.auth.exitSudo().catch(() => {})
      }
      app.setSudo(false)
      app.toast(i18n.auth.exitSudo)
      return
    }
    if (app.authEnabled) {
      setSudoPassword('')
      setSudoDialogOpen(true)
    } else {
      app.setSudo(true)
      app.toast(i18n.auth.enterSudo)
    }
  }

  const submitSudo = async () => {
    if (!sudoPassword) return
    setSudoLoading(true)
    try {
      await api.auth.sudo(sudoPassword)
      app.setSudo(true)
      app.toast(i18n.auth.enterSudo)
      setSudoDialogOpen(false)
    } catch (e: unknown) {
      const err = e as api.ApiError
      app.toast(`${i18n.auth.sudoMode}${i18n.common.error}：${err.body || err.status}`, 'destructive', 4000)
    } finally {
      setSudoLoading(false)
    }
  }

  const handleLogout = async () => {
    await api.auth.logout().catch(() => {})
    window.location.reload()
  }

  const navLabel = (labelKey: string) => {
    if (labelKey === 'stats') {
      return lang === 'zh' ? '数据统计' : lang === 'ja' ? '統計' : 'Statistics'
    }
    return (i18n.nav as Record<string, string>)[labelKey] ?? labelKey
  }

  const { resolvedTheme, setTheme } = useTheme()
  const isDark = resolvedTheme === 'dark'
  const toggleTheme = () => setTheme(isDark ? 'light' : 'dark')

  return (
    <>
    <Sidebar collapsible="icon" className="border-r border-border">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild>
              <Link href="/" onClick={e => handleNavClick(e, '/')}>
                <div className="grid flex-1 text-left leading-tight ml-2">
                  <span className="truncate font-serif text-xl font-bold tracking-tighter text-primary">{i18n.app.name}</span>
                  <span className="text-muted-foreground truncate text-[9px] font-mono uppercase tracking-[0.18em] opacity-60">
                    Memory Engine · v{app.stats.version}
                  </span>
                </div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent className="flex-1 overflow-y-auto min-w-0">
        <SidebarGroup>
          <SidebarGroupLabel className="text-[9px] font-mono uppercase tracking-[0.18em] text-muted-foreground/60">{i18n.nav.visualization}</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {NAV_VISUALIZATION.map((item) => {
                const active = routeIsActive(pathname, item.href)
                return (
                  <SidebarMenuItem key={item.href}>
                    <Link href={item.href} className="flex w-full" onClick={e => handleNavClick(e, item.href)}>
                      <SidebarMenuButton isActive={active} tooltip={navLabel(item.labelKey)} className="w-full cursor-pointer">
                        <item.icon />
                        <span>{navLabel(item.labelKey)}</span>
                      </SidebarMenuButton>
                    </Link>
                  </SidebarMenuItem>
                )
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarSeparator />

        <SidebarGroup>
          <SidebarGroupLabel className="text-[9px] font-mono uppercase tracking-[0.18em] text-muted-foreground/60">{i18n.nav.tools}</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {NAV_TOOLS.map((item) => {
                const active = routeIsActive(pathname, item.href)
                return (
                  <SidebarMenuItem key={item.href}>
                    <Link href={item.href} className="flex w-full" onClick={e => handleNavClick(e, item.href)}>
                      <SidebarMenuButton isActive={active} tooltip={navLabel(item.labelKey)} className="w-full cursor-pointer">
                        <item.icon />
                        <span>{navLabel(item.labelKey)}</span>
                      </SidebarMenuButton>
                    </Link>
                  </SidebarMenuItem>
                )
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarSeparator />

        <SidebarGroup>
          <SidebarGroupLabel className="text-[9px] font-mono uppercase tracking-[0.18em] text-muted-foreground/60">{i18n.nav.admin}</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {NAV_ADMIN.map((item) => {
                const active = routeIsActive(pathname, item.href)
                return (
                  <SidebarMenuItem key={item.href}>
                    <Link href={item.href} className="flex w-full" onClick={e => handleNavClick(e, item.href)}>
                      <SidebarMenuButton isActive={active} tooltip={navLabel(item.labelKey)} className="w-full cursor-pointer">
                        <item.icon />
                        <span>{navLabel(item.labelKey)}</span>
                      </SidebarMenuButton>
                    </Link>
                  </SidebarMenuItem>
                )
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="mt-auto shrink-0 border-t border-border p-2">
        <EngineStatusBadge />

        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              onClick={handleSudoClick}
              disabled={sudoLoading}
              tooltip={app.sudo ? i18n.auth.exitSudo : i18n.auth.enterSudo}
              className="cursor-pointer"
            >
              {app.sudo ? <Unlock /> : <Lock />}
              <span>{app.sudo ? i18n.auth.exitSudo : i18n.auth.enterSudo}</span>
              {effectiveSudoAlways && (
                <Badge variant="secondary" className="ml-auto text-[10px] opacity-70">Dev</Badge>
              )}
            </SidebarMenuButton>
          </SidebarMenuItem>

          <SidebarMenuItem>
            <Link href="/settings" className="flex w-full" onClick={e => handleNavClick(e, '/settings')}>
              <SidebarMenuButton isActive={routeIsActive(pathname, '/settings')} tooltip={i18n.nav.settings} className="cursor-pointer">
                <Settings />
                <span>{i18n.nav.settings}</span>
              </SidebarMenuButton>
            </Link>
          </SidebarMenuItem>

          <SidebarMenuItem>
            <SidebarMenuButton onClick={toggleTheme} tooltip={i18n.settings.toggle} className="cursor-pointer">
              {isDark ? <Sun /> : <Moon />}
              <span>{i18n.settings.toggle}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>

          {app.authEnabled && (
            <SidebarMenuItem>
              <SidebarMenuButton onClick={handleLogout} tooltip={i18n.auth.logout} className="cursor-pointer">
                <LogOut />
                <span>{i18n.auth.logout}</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          )}
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>

    <Dialog open={sudoDialogOpen} onOpenChange={setSudoDialogOpen}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>{i18n.auth.sudoMode}</DialogTitle>
          <DialogDescription>{i18n.auth.sudoPrompt}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="sudo-password">{i18n.auth.password}</Label>
            <Input
              id="sudo-password"
              type="password"
              autoFocus
              placeholder="..."
              value={sudoPassword}
              onChange={e => setSudoPassword(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') submitSudo() }}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setSudoDialogOpen(false)} disabled={sudoLoading}>
            {i18n.common.cancel}
          </Button>
          <Button onClick={submitSudo} disabled={sudoLoading || !sudoPassword}>
            {sudoLoading ? i18n.common.loading : i18n.common.confirm}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

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
