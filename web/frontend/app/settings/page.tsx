'use client'

import { useState, useEffect, useMemo } from 'react'
import { useTheme } from 'next-themes'
import { Moon, Sun, Monitor, Languages, Palette, PanelsTopLeft } from 'lucide-react'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Badge } from '@/components/ui/badge'
import { PageHeader } from '@/components/layout/page-header'
import { OnThisPage } from '@/components/shared/on-this-page'
import { useApp } from '@/lib/store'
import { getStored, setStored } from '@/lib/safe-storage'
import * as api from '@/lib/api'
import { cn } from '@/lib/utils'

const SHADCN_THEMES = [
  { id: 'moirai', label: 'Moirai' },
  { id: 'nox', label: 'Nox' },
  { id: 'venus', label: 'Venus' },
  { id: 'juno', label: 'Cirrus' },
  { id: 'augustus', label: 'Augustus' },
  { id: 'selune', label: 'Aether' },
  { id: 'folio', label: 'Folio' },
]

const THEME_ACCENT_COLORS: Record<string, string> = {
  moirai: 'oklch(0.53 0.130 295)',
  nox: 'oklch(0.45 0.08 260)',
  venus: 'oklch(0.60 0.18 5)',
  juno: 'oklch(0.52 0.12 220)',
  augustus: 'oklch(0.58 0.14 55)',
  selune: 'oklch(0.55 0.10 200)',
  folio: 'oklch(0.48 0.09 140)',
}

