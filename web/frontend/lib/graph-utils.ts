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

// ── Constants ──────────────────────────────────────────────────────────────────
export const GROUP_ID_GLOBAL = '__global__'
export const GROUP_ID_PRIVATE = '__private__'

// ── buildGroupCards ───────────────────────────────────────────────────────────
// Partitions nodes by group_id when group_members is provided.
// Falls back to a single "__global__" group if grouping is not available.
//
// Scope semantics (mirroring the backend extractor):
//   - Group chat impressions → scope === group_id
//   - Private chat impressions → scope === "global"
//   - The "__private__" group_members key holds private-chat participants
//   - The "__global__" fallback card shows all edges with no scope filter

function _buildGlobalCard(nodes: PersonaNode[], edges: ImpressionEdge[], biWeight: number): GroupCard {
  const pairs = buildEdgePairs(edges, biWeight)
  const lastActive = [...nodes]
    .sort((a, b) => b.data.last_active_at.localeCompare(a.data.last_active_at))[0]
    ?.data.last_active_at ?? new Date().toISOString()
  return {
    group_id: GROUP_ID_GLOBAL,
    name: '全局关系图',
    member_count: nodes.filter(n => !n.data.is_bot).length,
    node_count: nodes.length,
    edge_pair_count: pairs.length,
    last_active: lastActive,
    top_tags: aggregateTopTags(nodes, 4),
    description: `共 ${nodes.length} 个节点，${pairs.length} 对关系`,
    nodes,
    edgePairs: pairs,
  }
}

export function buildGroupCards(
  nodes: PersonaNode[],
  edges: ImpressionEdge[],
  biWeight = 1.5,
  groupMembers?: Record<string, string[]>,
): GroupCard[] {
  if (nodes.length === 0) return []

  // Fall back to global view when no group data or only one group
  if (!groupMembers || Object.keys(groupMembers).length <= 1) {
    return [_buildGlobalCard(nodes, edges, biWeight)]
  }

  const nodeMap = new Map(nodes.map(n => [n.data.id, n]))
  const cards: GroupCard[] = []

  for (const [gid, uids] of Object.entries(groupMembers)) {
    const groupNodes = uids.map(uid => nodeMap.get(uid)).filter(Boolean) as PersonaNode[]
    if (groupNodes.length === 0) continue

    const groupUidSet = new Set(uids)

    // Scope-aware edge filtering:
    //   __private__ card → show impressions scoped to "global" (private-chat interactions)
    //   regular group   → show impressions scoped to that group_id
    const expectedScope = gid === GROUP_ID_PRIVATE ? 'global' : gid
    const groupEdges = edges.filter(e =>
      groupUidSet.has(e.data.source) &&
      groupUidSet.has(e.data.target) &&
      e.data.scope === expectedScope
    )
    const groupPairs = buildEdgePairs(groupEdges, biWeight)

    const lastActive = [...groupNodes]
      .sort((a, b) => b.data.last_active_at.localeCompare(a.data.last_active_at))[0]
      ?.data.last_active_at ?? new Date().toISOString()

    const isPrivate = gid === GROUP_ID_PRIVATE
    cards.push({
      group_id: gid,
      name: isPrivate ? '私聊' : gid,
      member_count: groupNodes.filter(n => !n.data.is_bot).length,
      node_count: groupNodes.length,
      edge_pair_count: groupPairs.length,
      last_active: lastActive,
      top_tags: aggregateTopTags(groupNodes, 4),
      description: isPrivate
        ? `${groupNodes.length} 个私聊参与者，${groupPairs.length} 对关系`
        : `共 ${groupNodes.length} 个成员，${groupPairs.length} 对关系`,
      nodes: groupNodes,
      edgePairs: groupPairs,
    })
  }

  // Sort by last activity descending; fall back to global if no cards built
  if (cards.length === 0) return [_buildGlobalCard(nodes, edges, biWeight)]
  return cards.sort((a, b) => b.last_active.localeCompare(a.last_active))
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
