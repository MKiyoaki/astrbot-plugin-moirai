'use client'

import { Fragment, useState, useRef } from 'react'
import { Lock, Unlock, Pencil, Trash2, GitBranch, ChevronDown, ChevronRight, Archive } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Checkbox } from '@/components/ui/checkbox'
import { TableCell, TableRow } from '@/components/ui/table'
import { useApp } from '@/lib/store'
import type { ApiEvent } from '@/lib/api'
import { cn, parseSummaryTopics } from '@/lib/utils'

// Deterministic thread color from event id (reuse same palette as landing)
const THREAD_COLORS = [
  'border-l-rose-500', 'border-l-amber-500', 'border-l-sky-500',
  'border-l-violet-500', 'border-l-emerald-500',
]
function threadColor(id: string) {
  let h = 0
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) & 0xffffffff
  return THREAD_COLORS[Math.abs(h) % THREAD_COLORS.length]
}

interface EventRowProps {
  ev: ApiEvent
  expanded: boolean
  editMode: boolean
  selected: boolean
  sudoMode: boolean
  activeTags: Set<string>
  lang: string
  onToggleExpand: (id: string) => void
  onToggleSelect: (id: string) => void
  onEdit: (ev: ApiEvent) => void
  onDelete: (ev: ApiEvent) => void
  onLockToggle: (ev: ApiEvent) => void
  onArchive?: (ev: ApiEvent) => void
  onGoToEvents: (id: string) => void
  onTagClick: (tag: string) => void
}

export function EventRow({
  ev, expanded, editMode, selected, sudoMode, activeTags, lang,
  onToggleExpand, onToggleSelect, onEdit, onDelete, onLockToggle, onArchive, onGoToEvents, onTagClick,
}: EventRowProps) {
  const { i18n } = useApp()
  const color = threadColor(ev.id)

  return (
    <Fragment>
      <TableRow
        className={cn(
          'cursor-pointer transition-colors border-b border-border/40',
          expanded && `border-l-2 ${color}`,
          ev.is_locked && 'bg-primary/[0.02]',
        )}
        onClick={() => editMode ? onToggleSelect(ev.id) : onToggleExpand(ev.id)}
      >
        {editMode && (
          <TableCell className="w-8 pr-0" onClick={e => { e.stopPropagation(); onToggleSelect(ev.id) }}>
            <Checkbox checked={selected} onCheckedChange={() => onToggleSelect(ev.id)} />
          </TableCell>
        )}
        <TableCell className="w-4 pr-0 text-muted-foreground/40">
          {!editMode && (expanded
            ? <ChevronDown className="size-3.5" />
            : <ChevronRight className="size-3.5" />)}
        </TableCell>
        <TableCell className="max-w-60 font-medium text-sm">
          <div className="flex items-center gap-1.5 truncate">
            {ev.is_locked && <Lock className="size-3 text-accent-foreground shrink-0" />}
            <span className="truncate">{ev.topic || ev.content || ev.id}</span>
          </div>
        </TableCell>
        <TableCell className="text-xs text-muted-foreground">{ev.group || i18n.events.privateChat}</TableCell>
        <TableCell className="text-xs text-muted-foreground font-mono">
          {new Date(ev.start).toLocaleDateString(lang === 'zh' ? 'zh-CN' : lang === 'ja' ? 'ja-JP' : 'en-US')}
        </TableCell>
        <TableCell className="text-xs font-mono">
          <span className={cn(
            ev.salience > 0.7 ? 'text-accent-foreground font-bold' : 'text-muted-foreground'
          )}>
            {(ev.salience * 100).toFixed(0)}%
          </span>
        </TableCell>
        <TableCell>
          <div className="flex flex-wrap gap-1">
            {(ev.tags || []).slice(0, 3).map(t => (
              <Badge
                key={t}
                variant={activeTags.has(t) ? 'default' : 'secondary'}
                className="cursor-pointer text-[9px] px-1.5 py-0 h-4 font-normal"
                onClick={(e) => { e.stopPropagation(); onTagClick(t) }}
              >
                #{t}
              </Badge>
            ))}
          </div>
        </TableCell>
        {!editMode && (
          <TableCell className="text-right">
            <Button
              variant="ghost" size="icon"
              className="size-7 text-muted-foreground/40 hover:text-destructive"
              onClick={(e) => { e.stopPropagation(); onDelete(ev) }}
            >
              <Trash2 className="size-3.5" />
            </Button>
          </TableCell>
        )}
      </TableRow>

      {expanded && (
        <TableRow className={cn('border-l-2', color)}>
          <TableCell colSpan={editMode ? 8 : 7} className="py-0 px-0">
            <EventDetailPanel
              ev={ev} sudoMode={sudoMode} lang={lang}
              onGoToEvents={onGoToEvents} onEdit={onEdit}
              onDelete={onDelete} onLockToggle={onLockToggle} onArchive={onArchive}
            />
          </TableCell>
        </TableRow>
      )}
    </Fragment>
  )
}

