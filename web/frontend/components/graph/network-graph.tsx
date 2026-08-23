import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import type { PersonaNode, ImpressionEdge } from '@/lib/api'
import type { EdgePair, PhysicsParams, VisualParams, PositionMap } from '@/lib/graph-types'
import { computeNodeRadius, degreeMap, mockCluster } from '@/lib/graph-utils'
import { GraphNode } from '@/components/graph/graph-node'
import { GraphEdge } from '@/components/graph/graph-edge'
import { useApp } from '@/lib/store'
import { getLocalizedOrientation } from '@/lib/i18n'
import { getPaletteColor } from '@/lib/colors'

const DEFAULT_FILL = 'var(--muted)'
const EDGE_POS_COLOR = '#2d7d46'
const EDGE_NEG_COLOR = '#c0392b'
const EDGE_NEU_COLOR = '#aaa'

/** id of the pan/zoom group; the image exporter neutralises its transform. */
export const GRAPH_VIEWPORT_ID = 'moirai-graph-viewport'

// ── Props ─────────────────────────────────────────────────────────────────────

interface NetworkGraphProps {
  nodes: PersonaNode[]
  edgePairs: EdgePair[]
  positions: PositionMap | null
  params: PhysicsParams & VisualParams
  selectedNodeId: string | null
  selectedPairKey: string | null
  focusNodeId: string | null
  /** Export pass: reveal every label and drop hover dimming. */
  exportMode?: boolean
  onSelectNode: (id: string | null) => void
  onSelectPair: (key: string | null) => void
  onSizeChange?: (size: { width: number; height: number }) => void
  svgRef?: React.RefObject<SVGSVGElement | null>
}

// ── Component ─────────────────────────────────────────────────────────────────

