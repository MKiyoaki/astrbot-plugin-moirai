'use client'

import { useState, useEffect, useMemo } from 'react'
import { useTheme } from 'next-themes'
import { Moon, Sun, Check, Play, Sparkles, Languages } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import { Switch } from '@/components/ui/switch'
import { Separator } from '@/components/ui/separator'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { PageHeader } from '@/components/layout/page-header'
import { useApp } from '@/lib/store'
import * as api from '@/lib/api'

// Standard shadcn/ui theme definitions
const SHADCN_THEMES = [
  { id: 'zinc', label: 'Zinc' },
  { id: 'venus', label: 'Venus' },
  { id: 'juno', label: 'Juno' },
  { id: 'orange', label: 'Orange' },
  { id: 'green', label: 'Green' },
  { id: 'yellow', label: 'Yellow' },
  { id: 'violet', label: 'Violet' },
]

export default function SettingsPage() {
  const { i18n, lang, setLang, ...app } = useApp()
  const { resolvedTheme, setTheme } = useTheme()
  const isDark = resolvedTheme === 'dark'
  
  // Default to zinc, the standard shadcn base
  const [colorScheme, setColorScheme] = useState(() =>
    typeof localStorage !== 'undefined' ? (localStorage.getItem('em_color_scheme') || 'zinc') : 'zinc',
  )

  const TASKS = useMemo(() => [
    { id: 'salience_decay',       icon: '📉', label: i18n.settings.taskSalienceDecay    },
    { id: 'projection',           icon: '📄', label: i18n.settings.taskProjection        },
    { id: 'persona_synthesis',    icon: '🧠', label: i18n.settings.taskPersonaSynthesis  },
    { id: 'impression_aggregation',icon: '👥', label: i18n.settings.taskImpressionAgg   },
    { id: 'group_summary',        icon: '📋', label: i18n.settings.taskGroupSummary      },
    { id: 'reindex_all',         icon: '🔍', label: i18n.settings.taskReindexAll       },
  ], [i18n])

  useEffect(() => {
    const root = document.documentElement
    root.classList.remove(...SHADCN_THEMES.map(t => `theme-${t.id}`))
    if (colorScheme !== 'zinc') {
      root.classList.add(`theme-${colorScheme}`)
    }
  }, [colorScheme])

  const [oldPw, setOldPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [taskStatus, setTaskStatus] = useState<Record<string, string>>({})
  const [extPanels, setExtPanels] = useState<{ plugin_id: string; title: string }[]>([])
  const [panelsLoaded, setPanelsLoaded] = useState(false)

  // Load ext panels on first render
  if (!panelsLoaded) {
    setPanelsLoaded(true)
    api.admin.panels().then(r => setExtPanels(r.panels)).catch(() => {})
  }

  const toggleTheme = () => {
    setTheme(isDark ? 'light' : 'dark')
  }

  // Update logic to apply standard shadcn theme classes
  const applyColor = (id: string | null) => {
    if (!id) return
    setColorScheme(id)
    localStorage.setItem('em_color_scheme', id)
  }

  const changePassword = async () => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    if (!oldPw || !newPw) { app.toast(i18n.common.error, 'destructive'); return }
    try {
      await api.auth.changePassword(oldPw, newPw)
      app.toast(i18n.common.success)
      setOldPw(''); setNewPw('')
      setTimeout(() => location.reload(), 1500)
    } catch (e: unknown) {
      app.toast(i18n.common.error + ': ' + (e as api.ApiError).body, 'destructive', 4000)
    }
  }

  const runTask = async (name: string) => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    setTaskStatus(prev => ({ ...prev, [name]: 'running' }))
    app.toast(`${i18n.common.loading} ${name}…`)
    try {
      const r = await api.admin.runTask(name)
      setTaskStatus(prev => ({ ...prev, [name]: r.ok ? 'ok' : 'fail' }))
      app.toast(r.ok ? `${name} ${i18n.common.success}` : `${name} ${i18n.common.error}`)
      await app.refreshStats()
    } catch (e: unknown) {
      setTaskStatus(prev => ({ ...prev, [name]: 'fail' }))
      app.toast(`${name} ${i18n.common.error}: ${(e as api.ApiError).body || ''}`, 'destructive', 4000)
    }
  }

  const injectDemo = async () => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    app.toast(i18n.common.loading + '…')
    try {
      const r = await api.admin.injectDemo()
      const s = r.seeded
      app.toast(`${i18n.common.success}: ${s.personas} , ${s.events}, ${s.impressions}`)
      await app.refreshStats()
    } catch (e: unknown) {
      app.toast(i18n.common.error + ': ' + (e as api.ApiError).body, 'destructive', 4000)
    }
  }

  const statusLabel = app.sudo
    ? i18n.auth.status.loggedInSudo
    : app.authenticated
      ? i18n.auth.status.loggedIn
      : i18n.auth.status.notLoggedIn

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <PageHeader
        title={i18n.page.settings.title}
        description={i18n.page.settings.description}
      />

      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-2xl space-y-6 p-6">

          <Card>
            <CardHeader>
              <CardTitle>{i18n.settings.language}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Languages className="size-4 text-muted-foreground" />
                  <Label>{i18n.settings.language}</Label>
                </div>
                <Tabs value={lang} onValueChange={(v: string) => setLang(v as 'zh' | 'en' | 'ja')}>
                  <TabsList className="grid w-60 grid-cols-3">
                    <TabsTrigger value="zh">中文</TabsTrigger>
                    <TabsTrigger value="en">EN</TabsTrigger>
                    <TabsTrigger value="ja">日本語</TabsTrigger>
                  </TabsList>
                </Tabs>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{i18n.settings.theme}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <Label>{i18n.settings.darkLight}</Label>
                <Button variant="outline" size="sm" onClick={toggleTheme}>
                  {isDark ? <Sun className="mr-1.5 size-3.5" /> : <Moon className="mr-1.5 size-3.5" />}
                  {i18n.settings.toggle}
                </Button>
              </div>
              
              <div className="flex items-center justify-between">
                <Label>{i18n.settings.accentColor}</Label>
                <Select value={colorScheme} onValueChange={applyColor}>
                  <SelectTrigger className="w-[180px]">
                    <SelectValue placeholder="Select a theme" />
                  </SelectTrigger>
                  <SelectContent>
                    {SHADCN_THEMES.map((theme) => (
                      <SelectItem key={theme.id} value={theme.id}>
                        {theme.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{i18n.settings.auth}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <Label>{i18n.settings.session}</Label>
                <Badge variant={app.sudo ? 'default' : 'secondary'} className="text-xs">
                  {statusLabel}
                </Badge>
              </div>
              <Separator />
              <div className="flex flex-col gap-2">
                <Label>{i18n.settings.changePassword}</Label>
                <div className="flex gap-2">
                  <Input
                    type="password"
                    placeholder={i18n.auth.oldPassword}
                    value={oldPw}
                    onChange={e => setOldPw(e.target.value)}
                    className="flex-1"
                  />
                  <Input
                    type="password"
                    placeholder={i18n.auth.newPassword}
                    value={newPw}
                    onChange={e => setNewPw(e.target.value)}
                    className="flex-1"
                  />
                  <Button size="sm" onClick={changePassword} disabled={!app.sudo}>
                    <Check className="mr-1 size-3.5" />{i18n.common.save}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{i18n.settings.sudoSettings}</CardTitle>
              <CardDescription>{i18n.settings.sudoGuardDisabledHint}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <Label htmlFor="sudo-guard">{i18n.settings.sudoGuardEnabled}</Label>
                <Switch
                  id="sudo-guard"
                  checked={app.sudoGuardEnabled}
                  onCheckedChange={app.setSudoGuardEnabled}
                />
              </div>
              {app.sudoGuardEnabled && (
                <div className="flex items-center gap-3">
                  <Label htmlFor="sudo-minutes" className="flex-1">
                    {i18n.settings.sudoGuardMinutes}
                  </Label>
                  <Input
                    id="sudo-minutes"
                    type="number"
                    min={0}
                    value={app.sudoGuardMinutes}
                    onChange={e => {
                      const v = parseInt(e.target.value, 10)
                      if (v >= 0) app.setSudoGuardMinutes(v)
                    }}
                    className="w-24"
                  />
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{i18n.settings.tasks}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              {TASKS.map(task => (
                <div key={task.id} className="flex items-center justify-between py-1">
                  <span className="text-sm">{task.icon} {task.label}</span>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!app.sudo || taskStatus[task.id] === 'running'}
                    onClick={() => runTask(task.id)}
                  >
                    {taskStatus[task.id] === 'running' ? (
                      i18n.common.loading
                    ) : taskStatus[task.id] === 'ok' ? (
                      <><Check className="mr-1 size-3.5 text-green-500" />{i18n.settings.run}</>
                    ) : (
                      <><Play className="mr-1 size-3.5" />{i18n.settings.run}</>
                    )}
                  </Button>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{i18n.settings.demo}</CardTitle>
              <CardDescription>{i18n.settings.demoHint}</CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="outline" size="sm" onClick={injectDemo} disabled={!app.sudo}>
                <Sparkles className="mr-1.5 size-3.5" />{i18n.settings.inject}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{i18n.settings.thirdParty}</CardTitle>
            </CardHeader>
            <CardContent>
              {extPanels.length === 0 ? (
                <p className="text-muted-foreground text-sm">{i18n.settings.noThirdParty}</p>
              ) : (
                extPanels.map(p => (
                  <div key={p.plugin_id} className="text-sm py-1">
                    <strong>{p.title}</strong> — {p.plugin_id}
                  </div>
                ))
              )}
            </CardContent>
          </Card>

        </div>
      </div>
    </div>
  )
}
