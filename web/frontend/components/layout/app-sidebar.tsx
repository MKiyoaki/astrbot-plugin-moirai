'use client'

import React, { useState } from 'react'
import { usePathname } from 'next/navigation'
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
import Link from 'next/link'
import { useApp } from '@/lib/store'
import * as api from '@/lib/api'
import { routeIsActive } from '@/lib/navigation'

export function AppSidebar() {
  const pathname = usePathname()
  const app = useApp()
  const { i18n, lang } = app

  const [sudoLoading, setSudoLoading] = useState(false)
  const [sudoDialogOpen, setSudoDialogOpen] = useState(false)
  const [sudoPassword, setSudoPassword] = useState('')

  const effectiveSudoAlways = !app.authEnabled

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

  const NAV_VISUALIZATION = React.useMemo(() => [
    { href: '/events', icon: Activity,  label: i18n.nav.events },
    { href: '/graph',  icon: Share2,    label: i18n.nav.graph },
    { href: '/summary',icon: BookOpen,  label: i18n.nav.summary },
  ], [i18n])

  const NAV_TOOLS = React.useMemo(() => [
    { href: '/recall', icon: Search,    label: i18n.nav.recall },
    { href: '/stats',  icon: BarChart3, label: lang === 'zh' ? '数据统计' : (lang === 'ja' ? '統計' : 'Statistics') },
  ], [i18n, lang])

  const NAV_ADMIN = React.useMemo(() => [
    { href: '/library',  icon: Database,           label: i18n.nav.library },
    { href: '/config',   icon: SlidersHorizontal,  label: i18n.nav.config },
  ], [i18n])

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
              <Link href="/">
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
                    <Link href={item.href} className="flex w-full">
                      <SidebarMenuButton isActive={active} tooltip={item.label} className="w-full cursor-pointer">
                        <item.icon />
                        <span>{item.label}</span>
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
                    <Link href={item.href} className="flex w-full">
                      <SidebarMenuButton isActive={active} tooltip={item.label} className="w-full cursor-pointer">
                        <item.icon />
                        <span>{item.label}</span>
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
                    <Link href={item.href} className="flex w-full">
                      <SidebarMenuButton isActive={active} tooltip={item.label} className="w-full cursor-pointer">
                        <item.icon />
                        <span>{item.label}</span>
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
        <div className="flex items-center gap-2 px-3 py-2">
          <span className="relative flex h-1.5 w-1.5 shrink-0">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-green-500"></span>
          </span>
          <span className="group-data-[collapsible=icon]:hidden truncate text-[9px] font-mono uppercase tracking-[0.18em] text-muted-foreground/60">
            {i18n.landing.engineActive}
          </span>
        </div>

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
            <Link href="/settings" className="flex w-full">
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
    </>
  )
}
