'use client'

import { useEffect, useState } from 'react'
import { Bot, Globe } from 'lucide-react'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { useApp } from '@/lib/store'
import * as api from '@/lib/api'
import { cn } from '@/lib/utils'

function getInitials(name: string): string {
  return name.slice(0, 2).toUpperCase()
}

export function FirstLaunchPersonaPicker() {
  const { i18n, firstLaunchDone, setCurrentPersona, setFirstLaunchDone, authenticated } = useApp()
  const t = i18n.personaSelector
  const [bots, setBots] = useState<api.BotPersonaItem[]>([])
  const [selected, setSelected] = useState<{ name: string | null; mode: 'single' | 'all' }>({
    name: null, mode: 'all',
  })
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!authenticated || firstLaunchDone) return
    api.graph.listBots().then(r => {
      const items = r.items
      // Only show picker if there are multiple distinct bot personas
      if (items.length > 1 || (items.length === 1 && items[0].name !== null)) {
        setBots(items)
        setOpen(true)
      } else {
        // Single or no personas — skip picker, mark done
        setFirstLaunchDone(true)
      }
    }).catch(() => setFirstLaunchDone(true))
  }, [authenticated, firstLaunchDone, setFirstLaunchDone])

  const handleConfirm = () => {
    setCurrentPersona(selected.name, selected.mode)
    setFirstLaunchDone(true)
    setOpen(false)
  }

  return (
    <Dialog open={open} onOpenChange={() => {}}>
      <DialogContent className="sm:max-w-md" onInteractOutside={e => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>{t.firstLaunchTitle}</DialogTitle>
          <DialogDescription>{t.firstLaunchDesc}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-2 py-2">
          {/* All Bots */}
          <button
            onClick={() => setSelected({ name: null, mode: 'all' })}
            className={cn(
              'flex items-center gap-3 rounded-lg border px-3 py-2.5 text-sm transition-colors hover:bg-muted',
              selected.mode === 'all' && 'border-primary bg-primary/5'
            )}
          >
            <Avatar className="h-8 w-8 shrink-0">
              <AvatarFallback className="bg-muted text-muted-foreground">
                <Globe className="h-4 w-4" />
              </AvatarFallback>
            </Avatar>
            <div className="flex-1 text-left">
              <p className="font-medium">{t.viewAll}</p>
              <p className="text-xs text-muted-foreground">{t.viewAllDesc}</p>
            </div>
            {selected.mode === 'all' && (
              <div className="h-2 w-2 rounded-full bg-primary shrink-0" />
            )}
          </button>

          {/* Per-bot options */}
          {bots.map(bot => {
            const name = bot.name
            const displayName = name ?? t.defaultPersona
            const isSelected = selected.mode === 'single' && selected.name === name
            return (
              <button
                key={name ?? '__legacy__'}
                onClick={() => setSelected({ name, mode: 'single' })}
                className={cn(
                  'flex items-center gap-3 rounded-lg border px-3 py-2.5 text-sm transition-colors hover:bg-muted',
                  isSelected && 'border-primary bg-primary/5'
                )}
              >
                <Avatar className="h-8 w-8 shrink-0">
                  <AvatarFallback className="bg-primary/15 text-primary font-bold text-xs">
                    {name ? getInitials(name) : <Bot className="h-4 w-4" />}
                  </AvatarFallback>
                </Avatar>
                <div className="flex-1 text-left">
                  <p className="font-medium">{displayName}</p>
                  <p className="text-xs text-muted-foreground">
                    {bot.event_count} {t.events}
                  </p>
                </div>
                {isSelected && (
                  <div className="h-2 w-2 rounded-full bg-primary shrink-0" />
                )}
              </button>
            )
          })}
        </div>

        <DialogFooter>
          <Button onClick={handleConfirm} className="w-full">
            {t.confirmSelect}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
