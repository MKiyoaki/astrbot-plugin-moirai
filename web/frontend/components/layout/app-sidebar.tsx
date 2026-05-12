'use client'

import React from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useTheme } from 'next-themes'
import {
  Activity, Share2, BookOpen, Search, Database, Settings, SlidersHorizontal,
  Moon, Sun, BarChart3,
} from 'lucide-react'
import {
  Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent,
  SidebarGroupLabel, SidebarHeader, SidebarMenu, SidebarMenuButton,
  SidebarMenuItem, SidebarSeparator,
} from '@/components/ui/sidebar'
import { useApp } from '@/lib/store'

export function AppSidebar() {
  const pathname = usePathname()
  const app = useApp()
  const { i18n, lang } = app

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
                const active = pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href))
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
                const active = pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href))
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
                const active = pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href))
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
            <Link href="/settings" className="flex w-full">
              <SidebarMenuButton isActive={pathname === '/settings'} tooltip={i18n.nav.settings} className="cursor-pointer">
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
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  )
}
