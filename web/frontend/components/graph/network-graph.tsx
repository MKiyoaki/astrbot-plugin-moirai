import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import type { PersonaNode, ImpressionEdge } from '@/lib/api'
import type { EdgePair, PhysicsParams, VisualParams, PositionMap } from '@/lib/graph-types'
import { computeNodeRadius, mockCluster } from '@/lib/graph-utils'
import { GraphNode } from '@/components/graph/graph-node'
import { GraphEdge } from '@/components/graph/graph-edge'

// ── Cluster color palette (Leiden-style) ─────────────────────────────────────
const CLUSTER_COLORS = ['#d4e4f7', '#d5f0dc', '#fde8e6', '#fef9e7', '#f0eaff', '#e8f8f5']
const BOT_FILL = '#fce4ec'
const BOT_STROKE = '#e91e8c'
const DEFAULT_FILL = '#e8e8e8'
const EDGE_POS_COLOR = '#2d7d46'
const EDGE_NEG_COLOR = '#c0392b'
const EDGE_NEU_COLOR = '#aaa'

// ── Props ─────────────────────────────────────────────────────────────────────

interface NetworkGraphProps {
  nodes: PersonaNode[]
  edgePairs: EdgePair[]
  positions: PositionMap | null
  params: PhysicsParams & VisualParams
  selectedNodeId: string | null
  selectedPairKey: string | null
  focusNodeId: string | null
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
  onSelectNode,
  onSelectPair,
  onSizeChange,
  svgRef: externalSvgRef,
}: NetworkGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const internalSvgRef = useRef<SVGSVGElement>(null)
  const svgRef = (externalSvgRef as React.RefObject<SVGSVGElement>) ?? internalSvgRef

  const [containerSize, setContainerSize] = useState({ width: 640, height: 420 })
  const [transform, setTransform] = useState({ x: 0, y: 0, scale: 1 })
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)
  const [hoveredPairKey, setHoveredPairKey] = useState<string | null>(null)
  const dragRef = useRef<{ startX: number; startY: number; tx: number; ty: number } | null>(null)
  const isDraggingRef = useRef(false)

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

  // Pre-compute node radius bounds
  const [minDeg, maxDeg] = useMemo(() => {
    const degrees = nodes.map(n => {
      return edgePairs.filter(p => p.srcId === n.data.id || p.tgtId === n.data.id).length
    })
    return [Math.min(...degrees, 0), Math.max(...degrees, 1)]
  }, [nodes, edgePairs])

  const nodeRadius = useCallback((n: PersonaNode): number => {
    const deg = edgePairs.filter(p => p.srcId === n.data.id || p.tgtId === n.data.id).length
    return computeNodeRadius(deg, minDeg, maxDeg)
  }, [edgePairs, minDeg, maxDeg])

  const nodeFill = useCallback((n: PersonaNode): string => {
    if (n.data.is_bot) return BOT_FILL
    if (params.leidenEnabled) {
      const cid = clusterMap[n.data.id] ?? 0
      return CLUSTER_COLORS[cid % CLUSTER_COLORS.length]
    }
    return DEFAULT_FILL
  }, [params.leidenEnabled, clusterMap])

  // Focus node: pan to center it
  useEffect(() => {
    if (!focusNodeId || !positions?.[focusNodeId]) return
    const p = positions[focusNodeId]
    const { width, height } = containerSize
    setTransform(t => ({
      ...t,
      x: width / 2 - p.x * t.scale,
      y: height / 2 - p.y * t.scale,
    }))
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
    const scale = Math.min(scaleX, scaleY, 3.5)
    const cx = (minX + maxX) / 2
    const cy = (minY + maxY) / 2
    setTransform({
      x: width / 2 - cx * scale,
      y: height / 2 - cy * scale,
      scale,
    })
  }, [positions, nodes, containerSize])

  // Expose fitView on SVG element so parent can call via svgRef
  useEffect(() => {
    const el = svgRef.current
    if (!el) return
    // @ts-expect-error custom method
    el.__fitView = fitView
  }, [fitView, svgRef])

  // ── Mouse handlers ──────────────────────────────────────────────────────────

  const handleMouseDown = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if (e.button !== 0) return
    isDraggingRef.current = false
    dragRef.current = { startX: e.clientX, startY: e.clientY, tx: transform.x, ty: transform.y }
  }, [transform])

  const handleMouseMove = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    const drag = dragRef.current
    if (!drag) return
    const dx = e.clientX - drag.startX
    const dy = e.clientY - drag.startY
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) isDraggingRef.current = true
    if (isDraggingRef.current) {
      const { tx, ty } = drag
      setTransform(t => ({ ...t, x: tx + dx, y: ty + dy }))
    }
  }, [])

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
      setTransform(t => {
        const newScale = Math.min(3.5, Math.max(0.25, t.scale * factor))
        const scaleDiff = newScale - t.scale
        return {
          x: t.x - mouseX * scaleDiff / t.scale,
          y: t.y - mouseY * scaleDiff / t.scale,
          scale: newScale,
        }
      })
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [svgRef])

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
  }, [params.sentimentEnabled, params.sentimentAxis, pickAxis])

  const edgeWidth = useCallback((pair: EdgePair): number => {
    const base = params.defaultEdgeWidth
    if (params.edgeWidthSource === 'affinity') return Math.max(1, pair.affinity * base * 2.8)
    if (params.edgeWidthSource === 'msgs') return Math.max(1, (pair.totalMsgs / 40) * base)
    return base
  }, [params.edgeWidthSource, params.defaultEdgeWidth])

  // --- Animation Helpers ---
  const activeFocusId = hoveredNodeId || selectedNodeId
  const activePairKey = hoveredPairKey || selectedPairKey
  
  // Calculate which edges and nodes are "connected" to the focus
  const { connectedNodeIds, connectedEdgeKeys } = useMemo(() => {
    const nodes = new Set<string>()
    const edges = new Set<string>()

    if (activePairKey) {
        const pair = edgePairs.find(p => p.pairKey === activePairKey)
        if (pair) {
            nodes.add(pair.srcId)
            nodes.add(pair.tgtId)
            edges.add(activePairKey)
        }
    } else if (activeFocusId) {
        nodes.add(activeFocusId)
        edgePairs.forEach(pair => {
            if (pair.srcId === activeFocusId || pair.tgtId === activeFocusId) {
                nodes.add(pair.srcId)
                nodes.add(pair.tgtId)
                edges.add(pair.pairKey)
            }
        })
    }
    
    return { connectedNodeIds: nodes, connectedEdgeKeys: edges }
  }, [activeFocusId, activePairKey, edgePairs])

  const getIsDimmed = (id: string, type: 'node' | 'edge') => {
    if (!activeFocusId && !activePairKey) return false
    if (type === 'node') {
      return !connectedNodeIds.has(id)
    }
    return !connectedEdgeKeys.has(id)
  }

  // LOD Smooth Fading: 0.4 -> 0, 0.8 -> 1
  const labelOpacity = Math.max(0, Math.min(1, (transform.scale - 0.4) / 0.4))

  // ── Render ──────────────────────────────────────────────────────────────────

  const showLabel = transform.scale >= 0.5
  const showEdgeLabel = params.showEdgeLabels && transform.scale > 0.7

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
          <marker
            id="arr"
            markerWidth={params.arrowSize} markerHeight={params.arrowSize * 0.75}
            refX={params.arrowSize} refY={params.arrowSize * 0.375}
            orient="auto"
            markerUnits="userSpaceOnUse"
          >
            <path
              d={`M0,0 L${params.arrowSize},${params.arrowSize * 0.375} L0,${params.arrowSize * 0.75} Z`}
              fill={EDGE_NEU_COLOR}
            />
          </marker>
          <marker
            id="arr-pos"
            markerWidth={params.arrowSize} markerHeight={params.arrowSize * 0.75}
            refX={params.arrowSize} refY={params.arrowSize * 0.375}
            orient="auto"
            markerUnits="userSpaceOnUse"
          >
            <path
              d={`M0,0 L${params.arrowSize},${params.arrowSize * 0.375} L0,${params.arrowSize * 0.75} Z`}
              fill={EDGE_POS_COLOR}
            />
          </marker>
          <marker
            id="arr-neg"
            markerWidth={params.arrowSize} markerHeight={params.arrowSize * 0.75}
            refX={params.arrowSize} refY={params.arrowSize * 0.375}
            orient="auto"
            markerUnits="userSpaceOnUse"
          >
            <path
              d={`M0,0 L${params.arrowSize},${params.arrowSize * 0.375} L0,${params.arrowSize * 0.75} Z`}
              fill={EDGE_NEG_COLOR}
            />
          </marker>
          <marker
            id="arr-highlight"
            markerWidth={params.arrowSize} markerHeight={params.arrowSize * 0.75}
            refX={params.arrowSize} refY={params.arrowSize * 0.375}
            orient="auto"
            markerUnits="userSpaceOnUse"
          >
            <path
              d={`M0,0 L${params.arrowSize},${params.arrowSize * 0.375} L0,${params.arrowSize * 0.75} Z`}
              fill="var(--primary)"
            />
          </marker>
        </defs>

        {/* Background click catcher */}
        <rect
          width="100%"
          height="100%"
          fill="transparent"
          onClick={handleBgClick}
        />

        <g transform={`translate(${transform.x},${transform.y}) scale(${transform.scale})`}>
          {/* Edges rendered first (under nodes) */}
          {positions && edgePairs.map(pair => {
            const pa = positions[pair.srcId]
            const pb = positions[pair.tgtId]
            if (!pa || !pb) return null

            const nodeA = nodes.find(n => n.data.id === pair.srcId)
            const nodeB = nodes.find(n => n.data.id === pair.tgtId)
            const rA = nodeA ? nodeRadius(nodeA) : 10
            const rB = nodeB ? nodeRadius(nodeB) : 10

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
            
            const r = nodeRadius(node)
            const fill = nodeFill(node)
            const strokeColor = node.data.is_bot ? BOT_STROKE : 'var(--primary)'
            const fontSize = Math.max(7, Math.min(11, r * 0.52))

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
                fontSize={fontSize}
                labelOpacity={labelOpacity}
                showLabel={showLabel}
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
            const relationLabel = pair.isBidirectional
              ? `⇄ ${pair.fwd.data.label}`
              : `→ ${pair.fwd.data.label}`
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
                  fontSize: `${params.edgeLabelFontSize / transform.scale}px`,
                  fill: 'var(--foreground)',
                  stroke: 'var(--background)',
                  strokeWidth: 5 / transform.scale,
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