export function NetworkGraph({
  nodes,
  edgePairs,
  positions,
  params,
  selectedNodeId,
  selectedPairKey,
  focusNodeId,
  exportMode = false,
  onSelectNode,
  onSelectPair,
  onSizeChange,
  svgRef: externalSvgRef,
}: NetworkGraphProps) {
  const { i18n } = useApp()
  const containerRef = useRef<HTMLDivElement>(null)
  const internalSvgRef = useRef<SVGSVGElement>(null)
  const svgRef = (externalSvgRef as React.RefObject<SVGSVGElement>) ?? internalSvgRef
  const viewportRef = useRef<SVGGElement>(null)

  const [containerSize, setContainerSize] = useState({ width: 640, height: 420 })
  // Pan/zoom lives in a ref and is written straight to the DOM; only the zoom
  // level is mirrored into state, because label sizing depends on it.
  const transformRef = useRef({ x: 0, y: 0, scale: 1 })
  const [scale, setScale] = useState(1)
  const scaleFrameRef = useRef(0)
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)
  const [hoveredPairKey, setHoveredPairKey] = useState<string | null>(null)
  const dragRef = useRef<{ startX: number; startY: number; tx: number; ty: number } | null>(null)
  const isDraggingRef = useRef(false)

  const applyTransform = useCallback(() => {
    const t = transformRef.current
    viewportRef.current?.setAttribute(
      'transform', `translate(${t.x},${t.y}) scale(${t.scale})`,
    )
    if (scaleFrameRef.current) return
    scaleFrameRef.current = requestAnimationFrame(() => {
      scaleFrameRef.current = 0
      setScale(prev => (Math.abs(prev - transformRef.current.scale) > 0.005
        ? transformRef.current.scale
        : prev))
    })
  }, [])

  useEffect(() => () => {
    if (scaleFrameRef.current) cancelAnimationFrame(scaleFrameRef.current)
  }, [])

  // ResizeObserver
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect
      setContainerSize({ width, height })
      onSizeChange?.({ width, height })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [onSizeChange])

  // Leiden clustering (memoized)
  const clusterMap = useMemo(() => {
    if (!params.leidenEnabled) return {}
    return mockCluster(nodes, edgePairs, params.leidenResolution)
  }, [nodes, edgePairs, params.leidenEnabled, params.leidenResolution])

  // ── Derived lookups ─────────────────────────────────────────────────────────
  // Computed once per data change instead of scanning the edge/node arrays
  // inside the render loop, which used to make drawing O(V·E).

  const radiusById = useMemo(() => {
    const degrees = degreeMap(nodes, edgePairs)
    let minDeg = Infinity
    let maxDeg = 1
    for (const d of degrees.values()) {
      minDeg = Math.min(minDeg, d)
      maxDeg = Math.max(maxDeg, d)
    }
    if (!Number.isFinite(minDeg)) minDeg = 0
    const radii = new Map<string, number>()
    for (const [id, deg] of degrees) {
      radii.set(id, computeNodeRadius(deg, minDeg, maxDeg))
    }
    return radii
  }, [nodes, edgePairs])

  const nodeRadius = useCallback(
    (id: string): number => radiusById.get(id) ?? 12,
    [radiusById],
  )

  const nodeFill = useCallback((n: PersonaNode): string => {
    if (n.data.is_bot) return 'var(--primary)'
    if (params.leidenEnabled) {
      const cid = clusterMap[n.data.id] ?? 0
      return getPaletteColor(cid)
    }
    return DEFAULT_FILL
  }, [params.leidenEnabled, clusterMap])

  // Focus node: pan to center it
  useEffect(() => {
    if (!focusNodeId || !positions?.[focusNodeId]) return
    const p = positions[focusNodeId]
    const { width, height } = containerSize
    const t = transformRef.current
    transformRef.current = {
      ...t,
      x: width / 2 - p.x * t.scale,
      y: height / 2 - p.y * t.scale,
    }
    applyTransform()
    onSelectNode(focusNodeId)
  }, [focusNodeId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Fit to view
  const fitView = useCallback(() => {
    if (!positions || nodes.length === 0) return
    const xs = nodes.map(n => positions[n.data.id]?.x ?? 0)
    const ys = nodes.map(n => positions[n.data.id]?.y ?? 0)
    const minX = Math.min(...xs), maxX = Math.max(...xs)
    const minY = Math.min(...ys), maxY = Math.max(...ys)
    const { width, height } = containerSize
    const padding = 60
    const scaleX = (width - padding * 2) / (maxX - minX || 1)
    const scaleY = (height - padding * 2) / (maxY - minY || 1)
    const nextScale = Math.min(scaleX, scaleY, 3.5)
    const cx = (minX + maxX) / 2
    const cy = (minY + maxY) / 2
    transformRef.current = {
      x: width / 2 - cx * nextScale,
      y: height / 2 - cy * nextScale,
      scale: nextScale,
    }
    applyTransform()
  }, [positions, nodes, containerSize, applyTransform])

  // Expose fitView on SVG element so parent can call via svgRef
  useEffect(() => {
    const el = svgRef.current
    if (!el) return
    // @ts-expect-error custom method
    el.__fitView = fitView
  }, [fitView, svgRef])

  // Re-apply the current transform whenever the group remounts.
  useEffect(() => { applyTransform() }, [applyTransform, positions])

  // ── Mouse handlers ──────────────────────────────────────────────────────────

  const handleMouseDown = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if (e.button !== 0) return
    isDraggingRef.current = false
    const t = transformRef.current
    dragRef.current = { startX: e.clientX, startY: e.clientY, tx: t.x, ty: t.y }
  }, [])

  const handleMouseMove = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    const drag = dragRef.current
    if (!drag) return
    const dx = e.clientX - drag.startX
    const dy = e.clientY - drag.startY
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) isDraggingRef.current = true
    if (isDraggingRef.current) {
      transformRef.current = { ...transformRef.current, x: drag.tx + dx, y: drag.ty + dy }
      applyTransform()
    }
  }, [applyTransform])

  const handleMouseUp = useCallback(() => {
    dragRef.current = null
  }, [])

  // Native wheel handler — must be non-passive to call preventDefault()
  useEffect(() => {
    const el = svgRef.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const factor = e.deltaY < 0 ? 1.1 : 0.91
      const rect = el.getBoundingClientRect()
      const mouseX = e.clientX - rect.left
      const mouseY = e.clientY - rect.top
      const t = transformRef.current
      const newScale = Math.min(3.5, Math.max(0.25, t.scale * factor))
      const scaleDiff = newScale - t.scale
      transformRef.current = {
        x: t.x - (mouseX * scaleDiff) / t.scale,
        y: t.y - (mouseY * scaleDiff) / t.scale,
        scale: newScale,
      }
      applyTransform()
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [svgRef, applyTransform])

  const handleBgClick = useCallback(() => {
    if (!isDraggingRef.current) {
      onSelectNode(null)
      onSelectPair(null)
    }
  }, [onSelectNode, onSelectPair])

  // ── Edge color ──────────────────────────────────────────────────────────────

  const pickAxis = useCallback((edge: ImpressionEdge): number =>
    params.sentimentAxis === 'power' ? edge.data.power : edge.data.affect
  , [params.sentimentAxis])

  const edgeColor = useCallback((pair: EdgePair): string => {
    if (!params.sentimentEnabled) return EDGE_NEU_COLOR
    const avg = pair.isBidirectional && pair.bwd
      ? (pickAxis(pair.fwd) + pickAxis(pair.bwd)) / 2
      : pickAxis(pair.fwd)
    if (avg > 0.3) return EDGE_POS_COLOR
    if (avg < -0.1) return EDGE_NEG_COLOR
    return EDGE_NEU_COLOR
  }, [params.sentimentEnabled, pickAxis])

  const edgeWidth = useCallback((pair: EdgePair): number => {
    const base = params.defaultEdgeWidth
    if (params.edgeWidthSource === 'affinity') return Math.max(1, pair.affinity * base * 2.8)
    if (params.edgeWidthSource === 'msgs') return Math.max(1, (pair.totalMsgs / 40) * base)
    return base
  }, [params.edgeWidthSource, params.defaultEdgeWidth])

  // --- Focus / neighbourhood ---
  const activeFocusId = hoveredNodeId || selectedNodeId
  const activePairKey = hoveredPairKey || selectedPairKey

  // Adjacency, built once, so hover does not re-scan every edge pair.
  const adjacency = useMemo(() => {
    const map = new Map<string, EdgePair[]>()
    for (const pair of edgePairs) {
      const forSrc = map.get(pair.srcId)
      if (forSrc) forSrc.push(pair); else map.set(pair.srcId, [pair])
      const forTgt = map.get(pair.tgtId)
      if (forTgt) forTgt.push(pair); else map.set(pair.tgtId, [pair])
    }
    return map
  }, [edgePairs])

  const pairByKey = useMemo(
    () => new Map(edgePairs.map(p => [p.pairKey, p])),
    [edgePairs],
  )

  const { connectedNodeIds, connectedEdgeKeys } = useMemo(() => {
    const nodeIds = new Set<string>()
    const edgeKeys = new Set<string>()

    if (activePairKey) {
      const pair = pairByKey.get(activePairKey)
      if (pair) {
        nodeIds.add(pair.srcId)
        nodeIds.add(pair.tgtId)
        edgeKeys.add(activePairKey)
      }
    } else if (activeFocusId) {
      nodeIds.add(activeFocusId)
      for (const pair of adjacency.get(activeFocusId) ?? []) {
        nodeIds.add(pair.srcId)
        nodeIds.add(pair.tgtId)
        edgeKeys.add(pair.pairKey)
      }
    }

    return { connectedNodeIds: nodeIds, connectedEdgeKeys: edgeKeys }
  }, [activeFocusId, activePairKey, adjacency, pairByKey])

  const hasFocus = !!activeFocusId || !!activePairKey

  const getIsDimmed = (id: string, type: 'node' | 'edge') => {
    if (exportMode || !hasFocus) return false
    if (type === 'node') return !connectedNodeIds.has(id)
    return !connectedEdgeKeys.has(id)
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  // Names stay hidden until the pointer picks out a node — a full-graph label
  // layer is unreadable past a few dozen people. Hovering reveals that node and
  // everyone it is connected to.
  const showAllLabels = exportMode || params.alwaysShowLabels
  const isLabelVisible = (id: string) => showAllLabels || connectedNodeIds.has(id)
  const showEdgeLabel = params.showEdgeLabels && (exportMode || scale > 0.7)
  const labelScale = exportMode ? 1 : scale

  return (
    <div ref={containerRef} className="size-full relative overflow-hidden select-none">
      {!positions && (
        <div className="absolute inset-0 z-10 flex items-center justify-center text-muted-foreground text-sm pointer-events-none">
          计算布局中…
        </div>
      )}
      <svg
        ref={svgRef as React.RefObject<SVGSVGElement>}
        className="size-full cursor-grab active:cursor-grabbing"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        <defs>
          {([
            ['arr', EDGE_NEU_COLOR],
            ['arr-pos', EDGE_POS_COLOR],
            ['arr-neg', EDGE_NEG_COLOR],
            ['arr-highlight', 'var(--primary)'],
          ] as const).map(([id, fill]) => (
            <marker
              key={id}
              id={id}
              markerWidth={params.arrowSize} markerHeight={params.arrowSize * 0.75}
              refX={params.arrowSize} refY={params.arrowSize * 0.375}
              orient="auto"
              markerUnits="userSpaceOnUse"
            >
              <path
                d={`M0,0 L${params.arrowSize},${params.arrowSize * 0.375} L0,${params.arrowSize * 0.75} Z`}
                fill={fill}
              />
            </marker>
          ))}
        </defs>

        {/* Background click catcher */}
        <rect
          data-export-omit=""
          width="100%"
          height="100%"
          fill="transparent"
          onClick={handleBgClick}
        />

        <g id={GRAPH_VIEWPORT_ID} ref={viewportRef}>
          {/* Edges rendered first (under nodes) */}
          {positions && edgePairs.map(pair => {
            const pa = positions[pair.srcId]
            const pb = positions[pair.tgtId]
            if (!pa || !pb) return null

            const rA = nodeRadius(pair.srcId)
            const rB = nodeRadius(pair.tgtId)

            const isHovered = hoveredPairKey === pair.pairKey
            const isSelected = selectedPairKey === pair.pairKey
            const isFocused = connectedEdgeKeys.has(pair.pairKey)

            const color = edgeColor(pair)
            const w = edgeWidth(pair)
            const isDimmed = getIsDimmed(pair.pairKey, 'edge')

            const dx = pb.x - pa.x
            const dy = pb.y - pa.y
            const dist = Math.sqrt(dx * dx + dy * dy) || 0.01
            const unitX = dx / dist
            const unitY = dy / dist
            const perpX = -dy / dist
            const perpY = dx / dist

            // Standard separation distance (inner gap)
            const GAP = 1.2
            // Shift center of line outwards by half-width + half-gap
            const offset = (w / 2) + GAP

            // Adjust endpoints to stop at node boundaries
            const x1 = pa.x + unitX * rA
            const y1 = pa.y + unitY * rA
            const x2 = pb.x - unitX * rB
            const y2 = pb.y - unitY * rB

            const arrowId = (isHovered || isSelected) ? 'arr-highlight' : (color === EDGE_POS_COLOR ? 'arr-pos' : color === EDGE_NEG_COLOR ? 'arr-neg' : 'arr')

            return (
              <GraphEdge
                key={pair.pairKey}
                x1={x1} y1={y1} x2={x2} y2={y2}
                color={color}
                width={w}
                opacity={params.edgeOpacity}
                isBidirectional={pair.isBidirectional}
                isHovered={isHovered}
                isSelected={isSelected}
                isFocused={isFocused}
                isDimmed={isDimmed}
                arrowId={params.showArrows ? arrowId : undefined}
                perpX={perpX}
                perpY={perpY}
                offset={offset}
                onClick={e => { e.stopPropagation(); if (!isDraggingRef.current) onSelectPair(pair.pairKey) }}
                onMouseEnter={() => setHoveredPairKey(pair.pairKey)}
                onMouseLeave={() => setHoveredPairKey(null)}
              />
            )
          })}

          {/* Layer 2: Nodes */}
          {positions && nodes.map(node => {
            const p = positions[node.data.id]
            if (!p) return null
            const isHovered = hoveredNodeId === node.data.id
            const isSelected = selectedNodeId === node.data.id
            const isFocused = connectedNodeIds.has(node.data.id)
            const isDimmed = getIsDimmed(node.data.id, 'node')

            const r = nodeRadius(node.data.id)
            const fill = nodeFill(node)
            const strokeColor = 'var(--primary)'
            const botPlatform = node.data.is_bot
              ? (node.data.bound_identities.find(b => b.platform !== 'internal')?.platform ?? 'BOT').toUpperCase()
              : undefined

            return (
              <GraphNode
                key={node.data.id}
                x={p.x}
                y={p.y}
                r={r}
                label={node.data.label}
                fill={fill}
                strokeColor={strokeColor}
                isSelected={isSelected}
                isHovered={isHovered}
                isFocused={isFocused}
                isDimmed={isDimmed}
                isBot={node.data.is_bot}
                botLabel={botPlatform}
                fontSize={params.labelFontSize / labelScale}
                showLabel={isLabelVisible(node.data.id)}
                onClick={e => { e.stopPropagation(); if (!isDraggingRef.current) onSelectNode(node.data.id) }}
                onMouseEnter={() => setHoveredNodeId(node.data.id)}
                onMouseLeave={() => setHoveredNodeId(null)}
              />
            )
          })}
          {/* Layer 3: Edge labels — above edges AND nodes, with background halo */}
          {positions && showEdgeLabel && edgePairs.map(pair => {
            const pa = positions[pair.srcId]
            const pb = positions[pair.tgtId]
            if (!pa || !pb) return null
            const isDimmed = getIsDimmed(pair.pairKey, 'edge')
            const midX = (pa.x + pb.x) / 2
            const midY = (pa.y + pb.y) / 2
            const localizedLabel = getLocalizedOrientation(pair.fwd.data.label, i18n)
            const relationLabel = pair.isBidirectional
              ? `⇄ ${localizedLabel}`
              : `→ ${localizedLabel}`
            return (
              <text
                key={`lbl-${pair.pairKey}`}
                x={midX}
                y={midY}
                textAnchor="middle"
                dominantBaseline="middle"
                style={{
                  userSelect: 'none',
                  pointerEvents: 'none',
                  fontSize: `${params.edgeLabelFontSize / labelScale}px`,
                  fill: 'var(--foreground)',
                  stroke: 'var(--background)',
                  strokeWidth: 5 / labelScale,
                  paintOrder: 'stroke',
                  opacity: isDimmed ? 0.08 : 1,
                }}
              >
                {relationLabel}
              </text>
            )
          })}
        </g>

        {/* Fixed stats overlay (outside transform group) */}
        <text
          data-export-omit=""
          x={containerSize.width - 12}
          y={20}
          fontSize={11}
          fill="var(--muted-foreground)"
          textAnchor="end"
          style={{ userSelect: 'none', pointerEvents: 'none' }}
        >
          {`节点 ${nodes.length} · 边对 ${edgePairs.length}`}
        </text>
      </svg>
    </div>
  )
}
