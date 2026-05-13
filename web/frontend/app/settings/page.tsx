'use client'

import { useState, useEffect, useMemo } from 'react'
import { useTheme } from 'next-themes'
import { Moon, Sun, Languages } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { PageHeader } from '@/components/layout/page-header'
import { OnThisPage } from '@/components/shared/on-this-page'
import { useApp } from '@/lib/store'
import { getStored, setStored } from '@/lib/safe-storage'
import * as api from '@/lib/api'

const SHADCN_THEMES = [
  { id: 'moirai', label: 'Moirai' },
  { id: 'nox', label: 'Nox' },
  { id: 'venus', label: 'Venus' },
  { id: 'juno', label: 'Cirrus' },
  { id: 'augustus', label: 'Augustus' },
  { id: 'selune', label: 'Aether' },
  { id: 'folio', label: 'Folio' },
]

export default function SettingsPage() {
  const { i18n, lang, setLang } = useApp()
  const { resolvedTheme, setTheme } = useTheme()
  const isDark = resolvedTheme === 'dark'

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

  const toggleTheme = () => setTheme(isDark ? 'light' : 'dark')

  const applyColor = (id: string | null) => {
    if (!id) return
    setColorScheme(id)
    setStored('em_color_scheme', id)
  }

  return (
    <div className="flex h-full flex-col overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-500 ease-out fill-mode-both">
      <PageHeader
        title={i18n.page.settings.title}
        description={i18n.page.settings.description}
      />

      <div className="flex-1 overflow-y-auto">
        <div className="flex justify-center gap-8 px-6 pb-24 pt-6">
          <div className="flex-1 max-w-2xl space-y-6">

            <Card id="language" className="scroll-mt-20">
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

            <Card id="theme" className="scroll-mt-20">
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

            <Card id="third-party" className="scroll-mt-20">
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
