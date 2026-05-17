'use client'

import { ChevronLeft, Pencil, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import type { PersonaNode, ImpressionEdge } from '@/lib/api'
import type { EdgePair } from '@/lib/graph-types'
import { useApp } from '@/lib/store'
import { getLocalizedOrientation } from '@/lib/i18n'

interface EdgeDetailProps {
  pairKey: string
  edgePairs: EdgePair[]
  allNodes: PersonaNode[]
  onBack: () => void
  onEditForward: (edge: ImpressionEdge) => void
  onEditBackward: (edge: ImpressionEdge) => void
  onDelete: (edge: ImpressionEdge) => void
  onJumpToEvent: (eventId: string) => void
  sudoMode: boolean
}

export function EdgeDetail({
  pairKey,
  edgePairs,
  allNodes,
  onBack,
  onEditForward,
  onEditBackward,
  onDelete,
  onJumpToEvent,
  sudoMode,
}: EdgeDetailProps) {
  const { i18n } = useApp()
  const t = i18n.graph
  const td = i18n.graph.detail
  const pair = edgePairs.find(p => p.pairKey === pairKey)
  const nodeMap = new Map(allNodes.map(n => [n.data.id, n]))

  if (!pair) return (
    <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
      未找到边数据
    </div>
  )

  const srcNode = nodeMap.get(pair.srcId)
  const tgtNode = nodeMap.get(pair.tgtId)
  const srcLabel = srcNode?.data.label ?? pair.srcId
  const tgtLabel = tgtNode?.data.label ?? pair.tgtId

  const combinedAffect = pair.isBidirectional && pair.bwd
    ? (pair.fwd.data.affect + pair.bwd.data.affect) / 2
    : pair.fwd.data.affect

  const combinedPower = pair.isBidirectional && pair.bwd
    ? (pair.fwd.data.power + pair.bwd.data.power) / 2
    : pair.fwd.data.power

  return (
    <div className="flex h-full flex-col overflow-hidden text-sm">
      {/* Header */}
      <div className="shrink-0 border-b px-3 py-2 flex items-center gap-2">
        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onBack}>
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="text-xs text-muted-foreground flex-1">{td.backToParams}</span>
      </div>

      <ScrollArea className="flex-1">
        <div className="px-3 py-2 space-y-3">
          {/* Summary */}
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant={pair.isBidirectional ? 'default' : 'secondary'} className="text-xs">
              {pair.isBidirectional ? td.bidirectional : td.unidirectional}
            </Badge>
            {pair.totalMsgs > 1 && (
              <span className="text-xs text-muted-foreground">
                {td.totalMsgs}: {pair.totalMsgs}
              </span>
            )}
          </div>

          {/* A → B section */}
          <ImpressionSection
            label={`${srcLabel} → ${tgtLabel}`}
            edge={pair.fwd}
            onEdit={sudoMode ? () => onEditForward(pair.fwd) : undefined}
            onDelete={sudoMode ? () => onDelete(pair.fwd) : undefined}
            onJumpToEvent={onJumpToEvent}
            t={t}
            i18n={i18n}
          />

          {/* B → A section (bidirectional only) */}
          {pair.isBidirectional && pair.bwd && (
            <>
              <Separator />
              <ImpressionSection
                label={`${tgtLabel} → ${srcLabel}`}
                edge={pair.bwd}
                onEdit={sudoMode ? () => onEditBackward(pair.bwd!) : undefined}
                onDelete={sudoMode ? () => onDelete(pair.bwd!) : undefined}
                onJumpToEvent={onJumpToEvent}
                t={t}
                i18n={i18n}
              />
            </>
          )}

          {/* Combined affect & power (bidirectional only) */}
          {pair.isBidirectional && (
            <>
              <Separator />
              <div className="space-y-2">
                <div>
                  <p className="text-xs text-muted-foreground mb-1">{td.combinedAffect}</p>
                  <AffectBar value={combinedAffect} axisLabels={[t.axes.negative, t.axes.positive]} />
                </div>
                <div>
                  <p className="text-xs text-muted-foreground mb-1">{td.combinedPower}</p>
                  <AffectBar value={combinedPower} axisLabels={[t.axes.submissive, t.axes.dominant]} />
                </div>
              </div>
            </>
          )}
        </div>
      </ScrollArea>
    </div>
  )
}

// ── ImpressionSection ─────────────────────────────────────────────────────────

