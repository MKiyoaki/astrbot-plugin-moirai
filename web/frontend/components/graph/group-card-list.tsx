'use client'

import { Users, Search } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { GroupCardItem } from './group-card'
import type { GroupCard } from '@/lib/graph-types'
import { useApp } from '@/lib/store'

interface GroupCardListProps {
  groups: GroupCard[]
  onOpen: (groupId: string) => void
  loading?: boolean
  isFiltered?: boolean
}

export function GroupCardList({ groups, onOpen, loading, isFiltered }: GroupCardListProps) {
  const { i18n } = useApp()
  if (loading) {
    return (
      <div
        className="p-4 grid gap-3"
        style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}
      >
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-52 rounded-xl" />
        ))}
      </div>
    )
  }

  if (groups.length === 0) {
    if (isFiltered) {
      return (
        <div className="flex flex-1 flex-col items-center justify-center p-12 text-center animate-in fade-in duration-500 min-h-[400px]">
          <Search className="size-12 text-muted-foreground/30 mb-4" />
          <h3 className="text-md font-medium text-muted-foreground">{i18n.page.graph.noResults}</h3>
        </div>
      )
    }
    return (
      <div className="flex flex-1 flex-col items-center justify-center p-12 text-center animate-in fade-in duration-500 min-h-[400px]">
        <div className="size-16 rounded-full bg-muted flex items-center justify-center mb-4">
          <Users className="size-8 text-muted-foreground/60" />
        </div>
        <h3 className="text-lg font-medium mb-1">{i18n.page.graph.noData}</h3>
        <p className="text-sm text-muted-foreground max-w-xs mx-auto">
          {i18n.page.graph.noDataDescription}
        </p>
      </div>
    )
  }

  return (
    <div
      className="p-4 grid gap-3"
      style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}
    >
      {groups.map(g => (
        <GroupCardItem
          key={g.group_id}
          group={g}
          onClick={() => onOpen(g.group_id)}
        />
      ))}
    </div>
  )
}
