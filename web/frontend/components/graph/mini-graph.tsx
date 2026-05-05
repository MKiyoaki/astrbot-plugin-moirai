'use client'

import type { PersonaNode } from '@/lib/api'
import type { EdgePair } from '@/lib/graph-types'
import { circularLayout } from '@/lib/graph-utils'

interface MiniGraphProps {
  nodes: PersonaNode[]
  edgePairs: EdgePair[]
  width?: number
  height?: number
}

export function MiniGraph({ nodes, edgePairs, width = 260, height = 60 }: MiniGraphProps) {
  if (nodes.length === 0) return (
    <svg width={width} height={height} className="rounded opacity-40" />
  )

  const cx = width / 2
  const cy = height / 2
  const r = Math.min(width, height) * 0.36
  const positions = circularLayout(nodes, cx, cy, r)

  return (
    <svg
      width={width}
      height={height}
      className="rounded"
      style={{ overflow: 'visible' }}
    >
      {/* Edges */}
      {edgePairs.map(pair => {
        const pa = positions[pair.srcId]
        const pb = positions[pair.tgtId]
        if (!pa || !pb) return null
        return (
          <line
            key={pair.pairKey}
            x1={pa.x} y1={pa.y}
            x2={pb.x} y2={pb.y}
            stroke="currentColor"
            strokeWidth={0.8}
            strokeOpacity={0.5}
          />
        )
      })}
      {/* Nodes */}
      {nodes.map(node => {
        const p = positions[node.data.id]
        if (!p) return null
        return (
          <circle
            key={node.data.id}
            cx={p.x}
            cy={p.y}
            r={3.5}
            fill={node.data.is_bot ? '#fce4ec' : '#e8e8e8'}
            stroke={node.data.is_bot ? '#e91e8c' : 'currentColor'}
            strokeWidth={node.data.is_bot ? 1 : 0.5}
            opacity={0.85}
          />
        )
      })}
    </svg>
  )
}
