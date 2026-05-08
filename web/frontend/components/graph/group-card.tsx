'use client'

import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { MiniGraph } from './mini-graph'
import type { GroupCard } from '@/lib/graph-types'
import { useApp } from '@/lib/store'

interface GroupCardProps {
  group: GroupCard
  onClick: () => void
}

export function GroupCardItem({ group, onClick }: GroupCardProps) {
  const { i18n } = useApp()
  const t = i18n.graph
  const extraTags = group.top_tags.length > 4 ? group.top_tags.length - 4 : 0
  const visibleTags = group.top_tags.slice(0, 4)

  const lastActive = group.last_active
    ? new Date(group.last_active).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
    : '—'

  return (
    <Card
      className="cursor-pointer transition-all duration-150 hover:shadow-md hover:-translate-y-px"
      onClick={onClick}
    >
      <CardContent className="p-4 space-y-2.5">
        {/* Header: name + ID + member count */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="font-semibold text-sm truncate">{group.name}</p>
            <p className="text-[10px] text-muted-foreground font-mono truncate">{group.group_id}</p>
          </div>
          <Badge variant="secondary" className="shrink-0 text-xs">
            {group.member_count} {t.groupCard.members}
          </Badge>
        </div>

        {/* Stats row */}
        <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
          <span>{t.nodeCount} <strong className="text-foreground">{group.node_count}</strong></span>
          <span>·</span>
          <span>{t.edgePairCount} <strong className="text-foreground">{group.edge_pair_count}</strong></span>
          <span>·</span>
          <span>{t.groupCard.lastActive} {lastActive}</span>
        </div>

        {/* Top tags */}
        {visibleTags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {visibleTags.map(tag => (
              <Badge key={tag} variant="outline" className="text-[10px] h-4 px-1.5">
                {tag}
              </Badge>
            ))}
            {extraTags > 0 && (
              <Badge variant="outline" className="text-[10px] h-4 px-1.5 text-muted-foreground">
                +{extraTags}
              </Badge>
            )}
          </div>
        )}

        {/* Mini SVG preview */}
        <div className="flex justify-center py-1">
          <MiniGraph nodes={group.nodes} edgePairs={group.edgePairs} />
        </div>

        {/* Description */}
        {group.description && (
          <p className="text-xs text-muted-foreground line-clamp-2">{group.description}</p>
        )}
      </CardContent>
    </Card>
  )
}
