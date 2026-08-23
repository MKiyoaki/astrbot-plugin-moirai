import type { PersonaNode, ImpressionEdge } from './api'

// ── EdgePair ──────────────────────────────────────────────────────────────────
// A bidirectional or unidirectional pair of ImpressionEdges sharing the same
// node pair. pairKey = `${minUID}|${maxUID}` is stable regardless of direction.

export interface EdgePair {
  pairKey: string
  srcId: string           // forward edge's source (lexicographically smaller uid)
  tgtId: string           // forward edge's target
  fwd: ImpressionEdge     // source → target
  bwd?: ImpressionEdge    // target → source, may be absent
  isBidirectional: boolean
  affinity: number        // computed by computeAffinity(), cached here
  totalMsgs: number       // fwd.msg_count + bwd?.msg_count (fallback: 1 + 0)
}

// ── GroupCard ─────────────────────────────────────────────────────────────────
// Summary data for a group shown in the card list view.

export interface GroupCard {
  group_id: string
  name: string
  member_count: number
  node_count: number
  edge_pair_count: number
  last_active: string     // ISO 8601
  top_tags: string[]      // top-4 content_tags by frequency
  description: string
  nodes: PersonaNode[]
  edgePairs: EdgePair[]
}

// ── Physics / Visual params ───────────────────────────────────────────────────
// The ForceAtlas2 fields mirror Gephi Desktop's layout properties one for one —
// same names, same defaults, same semantics — so a value tuned here means the
// same thing after the graph is exported to GEXF and reopened in Gephi.

export type EdgeWeightSource = 'affinity' | 'msgs' | 'equal'

export interface PhysicsParams {
  layoutMode: 'circular' | 'force'
  locked: boolean

  // Tuning
  scalingRatio: number        // Gephi "Scaling"
  strongGravityMode: boolean  // Gephi "Stronger Gravity"
  gravity: number             // Gephi "Gravity"

  // Behavior Alternatives
  outboundAttractionDistribution: boolean  // Gephi "Dissuade Hubs"
  linLogMode: boolean                      // Gephi "LinLog mode"
  adjustSizes: boolean                     // Gephi "Prevent Overlap"
  edgeWeightInfluence: number              // Gephi "Edge Weight Influence"

  // Performance
  jitterTolerance: number     // Gephi "Tolerance (speed)"
  barnesHutOptimize: boolean  // Gephi "Approximate Repulsion"
  barnesHutTheta: number      // Gephi "Approximation"

  // Moirai-specific — Gephi runs continuously, we run a bounded pass.
  iterations: number
  edgeWeightSource: EdgeWeightSource  // what feeds the Gephi `weight` attribute
  biWeight: number                    // bidirectional impression multiplier
}

export interface VisualParams {
  showBot: boolean
  edgeOpacity: number         // 0.05 – 1
  defaultEdgeWidth: number
  alwaysShowLabels: boolean   // off: names appear only around the hovered node
  labelFontSize: number
  showArrows: boolean
  arrowSize: number
  edgeWidthSource: 'equal' | 'affinity' | 'msgs'
  showEdgeLabels: boolean     // Toggle for relationship type labels
  edgeLabelFontSize: number
  leidenEnabled: boolean
  leidenResolution: number
  sentimentEnabled: boolean
  sentimentAxis: 'benevolence' | 'power'
}

// ── View / Position ───────────────────────────────────────────────────────────

export type ViewMode = 'all' | 'member'

export type PositionMap = Record<string, { x: number; y: number }>

// ── Gephi auto settings ───────────────────────────────────────────────────────
// Port of Gephi Desktop's ForceAtlas2.resetPropertiesValues(): the "generate the
// settings that fit the current graph best" button. Only the node count varies.

export type GephiAutoSettings = Pick<
  PhysicsParams,
  | 'scalingRatio' | 'strongGravityMode' | 'gravity'
  | 'outboundAttractionDistribution' | 'linLogMode' | 'adjustSizes'
  | 'edgeWeightInfluence' | 'jitterTolerance'
  | 'barnesHutOptimize' | 'barnesHutTheta'
>

export function gephiAutoSettings(nodeCount: number): GephiAutoSettings {
  return {
    scalingRatio: nodeCount >= 100 ? 2.0 : 10.0,
    strongGravityMode: false,
    gravity: 1.0,
    outboundAttractionDistribution: false,
    linLogMode: false,
    adjustSizes: false,
    edgeWeightInfluence: 1.0,
    jitterTolerance: 1.0,
    barnesHutOptimize: nodeCount >= 1000,
    barnesHutTheta: 1.2,
  }
}

// ── Defaults ──────────────────────────────────────────────────────────────────

export const DEFAULT_PHYSICS_PARAMS: PhysicsParams = {
  layoutMode: 'circular',
  locked: false,
  ...gephiAutoSettings(0),
  iterations: 300,
  edgeWeightSource: 'affinity',
  biWeight: 1.0,
}

export const DEFAULT_VISUAL_PARAMS: VisualParams = {
  showBot: true,
  edgeOpacity: 0.7,
  defaultEdgeWidth: 1.8,
  alwaysShowLabels: false,
  labelFontSize: 10,
  showArrows: true,
  arrowSize: 6,
  edgeWidthSource: 'equal',
  showEdgeLabels: true,
  edgeLabelFontSize: 10,
  leidenEnabled: false,
  leidenResolution: 1.0,
  sentimentEnabled: true,
  sentimentAxis: 'benevolence',
}
