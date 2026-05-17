'use client'

import { useEffect, useState } from 'react'
import { Bot, ChevronsUpDown, Globe, GitMerge } from 'lucide-react'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { MergePersonaDialog } from '@/components/shared/merge-persona-dialog'
import { useApp } from '@/lib/store'
import * as api from '@/lib/api'
import { cn } from '@/lib/utils'

function getInitials(name: string | null): string {
  if (!name) return '?'
  return name.slice(0, 2).toUpperCase()
}

export function PersonaSelector() {
  const { i18n, currentPersonaName, scopeMode, setCurrentPersona, personaConfig, sudo } = useApp()
  const t = i18n.personaSelector
  const [bots, setBots] = useState<api.BotPersonaItem[]>([])
  const [open, setOpen] = useState(false)
  const [mergeSrc, setMergeSrc] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    if (!personaConfig.isolationEnabled) return
    api.graph.listBots().then(r => setBots(r.items)).catch(() => {})
  }, [personaConfig.isolationEnabled, refreshKey])

  // Master switch: hide selector entirely when isolation is disabled.
  if (!personaConfig.isolationEnabled) return null

  const handleMerged = (target: string) => {
    // If current selection was the src, auto-switch to target
    if (currentPersonaName === mergeSrc) {
      setCurrentPersona(target, 'single')
    }
    setMergeSrc(null)
    setRefreshKey(k => k + 1)  // refresh bots list
  }

  const isAll = scopeMode === 'all'
  const label = isAll ? t.allPersonas : (currentPersonaName ?? t.defaultPersona)
  const hasMultiple = bots.length > 1 || (bots.length === 1 && bots[0].name !== null)

  return (
    <>
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
      <PopoverContent side="top" align="start" className="w-56 p-1">
        <p className="px-2 py-1 text-[10px] font-mono uppercase tracking-[0.15em] text-muted-foreground/60">
          {t.switchPersona}
        </p>

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
        {bots.map(bot => {
          const name = bot.name
          const isSelected = !isAll && currentPersonaName === name
          const displayName = name ?? t.defaultPersona
          const canMerge = sudo && !!name
          return (
            <div
              key={name ?? '__legacy__'}
              className={cn(
                'flex w-full items-center gap-1 rounded-md px-1.5 py-0.5 text-sm hover:bg-muted transition-colors',
                isSelected && 'bg-muted font-medium'
              )}
            >
              <button
                onClick={() => { setCurrentPersona(name, 'single'); setOpen(false) }}
                className="flex flex-1 items-center gap-2 px-1 py-1 min-w-0 text-left"
              >
                <Avatar className="h-6 w-6 shrink-0">
                  <AvatarFallback className="bg-primary/15 text-primary text-[10px] font-bold">
                    {name ? getInitials(name) : <Bot className="h-3 w-3" />}
                  </AvatarFallback>
                </Avatar>
                <span className="flex-1 truncate">{displayName}</span>
                <span className="text-[10px] text-muted-foreground/60 shrink-0">
                  {bot.event_count} {t.events}
                </span>
                {isSelected && <Badge variant="secondary" className="text-[9px] h-4 px-1">✓</Badge>}
              </button>
              {canMerge && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 shrink-0 text-muted-foreground/60 hover:text-foreground"
                  onClick={e => { e.stopPropagation(); setOpen(false); setMergeSrc(name) }}
                  title={t.mergeAction}
                >
                  <GitMerge className="size-3" />
                </Button>
              )}
            </div>
          )
        })}

        {bots.length === 0 && (
          <p className="px-2 py-2 text-xs text-muted-foreground">{t.noBotsFound}</p>
        )}
      </PopoverContent>
    </Popover>

    {mergeSrc !== null && (
      <MergePersonaDialog
        open={mergeSrc !== null}
        src={mergeSrc}
        bots={bots}
        onClose={() => setMergeSrc(null)}
        onMerged={handleMerged}
      />
    )}
    </>
  )
}
