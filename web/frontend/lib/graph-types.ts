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

export interface PhysicsParams {
  layoutMode: 'circular' | 'force'
  locked: boolean
  scalingRatio: number      // 0.1 – 15: global repulsion strength
  gravity: number           // 0 – 5: center gravity
  edgeWeightInfluence: number  // 0 – 2: edge weight on attraction
  damping: number           // 0.1 – 1: velocity damping per step
  iterations: number        // 40 – 400
  linLog: boolean
  preventOverlap: boolean
  dissuadeHubs: boolean
  gravSource: 'affinity' | 'msgs' | 'equal'
  biWeight: number          // 1.0 – 2.0: bidirectional affinity multiplier
}

export interface VisualParams {
  showBot: boolean
  edgeOpacity: number         // 0.05 – 1
  labelZoomThreshold: number  // minimum node radius to show label
  showArrows: boolean
  arrowSize: number
  edgeWidthSource: 'equal' | 'affinity' | 'msgs'
  leidenEnabled: boolean
  leidenResolution: number    // 0.001 – 10
  sentimentEnabled: boolean
}

// ── View / Position ───────────────────────────────────────────────────────────

export type ViewMode = 'all' | 'member'

export type PositionMap = Record<string, { x: number; y: number }>

// ── Defaults ──────────────────────────────────────────────────────────────────

export const DEFAULT_PHYSICS_PARAMS: PhysicsParams = {
  layoutMode: 'circular',
  locked: false,
  scalingRatio: 2.5,
  gravity: 1.0,
  edgeWeightInfluence: 1.0,
  damping: 0.4,
  iterations: 120,
  linLog: false,
  preventOverlap: true,
  dissuadeHubs: false,
  gravSource: 'affinity',
  biWeight: 1.5,
}

export const DEFAULT_VISUAL_PARAMS: VisualParams = {
  showBot: true,
  edgeOpacity: 0.7,
  labelZoomThreshold: 0,
  showArrows: true,
  arrowSize: 6,
  edgeWidthSource: 'equal',
  leidenEnabled: false,
  leidenResolution: 1.0,
  sentimentEnabled: true,
}
