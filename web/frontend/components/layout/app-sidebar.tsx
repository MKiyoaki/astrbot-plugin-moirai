'use client'

import React from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useTheme } from 'next-themes'
import {
  Activity, Share2, BookOpen, Search, Database, Settings, SlidersHorizontal,
  Lock, Unlock, Moon, Sun, LogOut,
} from 'lucide-react'
import {
  Sidebar, SidebarContent, SidebarFooter, SidebarGroup,
  SidebarGroupLabel, SidebarHeader, SidebarMenu, SidebarMenuButton,
  SidebarMenuItem, SidebarSeparator,
} from '@/components/ui/sidebar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { useApp } from '@/lib/store'
import { i18n } from '@/lib/i18n'
import * as api from '@/lib/api'
import { useState } from 'react'

const NAV_VISUALIZATION = [
  { href: '/events', icon: Activity,  label: i18n.nav.events },
  { href: '/graph',  icon: Share2,    label: i18n.nav.graph },
  { href: '/summary',icon: BookOpen,  label: i18n.nav.summary },
]
const NAV_TOOLS = [
  { href: '/recall', icon: Search,   label: i18n.nav.recall },
]
const NAV_ADMIN = [
  { href: '/library',  icon: Database,           label: i18n.nav.library },
  { href: '/config',   icon: SlidersHorizontal,  label: i18n.nav.config },
  { href: '/settings', icon: Settings,           label: i18n.nav.settings },
]

export function AppSidebar() {
  const pathname = usePathname()
  const router = useRouter()
  const app = useApp()
  const { resolvedTheme, setTheme } = useTheme()
  const isDark = resolvedTheme === 'dark'
  const [sudoLoading, setSudoLoading] = useState(false)

  const effectiveSudoAlways = !app.sudoGuardEnabled || app.sudoGuardMinutes === 0

  const handleSudo = async () => {
    if (app.sudo && !effectiveSudoAlways) {
      await api.auth.exitSudo().catch(() => {})
      app.setSudo(false)
      app.toast('已退出 Sudo')
      return
    }
    if (effectiveSudoAlways) return // always sudo, no toggle
    const pw = window.prompt('再次输入密码以进入 Sudo 模式：')
    if (!pw) return
    setSudoLoading(true)
    try {
      await api.auth.sudo(pw)
      app.setSudo(true)
      app.toast('已进入 Sudo 模式')
    } catch (e: unknown) {
      const err = e as api.ApiError
      app.toast(`Sudo 失败：${err.body || err.status}`, 'destructive', 4000)
    } finally {
      setSudoLoading(false)
    }
  }

  const handleLogout = async () => {
    await api.auth.logout().catch(() => {})
    await app.refreshAuth()
    router.push('/')
  }

  const toggleTheme = () => {
    setTheme(isDark ? 'light' : 'dark')
  }

  function NavGroup({ items }: { items: Array<{ href: string; icon: React.ComponentType<{ className?: string }>; label: string }> }) {
    return (
      <SidebarMenu>
        {items.map(({ href, icon: Icon, label }) => {
          const active = pathname === href || (href !== '/' && pathname.startsWith(href))
          return (
            <SidebarMenuItem key={href}>
              <SidebarMenuButton render={<Link href={href} />} isActive={active} tooltip={label}>
                <Icon />
                <span>{label}</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          )
        })}
      </SidebarMenu>
    )
  }

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" render={<Link href="/" />}>
              <div className="bg-primary text-primary-foreground flex aspect-square size-8 items-center justify-center rounded-lg">
                <BookOpen className="size-4" />
              </div>
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-semibold">{i18n.app.name}</span>
                <span className="text-muted-foreground truncate text-xs">
                  v{app.stats.version}
                </span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>{i18n.nav.visualization}</SidebarGroupLabel>
          <NavGroup items={NAV_VISUALIZATION} />
        </SidebarGroup>
        <SidebarSeparator />
        <SidebarGroup>
          <SidebarGroupLabel>{i18n.nav.tools}</SidebarGroupLabel>
          <NavGroup items={NAV_TOOLS} />
        </SidebarGroup>
        <SidebarSeparator />
        <SidebarGroup>
          <SidebarGroupLabel>{i18n.nav.admin}</SidebarGroupLabel>
          <NavGroup items={NAV_ADMIN} />
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        {/* Stats */}
        <div className="flex flex-wrap gap-1 px-2 py-1">
          {[
            { label: i18n.stats.personas,    val: app.stats.personas    },
            { label: i18n.stats.events,      val: app.stats.events      },
            { label: i18n.stats.impressions, val: app.stats.impressions },
          ].map(({ label, val }) => (
            <Badge key={label} variant="secondary" className="text-xs">
              {label} {val}
            </Badge>
          ))}
        </div>

        <Separator />

        {/* Actions */}
        <div className="flex items-center gap-1 px-1">
          {/* Sudo */}
          {!effectiveSudoAlways && (
            <Button
              variant={app.sudo ? 'secondary' : 'ghost'}
              size="icon-sm"
              onClick={handleSudo}
              disabled={sudoLoading}
              title={app.sudo ? '退出 Sudo' : '进入 Sudo 模式'}
            >
              {app.sudo ? <Unlock className="size-3.5" /> : <Lock className="size-3.5" />}
            </Button>
          )}
          {effectiveSudoAlways && (
            <Badge variant="secondary" className="text-xs px-1.5">
              <Unlock className="size-3 mr-1" />Sudo
            </Badge>
          )}

          {/* Theme */}
          <Button variant="ghost" size="icon-sm" onClick={toggleTheme} title="切换主题">
            {isDark ? <Sun className="size-3.5" /> : <Moon className="size-3.5" />}
          </Button>

          {/* Logout */}
          {app.authEnabled && (
            <Button variant="ghost" size="icon-sm" onClick={handleLogout} title="退出登录">
              <LogOut className="size-3.5" />
            </Button>
          )}
        </div>
      </SidebarFooter>
    </Sidebar>
  )
}
