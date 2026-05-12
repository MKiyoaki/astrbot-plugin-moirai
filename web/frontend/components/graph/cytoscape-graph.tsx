'use client'

import { useEffect, useRef, useCallback } from 'react'
import type { PersonaNode, ImpressionEdge } from '@/lib/api'

interface CytoscapeGraphProps {
  nodes: PersonaNode[]
  edges: ImpressionEdge[]
  onNodeClick?: (data: PersonaNode['data']) => void
  onEdgeClick?: (data: ImpressionEdge['data']) => void
  onBackgroundClick?: () => void
  instanceRef?: React.MutableRefObject<unknown>
}

function getCssVar(name: string): string {
  if (typeof window === 'undefined') return '#888'
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

function resolveColor(oklchVar: string, fallback: string): string {
  // Use canvas to resolve oklch colours that Cytoscape can't parse
  const raw = getCssVar(oklchVar)
  if (!raw) return fallback
  try {
    const canvas = document.createElement('canvas')
    canvas.width = 1; canvas.height = 1
    const ctx = canvas.getContext('2d')!
    ctx.fillStyle = raw
    ctx.fillRect(0, 0, 1, 1)
    const [r, g, b] = ctx.getImageData(0, 0, 1, 1).data
    return `rgb(${r},${g},${b})`
  } catch {
    return fallback
  }
}

export function CytoscapeGraph({
  nodes, edges, onNodeClick, onEdgeClick, onBackgroundClick, instanceRef,
}: CytoscapeGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<unknown>(null)

  const initGraph = useCallback(async () => {
    if (!containerRef.current) return
    const cytoscape = (await import('cytoscape')).default

    const isDark = document.documentElement.classList.contains('dark')
    const nodeColor   = resolveColor('--color-accent', isDark ? '#3f3f46' : '#f4f4f5')
    const textColor   = resolveColor('--color-foreground', isDark ? '#fafafa' : '#09090b')
    const borderColor = resolveColor('--color-border', isDark ? 'rgba(255,255,255,0.1)' : '#e4e4e7')
    const edgeDimColor = resolveColor('--color-muted-foreground', isDark ? '#a1a1aa' : '#71717a')

    // Separate connected vs isolated nodes
    const connectedIds = new Set<string>()
    edges.forEach(e => { connectedIds.add(e.data.source); connectedIds.add(e.data.target) })
    const connectedNodes = nodes.filter(n => connectedIds.has(n.data.id))
    const isolatedNodes  = nodes.filter(n => !connectedIds.has(n.data.id))

    // Build elements
    const elements = [
      ...connectedNodes.map(n => ({ ...n, group: 'nodes' as const })),
      ...isolatedNodes.map(n => ({ ...n, group: 'nodes' as const })),
      ...edges.map(e => ({ ...e, group: 'edges' as const })),
    ]

    if (cyRef.current) {
      (cyRef.current as { destroy: () => void }).destroy()
    }

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: [
        {
          selector: 'node',
          style: {
            label: 'data(label)',
            'background-color': nodeColor,
            color: textColor,
            'text-valign': 'center',
            'text-halign': 'center',
            'font-size': '11px',
            'font-family': 'inherit',
            width: 50,
            height: 50,
            'text-wrap': 'wrap',
            'text-max-width': '48',
            'border-width': 1.5,
            'border-color': borderColor,
          },
        },
        {
          selector: 'node[?is_bot]',
          style: {
            'background-color': '#ec4899',
            'border-color': '#f9a8d4',
            'border-width': 2.5,
            color: '#fff',
          },
        },
        {
          selector: 'edge',
          style: {
            label: 'data(label)',
            'curve-style': 'bezier',
            'target-arrow-shape': 'triangle',
            'font-size': '9px',
            'font-family': 'inherit',
            color: edgeDimColor,
            'text-background-color': isDark ? '#09090b' : '#fff',
            'text-background-opacity': 0.7,
            'text-background-padding': '2px',
            width: 'mapData(intensity, 0, 1, 1.5, 5)',
            'line-color': 'mapData(affect, -1, 1, #ef4444, #22c55e)',
            'target-arrow-color': 'mapData(affect, -1, 1, #ef4444, #22c55e)',
            opacity: 0.85,
          },
        },
        { selector: '.dim',     style: { opacity: 0.12 } },
        { selector: '.focused', style: { opacity: 1, 'border-width': 3, 'border-color': '#f59e0b' } },
        { 
          selector: 'edge.focused', 
          style: { 
            width: 6, 
            opacity: 1,
            'line-color': '#f59e0b',
            'target-arrow-color': '#f59e0b',
            'z-index': 999 
          } 
        },
        { selector: '.hovered', style: { opacity: 1, 'border-width': 2, 'border-color': '#fbbf24' } },
        { selector: 'edge.hovered', style: { width: 5, opacity: 1, 'z-index': 998 } },
      ],
      layout: { name: 'preset' }, // We'll run layouts manually
    })

    cyRef.current = cy
    if (instanceRef) instanceRef.current = cy

    // Layout: concentric for connected nodes, spread isolated to the right
    if (connectedNodes.length > 0) {
      const connectedEls = cy.nodes().filter(n => connectedIds.has(n.id()))
      const subgraph = connectedEls.add(cy.edges())
      subgraph.layout({
        name: 'concentric',
        concentric: (node: { data: (k: string) => number }) => node.data('confidence') * 10,
        levelWidth: () => 2,
        padding: 40,
        animate: false,
        fit: false,
      }).run()
    }

    if (isolatedNodes.length > 0) {
      const connectedBB = connectedNodes.length > 0
        ? (cy.nodes().filter(n => connectedIds.has(n.id())) as { boundingBox: () => { x2: number; y1: number } }).boundingBox()
        : { x2: 0, y1: 0 }
      const offsetX = connectedBB.x2 + 120
      cy.nodes().filter(n => !connectedIds.has(n.id())).forEach((n, i) => {
        const col = i % 3
        const row = Math.floor(i / 3)
        n.position({ x: offsetX + col * 100, y: connectedBB.y1 + row * 100 })
      })
    }

    cy.fit(undefined, 40)

    // Events
    cy.on('tap', 'node', evt => {
      cy.elements().removeClass('focused')
      cy.elements().addClass('dim')
      evt.target.closedNeighborhood().removeClass('dim').addClass('focused')
      onNodeClick?.(evt.target.data())
    })

    cy.on('tap', 'edge', evt => {
      cy.elements().removeClass('focused')
      cy.elements().addClass('dim')
      evt.target.removeClass('dim').addClass('focused')
      evt.target.connectedNodes().removeClass('dim').addClass('focused')
      onEdgeClick?.(evt.target.data())
    })

    cy.on('tap', evt => {
      if (evt.target === cy) {
        cy.elements().removeClass('dim focused hovered')
        onBackgroundClick?.()
      }
    })

    cy.on('mouseover', 'edge', evt => {
      evt.target.addClass('hovered')
      evt.target.connectedNodes().addClass('hovered')
    })

    cy.on('mouseout', 'edge', evt => {
      evt.target.removeClass('hovered')
      evt.target.connectedNodes().removeClass('hovered')
    })

    cy.on('mouseover', 'node', evt => {
      evt.target.addClass('hovered')
    })

    cy.on('mouseout', 'node', evt => {
      evt.target.removeClass('hovered')
    })

    cy.on('zoom', () => {
      const z = cy.zoom()
      cy.style().selector('node').style('font-size', z < 0.6 ? 0 : 11).update()
    })
  }, [nodes, edges, onNodeClick, onEdgeClick, onBackgroundClick, instanceRef])

  useEffect(() => {
    initGraph()
    return () => {
      if (cyRef.current) {
        (cyRef.current as { destroy: () => void }).destroy()
        cyRef.current = null
      }
    }
  }, [initGraph])

  // Re-apply colours on theme change
  useEffect(() => {
    const observer = new MutationObserver(() => initGraph())
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    return () => observer.disconnect()
  }, [initGraph])

  return <div ref={containerRef} className="size-full" />
}
