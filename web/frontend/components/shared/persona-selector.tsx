'use client'

import { useEffect, useMemo, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { ArrowRightLeft, Bot, ChevronsUpDown, Globe } from 'lucide-react'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { useApp } from '@/lib/store'
import * as api from '@/lib/api'
import { cn } from '@/lib/utils'

function getInitials(name: string | null): string {
  if (!name) return '?'
  return name.slice(0, 2).toUpperCase()
}

export function PersonaSelector({ popoverSide = 'top' }: { popoverSide?: 'top' | 'right' | 'bottom' | 'left' } = {}) {
  const { i18n, currentPersonaName, scopeMode, setCurrentPersona, personaConfig } = useApp()
  const t = i18n.personaSelector
  const router = useRouter()
  const pathname = usePathname()
  const [bots, setBots] = useState<api.BotPersonaItem[]>([])
  const [open, setOpen] = useState(false)

  const loadBots = () => {
    if (!personaConfig.isolationEnabled) return
    api.graph.listBots().then(r => setBots(r.items)).catch(() => {})
  }

  useEffect(() => {
    loadBots()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [personaConfig.isolationEnabled])

  useEffect(() => {
    if (open) loadBots()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const isAll = scopeMode === 'all'
  const label = isAll ? t.allPersonas : (currentPersonaName ?? t.defaultPersona)
  const visibleBots = useMemo(() => {
    if (isAll || bots.some(bot => bot.name === currentPersonaName)) return bots
    return [...bots, { name: currentPersonaName, event_count: 0 }]
  }, [bots, currentPersonaName, isAll])
  const hasMultiple = visibleBots.length > 1 || (visibleBots.length === 1 && visibleBots[0].name !== null)

  // Master switch: hide selector entirely when isolation is disabled.
  if (!personaConfig.isolationEnabled) return null
  const openOwnershipSettings = () => {
    const target = 'persona-ownership'
    setOpen(false)
    sessionStorage.setItem('em_config_scroll_target', target)
    if ((pathname ?? '').replace(/\/$/, '') === '/config') {
      window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}#${target}`)
      window.dispatchEvent(new CustomEvent('em_config_scroll_target', { detail: target }))
      window.setTimeout(() => {
        document.getElementById(target)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }, 120)
      return
    }
    router.push(`/config#${target}`)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          className="w-full justify-start gap-2 px-2 h-9 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:w-8 group-data-[collapsible=icon]:mx-auto"
          title={t.switchPersona}
        >
          <Avatar className="h-6 w-6 shrink-0">
            <AvatarFallback className={cn(
              'text-[10px] font-bold',
              isAll ? 'bg-muted text-muted-foreground' : 'bg-primary/15 text-primary'
            )}>
              {isAll ? <Globe className="h-3 w-3" /> : getInitials(currentPersonaName)}
            </AvatarFallback>
          </Avatar>
          <span className="group-data-[collapsible=icon]:hidden flex-1 truncate text-left text-xs">
            {label}
          </span>
          {hasMultiple && (
            <ChevronsUpDown className="group-data-[collapsible=icon]:hidden h-3 w-3 shrink-0 text-muted-foreground/60" />
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent side={popoverSide} align="start" className="w-56 p-1">
        <div className="flex items-center gap-1 px-2 py-1">
          <p className="min-w-0 flex-1 truncate text-[10px] font-mono uppercase tracking-[0.15em] text-muted-foreground/60">
            {t.switchPersona}
          </p>
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="size-7 shrink-0 border-primary/25 bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary"
            title={t.manageOwnershipTitle}
            aria-label={t.manageOwnership}
            onClick={openOwnershipSettings}
          >
            <ArrowRightLeft data-icon="icon-only" />
          </Button>
        </div>

        {/* All Bots option */}
        <button
          onClick={() => { setCurrentPersona(null, 'all'); setOpen(false) }}
          className={cn(
            'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted transition-colors',
            isAll && 'bg-muted font-medium'
          )}
        >
          <Avatar className="h-6 w-6 shrink-0">
            <AvatarFallback className="bg-muted text-muted-foreground text-[10px]">
              <Globe className="h-3 w-3" />
            </AvatarFallback>
          </Avatar>
          <span className="flex-1 truncate text-left">{t.viewAll}</span>
          {isAll && <Badge variant="secondary" className="text-[9px] h-4 px-1">✓</Badge>}
        </button>

        {/* Per-bot options */}
        {visibleBots.map(bot => {
          const name = bot.name
          const isSelected = !isAll && currentPersonaName === name
          const displayName = name ?? t.defaultPersona
          return (
            <button
              key={name ?? '__legacy__'}
              onClick={() => { setCurrentPersona(name, 'single'); setOpen(false) }}
              className={cn(
                'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted transition-colors',
                isSelected && 'bg-muted font-medium'
              )}
            >
              <Avatar className="h-6 w-6 shrink-0">
                <AvatarFallback className="bg-primary/15 text-primary text-[10px] font-bold">
                  {name ? getInitials(name) : <Bot className="h-3 w-3" />}
                </AvatarFallback>
              </Avatar>
              <span className="flex-1 truncate text-left">{displayName}</span>
              <span className="text-[10px] text-muted-foreground/60 shrink-0">
                {bot.event_count} {t.events}
              </span>
              {isSelected && <Badge variant="secondary" className="text-[9px] h-4 px-1">✓</Badge>}
            </button>
          )
        })}

        {visibleBots.length === 0 && (
          <p className="px-2 py-2 text-xs text-muted-foreground">{t.noBotsFound}</p>
        )}
      </PopoverContent>
    </Popover>
  )
}
