'use client'

import { Skeleton } from '@/components/ui/skeleton'
import { GroupCardItem } from './group-card'
import type { GroupCard } from '@/lib/graph-types'
import { useApp } from '@/lib/store'

interface GroupCardListProps {
  groups: GroupCard[]
  onOpen: (groupId: string) => void
  loading?: boolean
}

export function GroupCardList({ groups, onOpen, loading }: GroupCardListProps) {
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
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground py-16">
        {i18n.common.noData}
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