export default function SettingsPage() {
  const { i18n, lang, setLang } = useApp()
  const { theme, setTheme } = useTheme()

  const [activeSection, setActiveSection] = useState<string>('')

  const SECTIONS = useMemo(() => [
    { id: 'language', label: i18n.settings.language },
    { id: 'theme', label: i18n.settings.theme },
    { id: 'third-party', label: i18n.settings.thirdParty },
  ], [i18n])

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visibleSections = entries
          .filter(entry => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)
        if (visibleSections.length > 0) {
          setActiveSection(visibleSections[0].target.id)
        }
      },
      {
        root: null,
        threshold: [0, 0.1, 0.5, 1.0],
        rootMargin: '-80px 0px -50% 0px'
      }
    )
    SECTIONS.forEach((section) => {
      const el = document.getElementById(section.id)
      if (el) observer.observe(el)
    })
    return () => observer.disconnect()
  }, [SECTIONS])

  const scrollTo = (id: string) => {
    const el = document.getElementById(id)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const [colorScheme, setColorScheme] = useState(() =>
    getStored('em_color_scheme', 'moirai') || 'moirai',
  )

  useEffect(() => {
    const root = document.documentElement
    root.classList.remove(...SHADCN_THEMES.map(t => `theme-${t.id}`))
    if (colorScheme !== 'zinc') {
      root.classList.add(`theme-${colorScheme}`)
    }
  }, [colorScheme])

  const [extPanels, setExtPanels] = useState<{ plugin_id: string; title: string }[]>([])

  useEffect(() => {
    api.admin.panels().then(r => setExtPanels(r.panels)).catch(() => {})
  }, [])

  const themeOptions = [
    { value: 'light',  icon: <Sun className="size-3.5" />,     label: i18n.settings.themeLight },
    { value: 'dark',   icon: <Moon className="size-3.5" />,    label: i18n.settings.themeDark },
    { value: 'system', icon: <Monitor className="size-3.5" />, label: i18n.settings.themeSystem },
  ]

  const applyColor = (id: string | null) => {
    if (!id) return
    setColorScheme(id)
    setStored('em_color_scheme', id)
  }

  return (
    <div className="flex h-full flex-col overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-500 ease-out fill-mode-both">
      <PageHeader
        variant="loom"
        loomIssue="ΡΥΘΜΙΣΕΙΣ"
          loomWindow={i18n.page.settings.loomWindow}
        title={i18n.page.settings.title}
      />

      <div className="flex-1 overflow-y-auto">
        <div className="flex justify-center gap-8 px-6 pb-24 pt-6">
          <div className="flex-1 max-w-3xl space-y-6">

            <Card id="language" className="scroll-mt-20 overflow-hidden border-muted/60 shadow-sm">
              <CardHeader className="border-b border-border/50 pb-4">
                <div className="flex items-center gap-3">
                  <div className="flex size-9 items-center justify-center rounded-md border bg-muted/40">
                    <Languages className="size-4 text-muted-foreground" />
                  </div>
                  <div>
                    <CardTitle className="text-base">{i18n.settings.language}</CardTitle>
                    <CardDescription className="text-xs">{(i18n.settings as any).languageDesc}</CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap items-center justify-between gap-3 pt-6">
                  <div className="flex items-center gap-2 text-sm">
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

            <Card id="theme" className="scroll-mt-20 overflow-hidden border-muted/60 shadow-sm">
              <CardHeader className="border-b border-border/50 pb-4">
                <div className="flex items-center gap-3">
                  <div className="flex size-9 items-center justify-center rounded-md border bg-muted/40">
                    <Palette className="size-4 text-muted-foreground" />
                  </div>
                  <div>
                    <CardTitle className="text-base">{i18n.settings.theme}</CardTitle>
                    <CardDescription className="text-xs">{(i18n.settings as any).themeDesc}</CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <div className="flex flex-wrap items-center justify-between gap-3 pt-6">
                  <Label>{i18n.settings.darkLight}</Label>
                  <ToggleGroup
                    type="single"
                    value={theme ?? 'system'}
                    onValueChange={(v: string) => v && setTheme(v)}
                    variant="outline"
                    size="sm"
                    className="gap-0"
                  >
                    {themeOptions.map(opt => (
                      <ToggleGroupItem
                        key={opt.value}
                        value={opt.value}
                        className="h-8 gap-1.5 px-3 text-xs"
                      >
                        {opt.icon}
                        <span>{opt.label}</span>
                      </ToggleGroupItem>
                    ))}
                  </ToggleGroup>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <Label>{i18n.settings.accentColor}</Label>
                  <div className="flex items-center gap-1.5">
                    {SHADCN_THEMES.map(t => (
                      <Tooltip key={t.id}>
                        <TooltipTrigger asChild>
                          <button
                            onClick={() => applyColor(t.id)}
                            className={cn(
                              'size-5 rounded-full border-2 transition-all',
                              colorScheme === t.id
                                ? 'border-foreground scale-110'
                                : 'border-transparent hover:scale-105',
                            )}
                            style={{ background: THEME_ACCENT_COLORS[t.id] }}
                            aria-label={t.label}
                          />
                        </TooltipTrigger>
                        <TooltipContent>{t.label}</TooltipContent>
                      </Tooltip>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card id="third-party" className="scroll-mt-20 overflow-hidden border-muted/60 shadow-sm">
              <CardHeader className="border-b border-border/50 pb-4">
                <div className="flex items-center gap-3">
                  <div className="flex size-9 items-center justify-center rounded-md border bg-muted/40">
                    <PanelsTopLeft className="size-4 text-muted-foreground" />
                  </div>
                  <div>
                    <CardTitle className="text-base">{i18n.settings.thirdParty}</CardTitle>
                    <CardDescription className="text-xs">{(i18n.settings as any).thirdPartyDesc}</CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-6">
                {extPanels.length === 0 ? (
                  <p className="text-muted-foreground text-sm">{i18n.settings.noThirdParty}</p>
                ) : (
                  extPanels.map(p => (
                    <div key={p.plugin_id} className="flex items-center justify-between gap-3 py-1 text-sm">
                      <strong>{p.title}</strong>
                      <Badge variant="outline" className="font-mono text-[10px]">{p.plugin_id}</Badge>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>

          </div>

          <aside className="hidden lg:block w-[200px] shrink-0">
            <div className="sticky top-6">
              <OnThisPage
                items={SECTIONS}
                activeId={activeSection}
                onItemClick={scrollTo}
                title={i18n.common.onThisPage}
              />
            </div>
          </aside>
        </div>
      </div>
    </div>
  )
}
