'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import type { PersonaNode } from '@/lib/api'
import type { EdgePair, PhysicsParams, PositionMap } from '@/lib/graph-types'
import { circularLayout, computeNodeRadius, edgePairWeight } from '@/lib/graph-utils'
import { Fa2Simulation, type Fa2Edge, type Fa2Settings } from '@/lib/fa2/kernel'

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
  stop: () => void
  isComputing: boolean
  progress: number
  /**
   * Bumped once each time a layout finishes settling. The view watches this to
   * re-fit itself, which is what makes absolute layout size stop mattering —
   * the same trick Sigma plays for Gephi Lite by normalising coordinates.
   */
  layoutVersion: number
}

/** Budget per animation frame; keeps the main thread responsive while solving. */
const FRAME_BUDGET_MS = 8

/**
 * Publishing a fresh PositionMap re-renders every node and edge, so doing it
 * on all 60 frames a second costs far more than the solver itself: at 400 nodes
 * a whole 300-iteration solve is ~100ms of maths against seconds of React. The
 * solver still runs every frame; only the hand-off to React is rationed.
 */
const PUBLISH_INTERVAL_MS = 33

function settingsOf(p: PhysicsParams): Fa2Settings {
  return {
    scalingRatio: p.scalingRatio,
    strongGravityMode: p.strongGravityMode,
    gravity: p.gravity,
    outboundAttractionDistribution: p.outboundAttractionDistribution,
    linLogMode: p.linLogMode,
    adjustSizes: p.adjustSizes,
    edgeWeightInfluence: p.edgeWeightInfluence,
    jitterTolerance: p.jitterTolerance,
    barnesHutOptimize: p.barnesHutOptimize,
    barnesHutTheta: p.barnesHutTheta,
  }
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
  const [progress, setProgress] = useState(1)
  const [randSeed, setRandSeed] = useState(0)
  const [layoutVersion, setLayoutVersion] = useState(0)
  const cancelRef = useRef<(() => void) | null>(null)
  const settle = useCallback(() => setLayoutVersion(v => v + 1), [])

  const refresh = useCallback(() => setRandSeed(s => s + 1), [])
  const stop = useCallback(() => cancelRef.current?.(), [])

  // Structural identity: re-solve when the node/edge SET changes, not merely
  // when its length happens to differ.
  const nodesKey = nodes.map(n => n.data.id).join('|')
  const edgesKey = edgePairs.map(p => p.pairKey).join('|')

  const { width, height } = containerSize
  const {
    layoutMode, locked, iterations, edgeWeightSource,
    scalingRatio, strongGravityMode, gravity,
    outboundAttractionDistribution, linLogMode, adjustSizes,
    edgeWeightInfluence, jitterTolerance, barnesHutOptimize, barnesHutTheta,
  } = params

  useEffect(() => {
    cancelRef.current?.()

    if (!enabled || nodes.length === 0) {
      setPositions(null)
      setIsComputing(false)
      return
    }
    if (width === 0 || height === 0) return

    const cx = width / 2
    const cy = height / 2
    const r = Math.min(width, height) * 0.42

    if (locked) {
      // No settle(): the positions are whatever they already were, so re-fitting
      // here would only yank a locked view back from wherever the user panned it.
      // The fallback circular layout is built around the viewport centre and
      // already fits by construction.
      setPositions(prev => prev ?? circularLayout(nodes, cx, cy, r))
      return
    }
    if (layoutMode === 'circular') {
      setPositions(circularLayout(nodes, cx, cy, r))
      setProgress(1)
      settle()
      return
    }

    // Force layout: solve in requestAnimationFrame slices so the UI stays live.
    const index = new Map(nodes.map((n, i) => [n.data.id, i]))
    const edges: Fa2Edge[] = []
    for (const pair of edgePairs) {
      const a = index.get(pair.srcId)
      const b = index.get(pair.tgtId)
      if (a === undefined || b === undefined) continue
      edges.push({ source: a, target: b, weight: edgePairWeight(pair, edgeWeightSource) })
    }

    const degree = new Float64Array(nodes.length)
    for (const e of edges) { degree[e.source] += 1; degree[e.target] += 1 }
    let minDeg = Infinity
    let maxDeg = 0
    for (const d of degree) { minDeg = Math.min(minDeg, d); maxDeg = Math.max(maxDeg, d) }
    if (!Number.isFinite(minDeg)) minDeg = 0
    const radii = new Float64Array(nodes.length)
    for (let i = 0; i < nodes.length; i++) {
      radii[i] = computeNodeRadius(degree[i], minDeg, Math.max(maxDeg, 1))
    }

    const sim = new Fa2Simulation(
      nodes.length, edges, radii, randSeed, Math.min(width, height) * 0.6,
    )
    const settings = settingsOf(params)

    const publish = () => {
      const out: PositionMap = {}
      for (let i = 0; i < nodes.length; i++) {
        out[nodes[i].data.id] = { x: cx + sim.x[i], y: cy + sim.y[i] }
      }
      setPositions(out)
    }

    let done = 0
    let raf = 0
    let cancelled = false
    let lastPublish = 0
    setIsComputing(true)
    setProgress(0)

    const tick = () => {
      if (cancelled) return
      const started = performance.now()
      do {
        sim.step(settings)
        done++
      } while (done < iterations && performance.now() - started < FRAME_BUDGET_MS)

      const finished = done >= iterations
      const now = performance.now()
      // The final state always goes out; intermediate frames only when the
      // rationing interval has elapsed, so the animation stays legible without
      // paying full React reconciliation 60 times a second.
      if (finished || now - lastPublish >= PUBLISH_INTERVAL_MS) {
        lastPublish = now
        publish()
        setProgress(done / iterations)
      }

      if (!finished) {
        raf = requestAnimationFrame(tick)
      } else {
        setIsComputing(false)
        settle()
      }
    }
    raf = requestAnimationFrame(tick)

    const cancel = () => {
      cancelled = true
      cancelAnimationFrame(raf)
      setIsComputing(false)
    }
    cancelRef.current = cancel
    return cancel
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    enabled, nodesKey, edgesKey,
    layoutMode, locked, iterations, edgeWeightSource,
    scalingRatio, strongGravityMode, gravity,
    outboundAttractionDistribution, linLogMode, adjustSizes,
    edgeWeightInfluence, jitterTolerance, barnesHutOptimize, barnesHutTheta,
    width, height, randSeed, settle,
  ])

  return { positions, refresh, stop, isComputing, progress, layoutVersion }
}