function ImpressionSection({
  label,
  edge,
  onEdit,
  onDelete,
  onJumpToEvent,
  t,
  i18n,
}: {
  label: string
  edge: ImpressionEdge
  onEdit?: () => void
  onDelete?: () => void
  onJumpToEvent: (eventId: string) => void
  t: any
  i18n: any
}) {
  const msgCount = (edge.data as { msg_count?: number }).msg_count
  const lastReinforced = edge.data.last_reinforced_at
    ? new Date(edge.data.last_reinforced_at).toLocaleDateString('zh-CN', { dateStyle: 'short' })
    : '—'
  const evidenceIds = edge.data.evidence_event_ids || []

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium truncate">{label}</p>
        <div className="flex shrink-0 items-center gap-1">
          {onEdit && (
            <Button variant="ghost" size="icon" className="size-5" onClick={onEdit}>
              <Pencil className="size-3" />
            </Button>
          )}
          {onDelete && (
            <Button variant="ghost" size="icon" className="size-5" onClick={onDelete}>
              <Trash2 className="size-3" />
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <Field label={t.relationType} value={getLocalizedOrientation(edge.data.label, i18n)} />
        <Field label={t.intensity} value={`${(edge.data.intensity * 100).toFixed(0)}%`} />
        <Field label={t.scope} value={edge.data.scope} />
        {msgCount != null && <Field label={i18n.graph.detail.msgCount} value={String(msgCount)} />}
        <Field label={i18n.graph.detail.lastActive} value={lastReinforced} />
      </div>

      {/* Confidence Indicator */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-[10px] text-muted-foreground">
          <span>{t.confidence}</span>
          <span className="font-mono">{(edge.data.confidence * 100).toFixed(0)}%</span>
        </div>
        <div className="h-1 w-full bg-muted rounded-full overflow-hidden border border-border/50">
          <div 
            className="h-full bg-primary transition-all duration-500" 
            style={{ width: `${edge.data.confidence * 100}%` }}
          />
        </div>
      </div>

      <AffectBar value={edge.data.affect} label={t.affect} axisLabels={[t.axes.negative, t.axes.positive]} />
      <AffectBar value={edge.data.power} label={t.power} axisLabels={[t.axes.submissive, t.axes.dominant]} />
      {edge.data.r_squared != null && (
        <p className="text-[10px] text-muted-foreground">
          {t.ipcFit} = {edge.data.r_squared.toFixed(2)}
        </p>
      )}

      {evidenceIds.length > 0 && (
        <div className="space-y-1 pt-1">
          <p className="text-[10px] text-muted-foreground">{t.evidenceEvents}</p>
          <div className="flex flex-wrap gap-1">
            {evidenceIds.map(id => (
              <Button
                key={id}
                variant="outline"
                className="h-5 px-1.5 text-[10px] font-mono"
                onClick={() => onJumpToEvent(id)}
              >
                {id.slice(0, 8)}
              </Button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── AffectBar ────────────────────────────────────────────────────────────────

function AffectBar({ value, label, axisLabels }: { value: number; label?: string; axisLabels?: [string, string] }) {
  const { i18n } = useApp()
  const t = i18n.graph.axes
  const clampedVal = Math.max(-1, Math.min(1, value))
  const color = clampedVal > 0.15
    ? 'bg-green-500'
    : clampedVal < -0.05
    ? 'bg-red-500'
    : 'bg-muted-foreground'

  const leftPct = clampedVal >= 0
    ? 50
    : (0.5 + clampedVal / 2) * 100
  const widthPct = Math.abs(clampedVal) * 50

  return (
    <div>
      {label && <p className="text-[10px] text-muted-foreground mb-0.5">{label}</p>}
      <div className="relative h-1.5 rounded-full bg-muted overflow-hidden border">
        <div
          className={`absolute top-0 h-full rounded-full ${color}`}
          style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
        />
        {/* Center tick */}
        <div className="absolute top-0 h-full w-px bg-border left-1/2" />
      </div>
      <div className="flex justify-between mt-0.5">
        <span className="text-[8px] text-red-500">{axisLabels?.[0] ?? t.negative}</span>
        <span
          className={`text-[9px] font-mono ${clampedVal > 0.15 ? 'text-green-600' : clampedVal < -0.05 ? 'text-red-500' : 'text-muted-foreground'}`}
        >
          {clampedVal >= 0 ? '+' : ''}{clampedVal.toFixed(2)}
        </span>
        <span className="text-[8px] text-green-500">{axisLabels?.[1] ?? t.positive}</span>
      </div>
    </div>
  )
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-muted-foreground">{label}</p>
      <p className="font-medium">{value}</p>
    </div>
  )
}
