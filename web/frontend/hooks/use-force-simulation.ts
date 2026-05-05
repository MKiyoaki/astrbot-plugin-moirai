'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import type { PersonaNode } from '@/lib/api'
import type { EdgePair, PhysicsParams, PositionMap } from '@/lib/graph-types'
import { circularLayout } from '@/lib/graph-utils'

interface UseForceSimulationOptions {
  nodes: PersonaNode[]
  edgePairs: EdgePair[]
  params: PhysicsParams
  containerSize: { width: number; height: number }
  enabled: boolean
}

interface UseForceSimulationResult {
  positions: PositionMap | null
  refresh: () => void
  isComputing: boolean
}

export function useForceSimulation({
  nodes,
  edgePairs,
  params,
  containerSize,
  enabled,
}: UseForceSimulationOptions): UseForceSimulationResult {
  const [positions, setPositions] = useState<PositionMap | null>(null)
  const [isComputing, setIsComputing] = useState(false)
  const [randSeed, setRandSeed] = useState(0)

  const refresh = useCallback(() => setRandSeed(s => s + 1), [])

  // Stable refs to avoid stale closures in the effect
  const nodesRef = useRef(nodes)
  nodesRef.current = nodes
  const edgePairsRef = useRef(edgePairs)
  edgePairsRef.current = edgePairs

  useEffect(() => {
    if (!enabled || nodes.length === 0) {
      setPositions(null)
      return
    }

    const { width, height } = containerSize
    if (width === 0 || height === 0) return

    const cx = width / 2
    const cy = height / 2
    const r = Math.min(width, height) * 0.42

    if (params.locked) {
      // Keep current positions unchanged; only update if none exist yet
      setPositions(prev => prev ?? circularLayout(nodes, cx, cy, r))
      return
    }

    if (params.layoutMode === 'circular') {
      setPositions(circularLayout(nodes, cx, cy, r))
      return
    }

    // Force-directed layout
    setIsComputing(true)
    const result = runForceAtlas2(nodes, edgePairs, params, { width, height }, randSeed)
    setPositions(result)
    setIsComputing(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    enabled,
    nodes.length,
    edgePairs.length,
    params.layoutMode,
    params.locked,
    params.scalingRatio,
    params.gravity,
    params.edgeWeightInfluence,
    params.linLog,
    params.preventOverlap,
    params.dissuadeHubs,
    params.damping,
    params.iterations,
    params.gravSource,
    params.biWeight,
    containerSize.width,
    containerSize.height,
    randSeed,
    enabled,
  ])

  return { positions, refresh, isComputing }
}

// ── ForceAtlas2 approximation ─────────────────────────────────────────────────

function runForceAtlas2(
  nodes: PersonaNode[],
  edgePairs: EdgePair[],
  params: PhysicsParams,
  size: { width: number; height: number },
  seed: number,
): PositionMap {
  const { width, height } = size
  const cx = width / 2
  const cy = height / 2

  // 1. Pre-compute degree and visual radius per node
  const degree: Record<string, number> = {}
  for (const n of nodes) degree[n.data.id] = 0
  for (const p of edgePairs) {
    degree[p.srcId] = (degree[p.srcId] ?? 0) + 1
    degree[p.tgtId] = (degree[p.tgtId] ?? 0) + 1
  }

  // Node radius mapped from degree (12–22 px)
  const degValues = Object.values(degree)
  const maxDeg = Math.max(...degValues, 1)
  const minDeg = Math.min(...degValues, 0)
  const radii: Record<string, number> = {}
  for (const n of nodes) {
    const d = degree[n.data.id] ?? 0
    const t = maxDeg === minDeg ? 0.5 : (d - minDeg) / (maxDeg - minDeg)
    radii[n.data.id] = 12 + t * 10
  }

  // 2. Random initial positions (seeded via simple LCG for reproducibility)
  const pos: PositionMap = {}
  let rng = seed * 1234567 + 987654321
  function rand() {
    rng = (rng * 1664525 + 1013904223) & 0xffffffff
    return (rng >>> 0) / 0xffffffff
  }

  for (const n of nodes) {
    pos[n.data.id] = {
      x: cx + (rand() - 0.5) * width * 0.5,
      y: cy + (rand() - 0.5) * height * 0.5,
    }
  }

  const {
    scalingRatio,
    gravity,
    edgeWeightInfluence,
    linLog,
    preventOverlap,
    dissuadeHubs,
    damping,
    iterations,
    gravSource,
  } = params

  const MIN_SPACING = 12

  // 3. Iterative simulation
  for (let step = 0; step < iterations; step++) {
    const fx: Record<string, number> = {}
    const fy: Record<string, number> = {}
    for (const n of nodes) { fx[n.data.id] = 0; fy[n.data.id] = 0 }

    // 3a. Repulsion O(V²)
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i].data.id
        const b = nodes[j].data.id
        const pa = pos[a], pb = pos[b]
        const dx = pa.x - pb.x
        const dy = pa.y - pb.y
        const dist = Math.sqrt(dx * dx + dy * dy) || 0.01
        const dirX = dx / dist
        const dirY = dy / dist

        const hardMin = preventOverlap ? (radii[a] + radii[b] + MIN_SPACING) : 0.01
        const effDist = Math.max(hardMin, dist)

        const degA = dissuadeHubs ? 1 / ((degree[a] ?? 0) + 1) : 1
        const degB = dissuadeHubs ? 1 / ((degree[b] ?? 0) + 1) : 1
        const rep = scalingRatio * 375 * degA * degB / (effDist * effDist)

        fx[a] += dirX * rep; fy[a] += dirY * rep
        fx[b] -= dirX * rep; fy[b] -= dirY * rep
      }
    }

    // 3b. Attraction along edges
    for (const p of edgePairs) {
      const pa = pos[p.srcId]
      const pb = pos[p.tgtId]
      if (!pa || !pb) continue

      const dx = pb.x - pa.x
      const dy = pb.y - pa.y
      const dist = Math.sqrt(dx * dx + dy * dy) || 0.01
      const dirX = dx / dist
      const dirY = dy / dist

      let weight = 1
      if (gravSource === 'affinity') weight = Math.max(0.01, p.affinity)
      else if (gravSource === 'msgs') weight = Math.max(0.01, p.totalMsgs / 120)

      const att = linLog
        ? Math.log(1 + dist) * weight * edgeWeightInfluence * 0.015
        : dist * weight * edgeWeightInfluence * 0.008

      fx[p.srcId] += dirX * att; fy[p.srcId] += dirY * att
      fx[p.tgtId] -= dirX * att; fy[p.tgtId] -= dirY * att
    }

    // 3c. Center gravity
    for (const n of nodes) {
      const id = n.data.id
      const p = pos[id]
      fx[id] += (cx - p.x) * gravity * 0.004
      fy[id] += (cy - p.y) * gravity * 0.004
    }

    // 3d. Position update
    for (const n of nodes) {
      const id = n.data.id
      pos[id] = {
        x: pos[id].x + fx[id] * damping,
        y: pos[id].y + fy[id] * damping,
      }
    }
  }

  return pos
}
