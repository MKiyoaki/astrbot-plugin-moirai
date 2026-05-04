'use client'

import React, { useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useTheme } from 'next-themes'
import {
  Activity, Share2, BookOpen, Search, Database, Settings, SlidersHorizontal,
  Lock, Unlock, Moon, Sun, LogOut,
} from 'lucide-react'
import {
  Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent,
  SidebarGroupLabel, SidebarHeader, SidebarMenu, SidebarMenuButton,
  SidebarMenuItem, SidebarSeparator,
} from '@/components/ui/sidebar'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useApp } from '@/lib/store'
import { i18n } from '@/lib/i18n'
import * as api from '@/lib/api'

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
  const [sudoDialogOpen, setSudoDialogOpen] = useState(false)
  const [sudoPassword, setSudoPassword] = useState('')

  const effectiveSudoAlways = !app.sudoGuardEnabled || app.sudoGuardMinutes === 0

  const handleSudoClick = async () => {
    if (app.sudo && !effectiveSudoAlways) {
      await api.auth.exitSudo().catch(() => {})
      app.setSudo(false)
      app.toast('已退出 Sudo')
      return
    }
    if (effectiveSudoAlways) return
    
    setSudoPassword('')
    setSudoDialogOpen(true)
  }

  const submitSudo = async () => {
    if (!sudoPassword) return
    setSudoLoading(true)
    try {
      await api.auth.sudo(sudoPassword)
      app.setSudo(true)
      app.toast('已进入 Sudo 模式')
      setSudoDialogOpen(false)
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

  return (
    <>
      <Sidebar collapsible="icon" className="border-r border-border">
        <SidebarHeader>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton size="lg" asChild>
                <Link href="/">
                  <div className="bg-primary text-primary-foreground flex aspect-square size-8 items-center justify-center rounded-lg">
                    <BookOpen className="size-4" />
                  </div>
                  <div className="grid flex-1 text-left text-sm leading-tight">
                    <span className="truncate font-semibold">{i18n.app.name}</span>
                    <span className="text-muted-foreground truncate text-xs">
                      v{app.stats.version}
                    </span>
                  </div>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarHeader>

        <SidebarContent className="flex-1 overflow-y-auto min-w-0">
          <SidebarGroup>
            <SidebarGroupLabel>{i18n.nav.visualization}</SidebarGroupLabel>
            {/* 严格补充 SidebarGroupContent，修复点击事件丢失 */}
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
            <SidebarGroupLabel>{i18n.nav.tools}</SidebarGroupLabel>
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
            <SidebarGroupLabel>{i18n.nav.admin}</SidebarGroupLabel>
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

        {/* 锁定底部的空间，防止透明溢出遮挡上面的菜单 */}
        <SidebarFooter className="mt-auto shrink-0 border-t border-border p-2">
          <div className="flex flex-wrap gap-1 px-2 py-2 group-data-[collapsible=icon]:hidden">
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

          <SidebarSeparator className="group-data-[collapsible=icon]:hidden mb-2" />

          <SidebarMenu>
            {!effectiveSudoAlways && (
              <SidebarMenuItem>
                <SidebarMenuButton 
                  onClick={handleSudoClick} 
                  disabled={sudoLoading}
                  tooltip={app.sudo ? '退出 Sudo' : '进入 Sudo 模式'}
                  className="cursor-pointer"
                >
                  {app.sudo ? <Unlock /> : <Lock />}
                  <span>{app.sudo ? '退出 Sudo' : '进入 Sudo'}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            )}
            
            {effectiveSudoAlways && (
              <SidebarMenuItem className="group-data-[collapsible=icon]:hidden">
                <div className="px-2 py-1">
                  <Badge variant="secondary" className="text-xs px-1.5">
                    <Unlock className="size-3 mr-1" />Sudo
                  </Badge>
                </div>
              </SidebarMenuItem>
            )}

            <SidebarMenuItem>
              <SidebarMenuButton onClick={toggleTheme} tooltip="切换主题" className="cursor-pointer">
                {isDark ? <Sun /> : <Moon />}
                <span>切换主题</span>
              </SidebarMenuButton>
            </SidebarMenuItem>

            {app.authEnabled && (
              <SidebarMenuItem>
                <SidebarMenuButton onClick={handleLogout} tooltip="退出登录" className="cursor-pointer">
                  <LogOut />
                  <span>退出登录</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            )}
          </SidebarMenu>
        </SidebarFooter>
      </Sidebar>

      <Dialog open={sudoDialogOpen} onOpenChange={setSudoDialogOpen}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>身份验证</DialogTitle>
            <DialogDescription>
              请输入管理密码以进入 Sudo 模式获取最高操作权限。
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="sudo-password">管理密码</Label>
              <Input
                id="sudo-password"
                type="password"
                autoFocus
                placeholder="在此输入密码..."
                value={sudoPassword}
                onChange={(e) => setSudoPassword(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') submitSudo()
                }}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSudoDialogOpen(false)} disabled={sudoLoading}>
              {i18n.common.cancel || "取消"}
            </Button>
            <Button onClick={submitSudo} disabled={sudoLoading || !sudoPassword}>
              {sudoLoading ? '验证中...' : (i18n.common.confirm || "确认")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}