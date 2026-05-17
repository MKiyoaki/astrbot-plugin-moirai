'use client'

import { Fragment } from 'react'
import { Network, Pencil, Trash2, ChevronDown, ChevronRight } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { TableCell, TableRow } from '@/components/ui/table'
import { useApp } from '@/lib/store'
import type { PersonaNode } from '@/lib/api'
import { cn } from '@/lib/utils'

interface PersonaRowProps {
  node: PersonaNode
  expanded: boolean
  editMode: boolean
  selected: boolean
  sudoMode: boolean
  activeTags: Set<string>
  onToggleExpand: (id: string) => void
  onToggleSelect: (id: string) => void
  onEdit: (node: PersonaNode) => void
  onDelete: (id: string, label: string) => void
  onGoToGraph: (uid: string) => void
  onTagClick: (tag: string) => void
}

export function PersonaRow({
  node, expanded, editMode, selected, sudoMode, activeTags,
  onToggleExpand, onToggleSelect, onEdit, onDelete, onGoToGraph, onTagClick,
}: PersonaRowProps) {
  const d = node.data
  const bigFiveSummary = d.attrs?.big_five
    ? (['O', 'C', 'E', 'A', 'N'] as const)
        .filter(dim => d.attrs?.big_five?.[dim] !== undefined)
        .map(dim => {
          const v = d.attrs!.big_five![dim]!
          return `${dim}${Math.round((v + 1) / 2 * 100)}%`
        }).join(' ')
    : null

  return (
    <Fragment>
      <TableRow
        className={cn(
          'cursor-pointer transition-colors border-b border-border/40',
          expanded && 'border-l-2 border-l-violet-500',
        )}
        onClick={() => editMode ? onToggleSelect(d.id) : onToggleExpand(d.id)}
      >
        {editMode && (
          <TableCell className="w-8 pr-0" onClick={e => { e.stopPropagation(); onToggleSelect(d.id) }}>
            <Checkbox checked={selected} onCheckedChange={() => onToggleSelect(d.id)} />
          </TableCell>
        )}
        <TableCell className="w-4 pr-0 text-muted-foreground/40">
          {!editMode && (expanded
            ? <ChevronDown className="size-3.5" />
            : <ChevronRight className="size-3.5" />)}
        </TableCell>
        <TableCell className="font-medium text-sm">
          <div className="flex items-center gap-1.5">
            <span>{d.label}</span>
            {d.is_bot && (
              <Badge variant="secondary" className="text-[9px] px-1.5 py-0 h-4 font-normal">Bot</Badge>
            )}
          </div>
        </TableCell>
        <TableCell className="max-w-48 text-xs text-muted-foreground truncate">
          {d.attrs?.description || '—'}
        </TableCell>
        <TableCell className="text-xs font-mono text-muted-foreground">
          {bigFiveSummary || '—'}
        </TableCell>
        <TableCell className="text-xs font-mono">
          <span className={cn(
            d.confidence > 0.7 ? 'text-accent-foreground font-bold' : 'text-muted-foreground'
          )}>
            {(d.confidence * 100).toFixed(0)}%
          </span>
        </TableCell>
        <TableCell>
          <div className="flex flex-wrap gap-1">
            {(d.attrs?.content_tags || []).slice(0, 3).map(t => (
              <Badge
                key={t}
                variant={activeTags.has(t) ? 'default' : 'secondary'}
                className="cursor-pointer text-[9px] px-1.5 py-0 h-4 font-normal"
                onClick={e => { e.stopPropagation(); onTagClick(t) }}
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
              onClick={e => { e.stopPropagation(); onDelete(d.id, d.label) }}
            >
              <Trash2 className="size-3.5" />
            </Button>
          </TableCell>
        )}
      </TableRow>

      {expanded && (
        <TableRow className="border-l-2 border-l-violet-500">
          <TableCell colSpan={editMode ? 8 : 7} className="py-0 px-0">
            <PersonaDetailPanel
              node={node} sudoMode={sudoMode}
              onGoToGraph={onGoToGraph} onEdit={onEdit} onDelete={onDelete}
            />
          </TableCell>
        </TableRow>
      )}
    </Fragment>
  )
}

function PersonaDetailPanel({
  node, sudoMode, onGoToGraph, onEdit, onDelete,
}: {
  node: PersonaNode; sudoMode: boolean
  onGoToGraph: (uid: string) => void
  onEdit: (node: PersonaNode) => void
  onDelete: (id: string, label: string) => void
}) {
  const { i18n } = useApp()
  const d = node.data
  const attrs = d.attrs || {}

  return (
    <div className="mx-4 my-3 rounded-lg border border-border/50 bg-background p-4 space-y-3">
      {/* Meta row */}
      <div className="flex flex-wrap gap-x-8 gap-y-1.5">
        <MetaItem label="UID" value={<span className="font-mono text-[10px]">{d.id}</span>} />
        <MetaItem label={i18n.graph.confidence} value={`${(d.confidence * 100).toFixed(0)}%`} />
        {d.is_bot && <MetaItem label={i18n.graph.isBot} value="✓" />}
        {(d.bound_identities?.length ?? 0) > 0 && (
          <MetaItem
            label={i18n.graph.bindings}
            value={
              <div className="flex flex-wrap gap-1 mt-0.5">
                {d.bound_identities!.map(b => (
                  <Badge key={`${b.platform}:${b.physical_id}`} variant="outline" className="text-[9px] px-1.5 py-0 h-4">
                    {b.platform}:{b.physical_id}
                  </Badge>
                ))}
              </div>
            }
          />
        )}
      </div>

      {/* Personality block */}
      {(attrs.description || attrs.big_five) && (
        <div className="border-l-2 border-accent-foreground/30 pl-3 space-y-2">
          {attrs.description && (
            <p className="text-xs text-foreground/80 leading-relaxed">{attrs.description}</p>
          )}
          {attrs.big_five && (
            <div className="flex flex-col gap-1.5">
              {(['O', 'C', 'E', 'A', 'N'] as const).map(dim => {
                const val = attrs.big_five?.[dim]
                if (val === undefined) return null
                const score = Math.round((val + 1) / 2 * 100)
                const evText = attrs.big_five_evidence && typeof attrs.big_five_evidence === 'object'
                  ? (attrs.big_five_evidence as Record<string, string>)[dim]
                  : undefined
                return (
                  <div key={dim} className="space-y-0.5 text-xs">
                    <div className="flex items-center gap-2">
                      <span className="text-[9px] uppercase font-mono tracking-wider text-accent-foreground/60 w-12 shrink-0">
                        {i18n.graph.bigFive[dim as keyof typeof i18n.graph.bigFive]}
                      </span>
                      <div className="flex-1 h-1 rounded-full bg-muted overflow-hidden">
                        <div
                          className={cn('h-full rounded-full', score >= 65 ? 'bg-emerald-500' : score <= 35 ? 'bg-rose-500' : 'bg-muted-foreground/50')}
                          style={{ width: `${score}%` }}
                        />
                      </div>
                      <span className={cn(
                        'font-mono text-[10px] w-8 text-right',
                        score >= 65 ? 'text-emerald-500' : score <= 35 ? 'text-rose-500' : 'text-muted-foreground'
                      )}>
                        {score}%
                      </span>
                    </div>
                    {evText && <p className="text-[10px] italic text-muted-foreground leading-snug pl-14">{evText}</p>}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2 pt-1">
        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => onGoToGraph(d.id)}>
          <Network className="mr-1.5 size-3" />{i18n.graph.graphView}
        </Button>
        <Button size="sm" variant="ghost" className="h-7 text-xs" disabled={!sudoMode} onClick={() => onEdit(node)}>
          <Pencil className="mr-1.5 size-3" />{i18n.common.edit}
        </Button>
        <Button
          size="sm" variant="ghost"
          className="h-7 text-xs text-destructive hover:text-destructive hover:bg-destructive/10"
          disabled={!sudoMode}
          onClick={() => onDelete(d.id, d.label)}
        >
          <Trash2 className="mr-1.5 size-3" />{i18n.common.delete}
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
