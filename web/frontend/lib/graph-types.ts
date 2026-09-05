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

// ── Auto settings ─────────────────────────────────────────────────────────────
// The "generate the settings that fit this graph best" button.
//
// Gephi Desktop's ForceAtlas2.resetPropertiesValues() is NOT this function — it
// is Gephi's *defaults initialiser*, re-run per graph (see setGraphModel), and
// its only graph-aware terms are two thresholds. Porting it here and then also
// deriving DEFAULT_PHYSICS_PARAMS from it made the button a guaranteed no-op on
// every graph under 100 nodes. Gephi Lite keeps the two apart — its panel
// defaults are graphology's FA2_DEFAULT_SETTINGS while its autoSettings button
// returns inferSettings(graph) — which is why its button always does something.
//
// The values below are measured against this codebase's kernel and pixel scale
// rather than inherited, because two things here differ from both Gephis:
// node radii are 12–22 screen px (Gephi's default node size is 10), and the
// view auto-fits after every solve, which normalises absolute layout size away.
// Once size is normalised, scalingRatio stops mattering above ~60 nodes and the
// only setting that measurably improves the picture is adjustSizes.

export type AutoPhysicsSettings = Pick<
  PhysicsParams,
  | 'scalingRatio' | 'strongGravityMode' | 'gravity'
  | 'outboundAttractionDistribution' | 'linLogMode' | 'adjustSizes'
  | 'edgeWeightInfluence' | 'jitterTolerance'
  | 'barnesHutOptimize' | 'barnesHutTheta'
>

/**
 * One boundary drives both performance switches, deliberately.
 *
 * It is the measured crossover for this kernel's quadtree — not Gephi's 1000:
 * at N=1200 the approximation still runs at 0.92x the speed of brute force and
 * only overtakes it around 1600, so switching earlier costs time and buys
 * nothing. Below it, brute-force repulsion is affordable and adjustSizes (which
 * the kernel can only serve brute-force) is worth having; at or above it, the
 * quadtree takes over and adjustSizes has to go.
 *
 * Keeping them on the same boundary also guarantees the two branches always
 * differ from DEFAULT_PHYSICS_PARAMS in at least one field. Two separate
 * thresholds left a dead band between them where the button did nothing again.
 */
const BRUTE_FORCE_MAX_NODES = 1500

export function autoPhysicsSettings(nodeCount: number): AutoPhysicsSettings {
  return {
    // Flat 10: with auto-fit in place this is scale-invariant above ~60 nodes,
    // and 10 measured best below that (N=15: 106px mean separation vs 45px at 2).
    scalingRatio: 10,
    // linLog and dissuadeHubs both measured worse on hub-shaped chat graphs —
    // they collapse the spokes into the bot. Same verdict as Gephi's defaults.
    strongGravityMode: false,
    gravity: 1.0,
    outboundAttractionDistribution: false,
    linLogMode: false,
    // The one setting that actually changes the picture: at N=400 it lifts mean
    // on-screen separation from 12px to 23px and the closest pair from 4px to
    // 16px, against a node radius of 17. Off in both Gephi and Gephi Lite.
    adjustSizes: nodeCount < BRUTE_FORCE_MAX_NODES,
    edgeWeightInfluence: 1.0,
    jitterTolerance: 1.0,
    barnesHutOptimize: nodeCount >= BRUTE_FORCE_MAX_NODES,
    barnesHutTheta: 1.2,
  }
}

/** Fields autoPhysicsSettings() writes, for diffing against the current state. */
export const AUTO_PHYSICS_KEYS = [
  'scalingRatio', 'strongGravityMode', 'gravity',
  'outboundAttractionDistribution', 'linLogMode', 'adjustSizes',
  'edgeWeightInfluence', 'jitterTolerance',
  'barnesHutOptimize', 'barnesHutTheta',
] as const satisfies readonly (keyof AutoPhysicsSettings)[]

/** How many of the auto fields differ from what the panel currently holds. */
export function countAutoChanges(
  current: PhysicsParams,
  next: AutoPhysicsSettings,
): number {
  return AUTO_PHYSICS_KEYS.reduce(
    (n, k) => (current[k] === next[k] ? n : n + 1),
    0,
  )
}

// ── Defaults ──────────────────────────────────────────────────────────────────
// Deliberately spelled out rather than derived from autoPhysicsSettings(): the
// panel's resting state and the button's output have to be able to differ, or
// the button cannot do anything. These are Gephi's own small-graph defaults.

export const DEFAULT_PHYSICS_PARAMS: PhysicsParams = {
  layoutMode: 'circular',
  locked: false,

  // Tuning
  scalingRatio: 10.0,
  strongGravityMode: false,
  gravity: 1.0,

  // Behavior Alternatives
  outboundAttractionDistribution: false,
  linLogMode: false,
  adjustSizes: false,
  edgeWeightInfluence: 1.0,

  // Performance
  jitterTolerance: 1.0,
  barnesHutOptimize: false,
  barnesHutTheta: 1.2,

  // Moirai-specific. 300 is measured, not guessed: on-screen separation stops
  // improving past ~300 iterations at every graph size from 15 to 800 nodes,
  // so there is nothing to gain by scaling this with the node count.
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
