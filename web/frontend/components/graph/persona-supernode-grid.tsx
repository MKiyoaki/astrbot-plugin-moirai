'use client'

import { Network, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import type { BotPersonaItem } from '@/lib/api'
import { useApp } from '@/lib/store'

interface PersonaSupernodeGridProps {
  items: BotPersonaItem[]
  loading?: boolean
  isFiltered?: boolean
  onOpen: (name: string | null) => void
}

export function PersonaSupernodeGrid({
  items,
  loading,
  isFiltered,
  onOpen,
}: PersonaSupernodeGridProps) {
  const { i18n } = useApp()
  const t = i18n.graph.supernodes

  if (loading) {
    return (
      <div
        className="grid gap-3 p-4"
        style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))' }}
      >
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-44 rounded-lg" />
        ))}
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="flex min-h-[400px] flex-col items-center justify-center p-12 text-center animate-in fade-in duration-500">
        <Search className="mb-4 size-12 text-muted-foreground/30" />
        <h3 className="text-md font-medium text-muted-foreground">
          {isFiltered ? i18n.page.graph.noResults : t.empty}
        </h3>
      </div>
    )
  }

  const maxEvents = Math.max(...items.map(item => item.event_count), 1)

  return (
    <div
      className="grid gap-3 p-4"
      style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))' }}
    >
      {items.map(item => {
        const label = item.name ?? i18n.personaSelector.defaultPersona
        const scale = Math.max(0.35, item.event_count / maxEvents)
        const nodeSize = 44 + Math.round(scale * 28)
        return (
          <Card key={item.name ?? '__legacy__'} className="overflow-hidden">
            <CardHeader className="gap-1 p-4 pb-2">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <CardTitle className="truncate text-sm">{label}</CardTitle>
                  <CardDescription className="text-xs">{t.nodeHint}</CardDescription>
                </div>
                <Badge variant="secondary" className="shrink-0">
                  {item.event_count}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="flex justify-center p-4">
              <div
                className="flex items-center justify-center rounded-full border bg-muted text-primary shadow-sm"
                style={{ width: nodeSize, height: nodeSize }}
              >
                <Network className="size-5" />
              </div>
            </CardContent>
            <CardFooter className="p-4 pt-0">
              <Button className="w-full" size="sm" onClick={() => onOpen(item.name)}>
                {t.drillDown}
              </Button>
            </CardFooter>
          </Card>
        )
      })}
    </div>
  )
}
