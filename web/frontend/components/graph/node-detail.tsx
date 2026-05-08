'use client'

import { ChevronLeft, Pencil, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import type { PersonaNode } from '@/lib/api'
import type { EdgePair } from '@/lib/graph-types'
import { useApp } from '@/lib/store'

interface NodeDetailProps {
  node: PersonaNode
  allNodes: PersonaNode[]
  edgePairs: EdgePair[]
  onBack: () => void
  onEdit: (node: PersonaNode) => void
  onDelete: (uid: string, name: string) => void
  sudoMode: boolean
}

export function NodeDetail({ node, allNodes, edgePairs, onBack, onEdit, onDelete, sudoMode }: NodeDetailProps) {
  const { i18n } = useApp()
  const t = i18n.graph
  const td = i18n.graph.detail
  const nodeMap = new Map(allNodes.map(n => [n.data.id, n]))

  const connectedEdges = edgePairs.filter(p => p.srcId === node.data.id || p.tgtId === node.data.id)

  const lastActive = node.data.last_active_at
    ? new Date(node.data.last_active_at).toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' })
    : '—'

  const msgCount = (node.data as { msg_count?: number }).msg_count ?? null

  return (
    <div className="flex h-full flex-col overflow-hidden text-sm">
      {/* Header */}
      <div className="shrink-0 border-b px-3 py-2 flex items-center gap-2">
        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onBack}>
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="text-xs text-muted-foreground flex-1">{td.backToParams}</span>
        {sudoMode && (
          <>
            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => onEdit(node)}>
              <Pencil className="h-3.5 w-3.5" />
            </Button>
            <Button variant="ghost" size="icon" className="h-6 w-6 text-destructive hover:text-destructive"
              onClick={() => onDelete(node.data.id, node.data.label)}>
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </>
        )}
      </div>

      <ScrollArea className="flex-1">
        <div className="px-3 py-2 space-y-3">
          {/* Name + Bot badge */}
          <div className="flex items-center gap-2">
            <span className="font-semibold text-base">{node.data.label}</span>
            {node.data.is_bot && <Badge variant="secondary" className="text-[10px]">BOT</Badge>}
          </div>

          {/* Core fields */}
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
            <Field label={t.uid} value={<span className="font-mono text-[10px]">{node.data.id}</span>} />
            <Field label={t.confidence} value={`${(node.data.confidence * 100).toFixed(0)}%`} />
            {msgCount !== null && (
              <Field label={td.msgCount} value={String(msgCount)} />
            )}
            <Field label={td.lastActive} value={lastActive} />
          </div>

          <Separator />

          {/* Description */}
          {node.data.attrs?.description && (
            <div>
              <p className="text-xs text-muted-foreground mb-1">{t.description}</p>
              <p className="text-xs">{node.data.attrs.description}</p>
            </div>
          )}

          {/* Affect type */}
          {node.data.attrs?.affect_type && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">{t.affectType}</span>
              <Badge variant="outline" className="text-xs">{node.data.attrs.affect_type}</Badge>
            </div>
          )}

          {/* Content tags */}
          {(node.data.attrs?.content_tags?.length ?? 0) > 0 && (
            <div>
              <p className="text-xs text-muted-foreground mb-1">{t.contentTags}</p>
              <div className="flex flex-wrap gap-1">
                {(node.data.attrs.content_tags ?? []).map(tag => (
                  <Badge key={tag} variant="secondary" className="text-[10px] h-4 px-1.5">{tag}</Badge>
                ))}
              </div>
            </div>
          )}

          {/* Bound identities */}
          {(node.data.bound_identities?.length ?? 0) > 0 && (
            <div>
              <p className="text-xs text-muted-foreground mb-1">{t.bindings}</p>
              <div className="space-y-0.5">
                {node.data.bound_identities.map((b, i) => (
                  <p key={i} className="text-[10px] font-mono text-muted-foreground">
                    {b.platform}: {b.physical_id}
                  </p>
                ))}
              </div>
            </div>
          )}

          {/* Connected edges */}
          {connectedEdges.length > 0 && (
            <>
              <Separator />
              <div>
                <p className="text-xs text-muted-foreground mb-1.5">{td.connectedEdges}</p>
                <div className="space-y-1.5">
                  {connectedEdges.map(pair => {
                    const otherId = pair.srcId === node.data.id ? pair.tgtId : pair.srcId
                    const other = nodeMap.get(otherId)
                    const dirSymbol = pair.isBidirectional ? '⇄' : (pair.srcId === node.data.id ? '→' : '←')
                    const label = pair.fwd.data.label
                    const affect = pair.fwd.data.affect
                    const power  = pair.fwd.data.power
                    const affectColor = affect > 0.3 ? 'text-green-600' : affect < -0.1 ? 'text-red-500' : 'text-muted-foreground'
                    const powerColor  = power  > 0.3 ? 'text-green-600' : power  < -0.1 ? 'text-red-500' : 'text-muted-foreground'

                    return (
                      <div key={pair.pairKey} className="flex items-center gap-1.5 text-xs">
                        <span className="text-muted-foreground">{dirSymbol}</span>
                        <span className="flex-1 truncate">{other?.data.label ?? otherId}</span>
                        <Badge variant="outline" className="text-[9px] h-3.5 px-1">{label}</Badge>
                        <span className={`font-mono text-[10px] ${affectColor}`} title="B">
                          {affect >= 0 ? '+' : ''}{affect.toFixed(2)}
                        </span>
                        <span className={`font-mono text-[10px] ${powerColor}`} title="P">
                          {power >= 0 ? '+' : ''}{power.toFixed(2)}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>
            </>
          )}
        </div>
      </ScrollArea>
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
