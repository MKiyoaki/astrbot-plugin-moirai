'use client'

import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import type { PersonaNode } from '@/lib/api'
import type { EdgePair, PhysicsParams, VisualParams, PositionMap } from '@/lib/graph-types'
import { computeNodeRadius, mockCluster } from '@/lib/graph-utils'

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

  // Expose fitView via data attribute hack for parent toolbar buttons
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    // @ts-expect-error custom method
    el.__fitView = fitView
  }, [fitView])

  // ── Mouse handlers ──────────────────────────────────────────────────────────

  const handleMouseDown = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if (e.button !== 0) return
    isDraggingRef.current = false
    dragRef.current = { startX: e.clientX, startY: e.clientY, tx: transform.x, ty: transform.y }
  }, [transform])

  const handleMouseMove = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if (!dragRef.current) return
    const dx = e.clientX - dragRef.current.startX
    const dy = e.clientY - dragRef.current.startY
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) isDraggingRef.current = true
    if (isDraggingRef.current) {
      setTransform(t => ({ ...t, x: dragRef.current!.tx + dx, y: dragRef.current!.ty + dy }))
    }
  }, [])

  const handleMouseUp = useCallback(() => {
    dragRef.current = null
  }, [])

  const handleWheel = useCallback((e: React.WheelEvent<SVGSVGElement>) => {
    e.preventDefault()
    const factor = e.deltaY < 0 ? 1.1 : 0.91
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return
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
  }, [svgRef])

  const handleBgClick = useCallback(() => {
    if (!isDraggingRef.current) {
      onSelectNode(null)
      onSelectPair(null)
    }
  }, [onSelectNode, onSelectPair])

  // ── Edge color ──────────────────────────────────────────────────────────────

  const edgeColor = useCallback((pair: EdgePair): string => {
    if (!params.sentimentEnabled) return EDGE_NEU_COLOR
    const avg = pair.isBidirectional && pair.bwd
      ? (pair.fwd.data.affect + pair.bwd.data.affect) / 2
      : pair.fwd.data.affect
    if (avg > 0.3) return EDGE_POS_COLOR
    if (avg < -0.1) return EDGE_NEG_COLOR
    return EDGE_NEU_COLOR
  }, [params.sentimentEnabled])

  const edgeWidth = useCallback((pair: EdgePair): number => {
    if (params.edgeWidthSource === 'affinity') return Math.max(1, pair.affinity * 5)
    if (params.edgeWidthSource === 'msgs') return Math.max(1, pair.totalMsgs / 40)
    return 1.8
  }, [params.edgeWidthSource])

  // ── Render ──────────────────────────────────────────────────────────────────

  if (!positions) {
    return (
      <div ref={containerRef} className="size-full flex items-center justify-center text-muted-foreground text-sm">
        计算布局中…
      </div>
    )
  }

  const showLabel = transform.scale >= 0.5

  return (
    <div ref={containerRef} className="size-full relative overflow-hidden select-none">
      <svg
        ref={svgRef as React.RefObject<SVGSVGElement>}
        className="size-full cursor-grab active:cursor-grabbing"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
      >
        <defs>
          <marker id="arr" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
            <path d="M0,0 L8,3 L0,6 Z" fill={EDGE_NEU_COLOR} />
          </marker>
          <marker id="arr-pos" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
            <path d="M0,0 L8,3 L0,6 Z" fill={EDGE_POS_COLOR} />
          </marker>
          <marker id="arr-neg" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
            <path d="M0,0 L8,3 L0,6 Z" fill={EDGE_NEG_COLOR} />
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
          {edgePairs.map(pair => {
            const pa = positions[pair.srcId]
            const pb = positions[pair.tgtId]
            if (!pa || !pb) return null
            const color = edgeColor(pair)
            const w = edgeWidth(pair)
            const isSelected = selectedPairKey === pair.pairKey
            const strokeW = isSelected ? w + 1.5 : w
            const opacity = params.edgeOpacity

            const dx = pb.x - pa.x
            const dy = pb.y - pa.y
            const dist = Math.sqrt(dx * dx + dy * dy) || 0.01
            const perpX = -dy / dist
            const perpY = dx / dist
            const PERP = 1.0

            const arrowId = color === EDGE_POS_COLOR ? 'arr-pos' : color === EDGE_NEG_COLOR ? 'arr-neg' : 'arr'
            const showEdgeLabel = transform.scale > 0.7
            const midX = (pa.x + pb.x) / 2
            const midY = (pa.y + pb.y) / 2
            const relationLabel = pair.isBidirectional
              ? `⇄ ${pair.fwd.data.label}`
              : `→ ${pair.fwd.data.label}`

            return (
              <g
                key={pair.pairKey}
                onClick={e => { e.stopPropagation(); if (!isDraggingRef.current) onSelectPair(pair.pairKey) }}
                style={{ cursor: 'pointer' }}
              >
                {pair.isBidirectional ? (
                  <>
                    <line
                      x1={pa.x + perpX * PERP} y1={pa.y + perpY * PERP}
                      x2={pb.x + perpX * PERP} y2={pb.y + perpY * PERP}
                      stroke={color} strokeWidth={isSelected ? strokeW / 1.5 + 1 : strokeW / 1.5}
                      strokeOpacity={opacity}
                    />
                    <line
                      x1={pb.x - perpX * PERP} y1={pb.y - perpY * PERP}
                      x2={pa.x - perpX * PERP} y2={pa.y - perpY * PERP}
                      stroke={color} strokeWidth={isSelected ? strokeW / 1.5 + 1 : strokeW / 1.5}
                      strokeOpacity={opacity}
                    />
                  </>
                ) : (
                  <line
                    x1={pa.x} y1={pa.y} x2={pb.x} y2={pb.y}
                    stroke={color} strokeWidth={strokeW}
                    strokeOpacity={opacity}
                    markerEnd={params.showArrows ? `url(#${arrowId})` : undefined}
                  />
                )}
                {/* Transparent wide hit area */}
                <line
                  x1={pa.x} y1={pa.y} x2={pb.x} y2={pb.y}
                  stroke="transparent" strokeWidth={14}
                />
                {/* Edge label */}
                {showEdgeLabel && (
                  <text
                    x={midX} y={midY}
                    fontSize={10 / transform.scale}
                    fill="var(--muted-foreground)"
                    textAnchor="middle"
                    dominantBaseline="middle"
                    style={{ userSelect: 'none', pointerEvents: 'none' }}
                  >
                    {relationLabel}
                  </text>
                )}
              </g>
            )
          })}

          {/* Nodes */}
          {nodes.map(node => {
            const p = positions[node.data.id]
            if (!p) return null
            const r = nodeRadius(node)
            const fill = nodeFill(node)
            const isSelected = selectedNodeId === node.data.id
            const strokeColor = node.data.is_bot ? BOT_STROKE : 'var(--foreground)'
            const fontSize = Math.max(7, Math.min(11, r * 0.52))

            return (
              <g
                key={node.data.id}
                transform={`translate(${p.x},${p.y})`}
                onClick={e => { e.stopPropagation(); if (!isDraggingRef.current) onSelectNode(node.data.id) }}
                style={{ cursor: 'pointer' }}
              >
                <circle
                  r={r}
                  fill={fill}
                  stroke={isSelected ? strokeColor : (node.data.is_bot ? BOT_STROKE : 'var(--border)')}
                  strokeWidth={isSelected ? 2.5 : (node.data.is_bot ? 1.5 : 1)}
                />
                {showLabel && (
                  <text
                    y={r + 10}
                    fontSize={fontSize}
                    fill="var(--foreground)"
                    textAnchor="middle"
                    dominantBaseline="middle"
                    style={{ userSelect: 'none', pointerEvents: 'none' }}
                  >
                    {node.data.label}
                  </text>
                )}
                {node.data.is_bot && transform.scale > 0.6 && (
                  <text
                    y={r + 20}
                    fontSize={8}
                    fill={BOT_STROKE}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fontWeight="bold"
                    style={{ userSelect: 'none', pointerEvents: 'none' }}
                  >
                    BOT
                  </text>
                )}
              </g>
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
