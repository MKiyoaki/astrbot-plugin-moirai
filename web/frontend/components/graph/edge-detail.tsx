'use client'

import { ChevronLeft, Pencil } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import type { PersonaNode, ImpressionEdge } from '@/lib/api'
import type { EdgePair } from '@/lib/graph-types'
import { i18n } from '@/lib/i18n'

const t = i18n.graph
const td = i18n.graph.detail

interface EdgeDetailProps {
  pairKey: string
  edgePairs: EdgePair[]
  allNodes: PersonaNode[]
  onBack: () => void
  onEditForward: (edge: ImpressionEdge) => void
  onEditBackward: (edge: ImpressionEdge) => void
  sudoMode: boolean
}

export function EdgeDetail({
  pairKey,
  edgePairs,
  allNodes,
  onBack,
  onEditForward,
  onEditBackward,
  sudoMode,
}: EdgeDetailProps) {
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
          />

          {/* B → A section (bidirectional only) */}
          {pair.isBidirectional && pair.bwd && (
            <>
              <Separator />
              <ImpressionSection
                label={`${tgtLabel} → ${srcLabel}`}
                edge={pair.bwd}
                onEdit={sudoMode ? () => onEditBackward(pair.bwd!) : undefined}
              />
            </>
          )}

          {/* Combined affect (bidirectional only) */}
          {pair.isBidirectional && (
            <>
              <Separator />
              <div>
                <p className="text-xs text-muted-foreground mb-1">{td.combinedAffect}</p>
                <AffectBar value={combinedAffect} />
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
}: {
  label: string
  edge: ImpressionEdge
  onEdit?: () => void
}) {
  const msgCount = (edge.data as { msg_count?: number }).msg_count
  const lastReinforced = edge.data.last_reinforced_at
    ? new Date(edge.data.last_reinforced_at).toLocaleDateString('zh-CN', { dateStyle: 'short' })
    : '—'

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium truncate">{label}</p>
        {onEdit && (
          <Button variant="ghost" size="icon" className="h-5 w-5 shrink-0" onClick={onEdit}>
            <Pencil className="h-3 w-3" />
          </Button>
        )}
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <Field label={t.relationType} value={edge.data.label} />
        <Field label={t.confidence} value={`${(edge.data.confidence * 100).toFixed(0)}%`} />
        <Field label={t.intensity} value={`${(edge.data.intensity * 100).toFixed(0)}%`} />
        <Field label={t.scope} value={edge.data.scope} />
        {msgCount != null && <Field label={i18n.graph.detail.msgCount} value={String(msgCount)} />}
        <Field label={i18n.graph.detail.lastActive} value={lastReinforced} />
      </div>

      <AffectBar value={edge.data.affect} label={t.affect} />
    </div>
  )
}

// ── AffectBar ────────────────────────────────────────────────────────────────

function AffectBar({ value, label }: { value: number; label?: string }) {
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
        <span className="text-[8px] text-red-500">消极</span>
        <span
          className={`text-[9px] font-mono ${clampedVal > 0.15 ? 'text-green-600' : clampedVal < -0.05 ? 'text-red-500' : 'text-muted-foreground'}`}
        >
          {clampedVal >= 0 ? '+' : ''}{clampedVal.toFixed(2)}
        </span>
        <span className="text-[8px] text-green-500">积极</span>
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
