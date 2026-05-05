import type { PersonaNode, ImpressionEdge } from './api'
import type { EdgePair, GroupCard, PositionMap } from './graph-types'

// ── buildEdgePairs ────────────────────────────────────────────────────────────
// Pairs ImpressionEdges into EdgePairs. Bidirectional when both A→B and B→A
// exist. pairKey = `${minUID}|${maxUID}` is stable regardless of direction.

export function buildEdgePairs(edges: ImpressionEdge[], biWeight = 1.5): EdgePair[] {
  const map = new Map<string, { fwd?: ImpressionEdge; bwd?: ImpressionEdge; srcId: string; tgtId: string }>()

  for (const edge of edges) {
    const a = edge.data.source
    const b = edge.data.target
    const [lo, hi] = a < b ? [a, b] : [b, a]
    const key = `${lo}|${hi}`

    if (!map.has(key)) {
      map.set(key, { srcId: lo, tgtId: hi })
    }
    const entry = map.get(key)!
    if (a < b) {
      entry.fwd = edge
    } else {
      entry.bwd = edge
    }
  }

  const pairs: EdgePair[] = []
  for (const [pairKey, entry] of map) {
    if (!entry.fwd && !entry.bwd) continue
    // Guarantee fwd is always set; if only bwd exists, swap
    const fwd = entry.fwd ?? entry.bwd!
    const bwd = entry.fwd ? entry.bwd : undefined
    const isBidirectional = !!fwd && !!bwd
    const affinity = computeAffinity({ fwd, bwd, isBidirectional } as EdgePair, biWeight)
    const fwdMsgs = (fwd.data as { msg_count?: number }).msg_count ?? 1
    const bwdMsgs = bwd ? ((bwd.data as { msg_count?: number }).msg_count ?? 0) : 0
    pairs.push({
      pairKey,
      srcId: entry.srcId,
      tgtId: entry.tgtId,
      fwd,
      bwd,
      isBidirectional,
      affinity,
      totalMsgs: fwdMsgs + bwdMsgs,
    })
  }
  return pairs
}

// ── computeAffinity ───────────────────────────────────────────────────────────
// biWeight amplifies mutual relationships.

export function computeAffinity(pair: Pick<EdgePair, 'fwd' | 'bwd' | 'isBidirectional'>, biWeight: number): number {
  if (pair.isBidirectional && pair.bwd) {
    return (pair.fwd.data.intensity + pair.bwd.data.intensity) * biWeight
  }
  return pair.fwd.data.intensity
}

// ── buildGroupCards ───────────────────────────────────────────────────────────
// Partitions nodes by group_id inferred from node bound_identities.
// Falls back to a single "__global__" group if no grouping is possible.

export function buildGroupCards(
  nodes: PersonaNode[],
  edges: ImpressionEdge[],
  biWeight = 1.5,
): GroupCard[] {
  if (nodes.length === 0) return []

  // Try to infer group from node data. PersonaNode doesn't carry group_id
  // natively, so we create a single global group (matching the demo data).
  const globalNodes = nodes
  const globalEdges = edges
  const globalPairs = buildEdgePairs(globalEdges, biWeight)

  // Compute last_active from nodes
  const lastActive = [...nodes]
    .sort((a, b) => b.data.last_active_at.localeCompare(a.data.last_active_at))[0]
    ?.data.last_active_at ?? new Date().toISOString()

  const card: GroupCard = {
    group_id: '__global__',
    name: '全局关系图',
    member_count: globalNodes.filter(n => !n.data.is_bot).length,
    node_count: globalNodes.length,
    edge_pair_count: globalPairs.length,
    last_active: lastActive,
    top_tags: aggregateTopTags(globalNodes, 4),
    description: `共 ${globalNodes.length} 个节点，${globalPairs.length} 对关系`,
    nodes: globalNodes,
    edgePairs: globalPairs,
  }

  return [card]
}

// ── circularLayout ────────────────────────────────────────────────────────────
// Places nodes evenly on a circle. First node appears at the top (−π/2 offset).

export function circularLayout(
  nodes: PersonaNode[],
  cx: number,
  cy: number,
  r: number,
): PositionMap {
  const pos: PositionMap = {}
  const n = nodes.length
  if (n === 0) return pos
  if (n === 1) {
    pos[nodes[0].data.id] = { x: cx, y: cy }
    return pos
  }
  for (let i = 0; i < n; i++) {
    const angle = (i / n) * Math.PI * 2 - Math.PI / 2
    pos[nodes[i].data.id] = {
      x: cx + Math.cos(angle) * r,
      y: cy + Math.sin(angle) * r,
    }
  }
  return pos
}

// ── computeNodeRadius ─────────────────────────────────────────────────────────
// Linear map from message count to visual radius [12, 22] px.

export function computeNodeRadius(msgs: number, minMsgs: number, maxMsgs: number): number {
  if (maxMsgs === minMsgs) return 17
  const t = Math.max(0, Math.min(1, (msgs - minMsgs) / (maxMsgs - minMsgs)))
  return 12 + t * 10
}

// ── mockCluster ───────────────────────────────────────────────────────────────
// BFS-based greedy clustering (Leiden approximation for MVP).
// Returns a map of nodeId → clusterId.

export function mockCluster(
  nodes: PersonaNode[],
  edgePairs: EdgePair[],
  _resolution = 1.0,
): Record<string, number> {
  const adj = new Map<string, Set<string>>()
  for (const n of nodes) adj.set(n.data.id, new Set())
  for (const p of edgePairs) {
    adj.get(p.srcId)?.add(p.tgtId)
    adj.get(p.tgtId)?.add(p.srcId)
  }

  const cluster: Record<string, number> = {}
  let cid = 0
  for (const n of nodes) {
    const id = n.data.id
    if (cluster[id] !== undefined) continue
    const queue = [id]
    cluster[id] = cid
    while (queue.length > 0) {
      const curr = queue.shift()!
      for (const nb of adj.get(curr) ?? []) {
        if (cluster[nb] === undefined) {
          cluster[nb] = cid
          queue.push(nb)
        }
      }
    }
    cid++
  }
  return cluster
}

// ── aggregateTopTags ──────────────────────────────────────────────────────────
// Returns the top-k content_tags by frequency across all nodes.

export function aggregateTopTags(nodes: PersonaNode[], k = 4): string[] {
  const freq = new Map<string, number>()
  for (const n of nodes) {
    for (const tag of n.data.attrs?.content_tags ?? []) {
      freq.set(tag, (freq.get(tag) ?? 0) + 1)
    }
  }
  return [...freq.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, k)
    .map(([tag]) => tag)
}