function EventDetailPanel({
  ev, sudoMode, lang, onGoToEvents, onEdit, onDelete, onLockToggle, onArchive,
}: {
  ev: ApiEvent; sudoMode: boolean; lang: string
  onGoToEvents: (id: string) => void
  onEdit: (ev: ApiEvent) => void
  onDelete: (ev: ApiEvent) => void
  onLockToggle: (ev: ApiEvent) => void
  onArchive?: (ev: ApiEvent) => void
}) {
  const { i18n } = useApp()
  const [pendingArchive, setPendingArchive] = useState(false)
  const archiveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const topics = parseSummaryTopics(ev.summary)

  return (
    <div className="mx-4 my-3 rounded-lg border border-border/50 bg-background p-4 space-y-3">
      {/* Meta row */}
      <div className="flex flex-wrap gap-x-8 gap-y-1.5">
        <MetaItem label="ID" value={<span className="font-mono text-[10px]">{ev.id}</span>} />
        <MetaItem label={i18n.events.confidence} value={`${(ev.confidence * 100).toFixed(0)}%`} />
        <MetaItem label={i18n.common.status} value={
          <span className="flex items-center gap-1">
            {ev.is_locked && <Lock className="size-3 text-accent-foreground" />}
            {ev.is_locked ? i18n.events.lockedMemory : i18n.common.all}
          </span>
        } />
        {(ev.participants?.length ?? 0) > 0 && (
          <MetaItem label={i18n.events.participants} value={ev.participants!.join(', ')} />
        )}
      </div>

      {/* Summary */}
      {ev.summary && (
        <div className="border-l-2 border-accent-foreground/30 pl-3 space-y-1.5">
          {topics ? topics.map((tp, i) => (
            <div key={i} className="space-y-1 text-xs">
              {i > 0 && <div className="border-t border-border/30 my-1.5" />}
              {([
                [i18n.events.summaryWhat, tp.what],
                [i18n.events.summaryWho, tp.who],
                [i18n.events.summaryHow, tp.how],
                [i18n.events.summaryEval, tp.eval ?? i18n.events.summaryEvalNone],
              ] as [string, string][]).map(([label, val]) => (
                <div key={label} className="flex gap-2 leading-snug">
                  <span className="text-[9px] uppercase font-mono tracking-wider text-accent-foreground/60 w-12 shrink-0 pt-0.5">{label}</span>
                  <span className="text-foreground/80">{val}</span>
                </div>
              ))}
            </div>
          )) : (
            <p className="text-xs text-muted-foreground">{ev.summary}</p>
          )}
        </div>
      )}

      {/* Inherit chain */}
      {(ev.inherit_from?.length ?? 0) > 0 && (
        <div className="flex flex-wrap gap-1">
          <span className="text-[9px] uppercase font-mono tracking-wider text-muted-foreground mr-1">{i18n.events.inheritFrom}</span>
          {ev.inherit_from!.map(id => (
            <Badge key={id} variant="outline" className="cursor-pointer text-[9px]" onClick={() => onGoToEvents(id)}>
              {id.slice(0, 12)}…
            </Badge>
          ))}
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2 pt-1 flex-wrap">
        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => onGoToEvents(ev.id)}>
          <GitBranch className="mr-1.5 size-3" />{lang === 'zh' ? '事件流' : 'Events'}
        </Button>
        <Button size="sm" variant="outline" className="h-7 text-xs" disabled={!sudoMode} onClick={() => onLockToggle(ev)}>
          {ev.is_locked ? <Unlock className="mr-1.5 size-3" /> : <Lock className="mr-1.5 size-3" />}
          {ev.is_locked ? i18n.events.unlock : i18n.events.lock}
        </Button>
        {onArchive && (
          <Button
            size="sm"
            variant={pendingArchive ? 'default' : 'outline'}
            className={`h-7 text-xs transition-colors ${pendingArchive ? 'bg-amber-500 hover:bg-amber-600 border-amber-500 text-white' : ''}`}
            disabled={!sudoMode || ev.is_locked || ev.status === 'archived'}
            onClick={() => {
              if (!pendingArchive) {
                setPendingArchive(true)
                archiveTimerRef.current = setTimeout(() => setPendingArchive(false), 3000)
              } else {
                if (archiveTimerRef.current) clearTimeout(archiveTimerRef.current)
                setPendingArchive(false)
                onArchive(ev)
              }
            }}
          >
            <Archive className="mr-1.5 size-3" />
            {pendingArchive ? i18n.common.confirm : i18n.events.archive}
          </Button>
        )}
        <Button size="sm" variant="ghost" className="h-7 text-xs" disabled={!sudoMode} onClick={() => onEdit(ev)}>
          <Pencil className="mr-1.5 size-3" />{i18n.common.edit}
        </Button>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <span>
                <Button
                  size="sm" variant="ghost"
                  className="h-7 text-xs text-destructive hover:text-destructive hover:bg-destructive/10"
                  disabled={!sudoMode || ev.is_locked}
                  onClick={() => onDelete(ev)}
                >
                  <Trash2 className="mr-1.5 size-3" />{i18n.common.delete}
                </Button>
              </span>
            </TooltipTrigger>
            {ev.is_locked && <TooltipContent><p>{i18n.events.lockedDeleteHint}</p></TooltipContent>}
          </Tooltip>
        </TooltipProvider>
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
