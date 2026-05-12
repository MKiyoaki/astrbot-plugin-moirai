'use client'

import { Fragment } from 'react'
import { Building2, MessageSquare, Activity, ChevronDown, ChevronRight } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { TableCell, TableRow } from '@/components/ui/table'
import { useApp } from '@/lib/store'
import type { PersonaNode } from '@/lib/api'
import { cn } from '@/lib/utils'

export interface GroupInfo {
  id: string
  displayName: string
  type: 'group' | 'private'
  event_count: number
  last_active?: string
  participants: string[]
}

interface GroupRowProps {
  group: GroupInfo
  personas: PersonaNode[]
  expanded: boolean
  lang: string
  onToggleExpand: (id: string) => void
  onGoToEvents: (gid: string) => void
}

export function GroupRow({
  group, personas, expanded, lang, onToggleExpand, onGoToEvents,
}: GroupRowProps) {
  const { i18n } = useApp()
  const isGroup = group.type === 'group'

  return (
    <Fragment>
      <TableRow
        className={cn(
          'cursor-pointer transition-colors border-b border-border/40',
          expanded && 'border-l-2 border-l-sky-500',
        )}
        onClick={() => onToggleExpand(group.id)}
      >
        <TableCell className="w-4 pr-0 text-muted-foreground/40">
          {expanded
            ? <ChevronDown className="size-3.5" />
            : <ChevronRight className="size-3.5" />}
        </TableCell>
        <TableCell className="font-medium text-sm">
          <div className="flex items-center gap-2">
            {isGroup
              ? <Building2 className="size-3.5 text-muted-foreground/60 shrink-0" />
              : <MessageSquare className="size-3.5 text-muted-foreground/60 shrink-0" />}
            <span className="font-mono">{group.displayName || group.id}</span>
            <Badge variant="outline" className="text-[9px] px-1.5 py-0 h-4 font-normal ml-1">
              {isGroup ? i18n.events.group : i18n.events.privateChat}
            </Badge>
          </div>
        </TableCell>
        <TableCell className="text-xs font-mono text-muted-foreground">
          {group.event_count}
        </TableCell>
        <TableCell className="text-xs text-muted-foreground font-mono">
          {group.last_active
            ? new Date(group.last_active).toLocaleDateString(
                lang === 'zh' ? 'zh-CN' : lang === 'ja' ? 'ja-JP' : 'en-US'
              )
            : '—'}
        </TableCell>
      </TableRow>

      {expanded && (
        <TableRow className="border-l-2 border-l-sky-500">
          <TableCell colSpan={4} className="py-0 px-0">
            <GroupDetailPanel
              group={group} personas={personas}
              onGoToEvents={onGoToEvents}
            />
          </TableCell>
        </TableRow>
      )}
    </Fragment>
  )
}

function GroupDetailPanel({
  group, personas, onGoToEvents,
}: {
  group: GroupInfo
  personas: PersonaNode[]
  onGoToEvents: (gid: string) => void
}) {
  const { i18n } = useApp()
  const members = personas.filter(p => group.participants.includes(p.data.id))
  const platforms = Array.from(
    new Set(members.flatMap(p => p.data.bound_identities?.map(b => b.platform) ?? []))
  )

  return (
    <div className="mx-4 my-3 rounded-lg border border-border/50 bg-background p-4 space-y-3">
      {/* Meta row */}
      <div className="flex flex-wrap gap-x-8 gap-y-1.5">
        <MetaItem label="ID" value={<span className="font-mono text-[10px] break-all">{group.id}</span>} />
        <MetaItem
          label={i18n.library.groups.type}
          value={group.type === 'group' ? i18n.events.group : i18n.events.privateChat}
        />
        <MetaItem label={i18n.library.groups.events} value={String(group.event_count)} />
        {platforms.length > 0 && (
          <MetaItem
            label={i18n.library.groups.platform}
            value={
              <div className="flex flex-wrap gap-1 mt-0.5">
                {platforms.map(p => (
                  <Badge key={p} variant="outline" className="text-[9px] px-1.5 py-0 h-4 uppercase">
                    {p}
                  </Badge>
                ))}
              </div>
            }
          />
        )}
      </div>

      {/* Participants */}
      <div className="border-l-2 border-accent-foreground/30 pl-3 space-y-1.5">
        <span className="text-[9px] uppercase font-mono tracking-wider text-muted-foreground">
          {i18n.events.participants}
        </span>
        <div className="flex flex-wrap gap-1.5">
          {members.length === 0 ? (
            <span className="text-xs text-muted-foreground italic">{i18n.library.groups.noParticipants}</span>
          ) : members.map(p => (
            <Badge key={p.data.id} variant="secondary" className="text-[10px] px-2 py-0.5 h-5">
              {p.data.label}
              {p.data.is_bot && <span className="ml-1 opacity-50 text-[9px]">Bot</span>}
            </Badge>
          ))}
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-2 pt-1">
        <Button
          size="sm" variant="outline" className="h-7 text-xs"
          onClick={() => onGoToEvents(group.type === 'group' ? group.id : '')}
        >
          <Activity className="mr-1.5 size-3" />{i18n.library.groups.viewEvents}
        </Button>
      </div>
    </div>
  )
}

function MetaItem({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[9px] uppercase font-mono tracking-wider text-muted-foreground">{label}</span>
      <span className="text-xs text-foreground">{value}</span>
    </div>
  )
}
