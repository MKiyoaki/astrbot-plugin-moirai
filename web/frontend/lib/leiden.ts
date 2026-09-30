import type { PersonaNode } from './api'
import type { EdgePair, EdgeWeightSource } from './graph-types'
import { edgePairWeight } from './graph-utils'

// ── Leiden community detection ────────────────────────────────────────────────
// Traag, Waltman & van Eck (2019), "From Louvain to Leiden: guaranteeing
// well-connected communities". The quality function is modularity with a
// resolution parameter γ (Reichardt–Bornholdt):
//
//   Q = Σ_c [ w_in(c)/m − γ·(K_c/2m)² ]
//
// w_in(c) is the edge weight inside community c, K_c the summed weighted degree
// of its members and m the total edge weight. A larger γ gives smaller, more
// numerous communities, which is what the resolution slider promises.
//
// Every pass runs fast local moving → refinement → aggregation until each
// community is a single aggregate node. Refinement only merges nodes inside a
// community, so every community stays connected. Passes repeat from the
// previous result until the partition stops changing (at most MAX_PASSES).
//
// The result is deterministic: nodes are indexed in id order and all
// randomness comes from a fixed-seed PRNG, so re-rendering or dragging a node
// never recolours the graph.

const SEED = 0x4c656964
const MAX_PASSES = 10
const MAX_LEVELS = 100
// Refinement picks among non-negative moves with probability ∝ exp(Δ/θ). Δ is
// divided by the node's own degree first, so θ means the same thing whichever
// edge weight source is active.
const RANDOMNESS = 0.01

interface Graph {
  n: number
  offsets: Int32Array      // CSR row starts, length n + 1; self-loops excluded
  targets: Int32Array
  weights: Float64Array
  selfLoop: Float64Array   // internal weight carried by an aggregate node
  degree: Float64Array     // weighted degree, self-loop counted twice
  total: number            // 2m
}

function mulberry32(seed: number): () => number {
  let a = seed | 0
  return () => {
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), a | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function identity(n: number): Int32Array {
  const out = new Int32Array(n)
  for (let i = 0; i < n; i++) out[i] = i
  return out
}

function shuffled(n: number, rng: () => number): Int32Array {
  const out = identity(n)
  for (let i = n - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1))
    const t = out[i]
    out[i] = out[j]
    out[j] = t
  }
  return out
}

// Renumbers community ids to 0..count-1 in order of first appearance.
function compact(membership: Int32Array): { part: Int32Array; count: number } {
  const map = new Map<number, number>()
  const part = new Int32Array(membership.length)
  for (let v = 0; v < membership.length; v++) {
    let c = map.get(membership[v])
    if (c === undefined) {
      c = map.size
      map.set(membership[v], c)
    }
    part[v] = c
  }
  return { part, count: map.size }
}

function buildGraph(n: number, src: number[], dst: number[], w: number[], selfLoop: Float64Array): Graph {
  const offsets = new Int32Array(n + 1)
  for (let e = 0; e < src.length; e++) {
    offsets[src[e] + 1]++
    offsets[dst[e] + 1]++
  }
  for (let v = 0; v < n; v++) offsets[v + 1] += offsets[v]
  const fill = offsets.slice(0, n)
  const targets = new Int32Array(offsets[n])
  const weights = new Float64Array(offsets[n])
  const degree = new Float64Array(n)
  for (let e = 0; e < src.length; e++) {
    const a = src[e]
    const b = dst[e]
    targets[fill[a]] = b
    weights[fill[a]++] = w[e]
    targets[fill[b]] = a
    weights[fill[b]++] = w[e]
    degree[a] += w[e]
    degree[b] += w[e]
  }
  let total = 0
  for (let v = 0; v < n; v++) {
    degree[v] += 2 * selfLoop[v]
    total += degree[v]
  }
  return { n, offsets, targets, weights, selfLoop, degree, total }
}

// ── Fast local moving ─────────────────────────────────────────────────────────
// Moves each node to the neighbouring (or an empty) community with the best
// modularity gain. Only neighbours that end up outside the node's new
// community are queued again, instead of sweeping every node until stable.

function moveNodes(g: Graph, membership: Int32Array, gamma: number, rng: () => number): void {
  const n = g.n
  const scale = gamma / g.total
  const tol = 1e-12 * g.total
  const clusterWeight = new Float64Array(n)
  const clusterSize = new Int32Array(n)
  for (let v = 0; v < n; v++) {
    clusterWeight[membership[v]] += g.degree[v]
    clusterSize[membership[v]]++
  }
  const empty: number[] = []
  for (let c = n - 1; c >= 0; c--) if (clusterSize[c] === 0) empty.push(c)

  const queue = shuffled(n, rng)
  const queued = new Uint8Array(n).fill(1)
  let head = 0
  let pending = n
  const edgeW = new Float64Array(n)
  const seen = new Uint8Array(n)
  const neigh = new Int32Array(n)

  while (pending > 0) {
    const v = queue[head]
    head = (head + 1) % n
    pending--
    queued[v] = 0

    const own = membership[v]
    const k = g.degree[v]
    clusterWeight[own] -= k
    clusterSize[own]--

    let count = 0
    for (let e = g.offsets[v]; e < g.offsets[v + 1]; e++) {
      const c = membership[g.targets[e]]
      if (!seen[c]) {
        seen[c] = 1
        neigh[count++] = c
      }
      edgeW[c] += g.weights[e]
    }

    let best = own
    let bestGain = edgeW[own] - scale * k * clusterWeight[own]
    for (let i = 0; i < count; i++) {
      const c = neigh[i]
      if (c === own) continue
      const gain = edgeW[c] - scale * k * clusterWeight[c]
      if (gain > bestGain + tol) {
        best = c
        bestGain = gain
      }
    }
    // Own community emptied by the removal is itself the "empty" option.
    let fromEmpty = false
    if (clusterSize[own] > 0 && bestGain < -tol && empty.length > 0) {
      best = empty[empty.length - 1]
      fromEmpty = true
    }

    for (let i = 0; i < count; i++) {
      edgeW[neigh[i]] = 0
      seen[neigh[i]] = 0
    }

    clusterWeight[best] += k
    clusterSize[best]++
    if (best === own) continue
    if (fromEmpty) empty.pop()
    if (clusterSize[own] === 0) empty.push(own)
    membership[v] = best
    for (let e = g.offsets[v]; e < g.offsets[v + 1]; e++) {
      const u = g.targets[e]
      if (!queued[u] && membership[u] !== best) {
        queue[(head + pending) % n] = u
        pending++
        queued[u] = 1
      }
    }
  }
}

// ── Refinement ────────────────────────────────────────────────────────────────
// Starts from singletons and merges nodes only within their community from the
// local-moving phase. A node or sub-community takes part only while it is
// well connected to the rest of that community (E(C, S−C) ≥ γ·K_C·(K_S−K_C)/2m),
// and a node joins a sub-community at random among the non-negative moves.

function refine(g: Graph, membership: Int32Array, gamma: number, rng: () => number): Int32Array {
  const n = g.n
  const scale = gamma / g.total
  const commWeight = new Float64Array(n)
  for (let v = 0; v < n; v++) commWeight[membership[v]] += g.degree[v]

  const refined = identity(n)
  const clusterWeight = Float64Array.from(g.degree)
  const external = new Float64Array(n)
  const nonSingleton = new Uint8Array(n)
  for (let v = 0; v < n; v++) {
    for (let e = g.offsets[v]; e < g.offsets[v + 1]; e++) {
      if (membership[g.targets[e]] === membership[v]) external[v] += g.weights[e]
    }
  }

  const edgeW = new Float64Array(n)
  const seen = new Uint8Array(n)
  const neigh = new Int32Array(n)
  const gains = new Float64Array(n)
  const cumulative = new Float64Array(n)

  for (const v of shuffled(n, rng)) {
    const r = refined[v]
    if (nonSingleton[r]) continue
    const s = membership[v]
    const ks = commWeight[s]
    const k = g.degree[v]
    if (external[r] < scale * k * (ks - k)) continue

    clusterWeight[r] = 0
    external[r] = 0
    let count = 0
    neigh[count++] = r
    seen[r] = 1
    for (let e = g.offsets[v]; e < g.offsets[v + 1]; e++) {
      const u = g.targets[e]
      if (membership[u] !== s) continue
      const c = refined[u]
      if (!seen[c]) {
        seen[c] = 1
        neigh[count++] = c
      }
      edgeW[c] += g.weights[e]
    }

    let maxGain = 0
    for (let i = 0; i < count; i++) {
      const c = neigh[i]
      gains[i] = -1
      if (external[c] < scale * clusterWeight[c] * (ks - clusterWeight[c])) continue
      const gain = edgeW[c] - scale * k * clusterWeight[c]
      if (gain < 0) continue
      gains[i] = gain
      if (gain > maxGain) maxGain = gain
    }
    const temperature = RANDOMNESS * (k > 0 ? k : 1)
    let sum = 0
    for (let i = 0; i < count; i++) {
      if (gains[i] >= 0) sum += Math.exp((gains[i] - maxGain) / temperature)
      cumulative[i] = sum
    }
    const x = rng() * sum
    let chosen = r
    for (let i = 0; i < count; i++) {
      if (gains[i] >= 0 && cumulative[i] > x) {
        chosen = neigh[i]
        break
      }
    }

    for (let i = 0; i < count; i++) {
      edgeW[neigh[i]] = 0
      seen[neigh[i]] = 0
    }

    clusterWeight[chosen] += k
    for (let e = g.offsets[v]; e < g.offsets[v + 1]; e++) {
      const u = g.targets[e]
      if (membership[u] !== s) continue
      external[chosen] += refined[u] === chosen ? -g.weights[e] : g.weights[e]
    }
    if (chosen !== r) {
      refined[v] = chosen
      nonSingleton[chosen] = 1
    }
  }
  return refined
}

// ── Aggregation ───────────────────────────────────────────────────────────────
// One node per community of `part`; edges inside a community become the new
// node's self-loop, edges between communities are summed.

function aggregate(g: Graph, part: Int32Array, count: number): Graph {
  const start = new Int32Array(count + 1)
  for (let v = 0; v < g.n; v++) start[part[v] + 1]++
  for (let c = 0; c < count; c++) start[c + 1] += start[c]
  const fill = start.slice(0, count)
  const members = new Int32Array(g.n)
  for (let v = 0; v < g.n; v++) members[fill[part[v]]++] = v

  const selfLoop = new Float64Array(count)
  const degree = new Float64Array(count)
  const offsets = new Int32Array(count + 1)
  const targets: number[] = []
  const weights: number[] = []
  const acc = new Float64Array(count)
  const stamp = new Int32Array(count).fill(-1)
  const touched: number[] = []

  for (let c = 0; c < count; c++) {
    for (let i = start[c]; i < start[c + 1]; i++) {
      const v = members[i]
      selfLoop[c] += g.selfLoop[v]
      degree[c] += g.degree[v]
      for (let e = g.offsets[v]; e < g.offsets[v + 1]; e++) {
        const cu = part[g.targets[e]]
        if (cu === c) {
          selfLoop[c] += g.weights[e] / 2
          continue
        }
        if (stamp[cu] !== c) {
          stamp[cu] = c
          acc[cu] = 0
          touched.push(cu)
        }
        acc[cu] += g.weights[e]
      }
    }
    for (const cu of touched) {
      targets.push(cu)
      weights.push(acc[cu])
    }
    touched.length = 0
    offsets[c + 1] = targets.length
  }

  return {
    n: count,
    offsets,
    targets: Int32Array.from(targets),
    weights: Float64Array.from(weights),
    selfLoop,
    degree,
    total: g.total,
  }
}

// ── One Leiden pass ───────────────────────────────────────────────────────────
// Level loop of the paper: stops once local moving leaves every aggregate node
// in its own community. When refinement merges nothing, the graph is
// aggregated on the local-moving partition instead so each level still shrinks.

function leidenPass(base: Graph, initial: Int32Array, gamma: number, rng: () => number): Int32Array {
  let g = base
  let membership: Int32Array = Int32Array.from(initial)
  const nodeOf = identity(base.n)

  for (let level = 0; level < MAX_LEVELS; level++) {
    moveNodes(g, membership, gamma, rng)
    const { part, count } = compact(membership)
    membership = part
    if (count === g.n) break

    let { part: refined, count: refinedCount } = compact(refine(g, part, gamma, rng))
    let next: Int32Array
    if (refinedCount === g.n) {
      refined = part
      refinedCount = count
      next = identity(count)
    } else {
      next = new Int32Array(refinedCount)
      for (let v = 0; v < g.n; v++) next[refined[v]] = part[v]
    }
    for (let i = 0; i < base.n; i++) nodeOf[i] = refined[nodeOf[i]]
    g = aggregate(g, refined, refinedCount)
    membership = next
  }

  const flat = new Int32Array(base.n)
  for (let i = 0; i < base.n; i++) flat[i] = membership[nodeOf[i]]
  return flat
}

function samePartition(a: Int32Array, b: Int32Array): boolean {
  const x = compact(a).part
  const y = compact(b).part
  for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) return false
  return true
}

// Safety net: a disconnected community is split into its components. With
// no edges between the parts this only raises Q, so it never costs quality.
function splitDisconnected(g: Graph, membership: Int32Array): Int32Array {
  const out = new Int32Array(g.n).fill(-1)
  const stack: number[] = []
  let next = 0
  for (let s = 0; s < g.n; s++) {
    if (out[s] !== -1) continue
    out[s] = next
    stack.push(s)
    while (stack.length > 0) {
      const v = stack.pop()!
      for (let e = g.offsets[v]; e < g.offsets[v + 1]; e++) {
        const u = g.targets[e]
        if (out[u] === -1 && membership[u] === membership[s]) {
          out[u] = next
          stack.push(u)
        }
      }
    }
    next++
  }
  return out
}

// ── leidenCluster ─────────────────────────────────────────────────────────────
// Returns nodeId → communityId. Edge weights follow edgePairWeight() for the
// active weight source, so communities agree with the ForceAtlas2 layout;
// isolated nodes are singleton communities. Ids are ranked by community size
// (largest first, ties broken by the smallest member id) so palette colours
// stay put when the resolution changes a little.

export function leidenCluster(
  nodes: PersonaNode[],
  edgePairs: EdgePair[],
  resolution = 1.0,
  weightSource: EdgeWeightSource = 'affinity',
): Record<string, number> {
  const ids = [...new Set(nodes.map(n => n.data.id))].sort()
  const n = ids.length
  if (n === 0) return {}
  const index = new Map(ids.map((id, i) => [id, i]))

  // Edges are sorted by endpoint index so the result does not depend on the
  // order the API happened to return them in.
  const edges: [number, number, number][] = []
  const selfLoop = new Float64Array(n)
  for (const pair of edgePairs) {
    const a = index.get(pair.srcId)
    const b = index.get(pair.tgtId)
    if (a === undefined || b === undefined) continue
    const weight = edgePairWeight(pair, weightSource)
    if (!(weight > 0) || !Number.isFinite(weight)) continue
    if (a === b) selfLoop[a] += weight
    else edges.push(a < b ? [a, b, weight] : [b, a, weight])
  }
  edges.sort((x, y) => x[0] - y[0] || x[1] - y[1])
  const base = buildGraph(n, edges.map(e => e[0]), edges.map(e => e[1]), edges.map(e => e[2]), selfLoop)
  const gamma = Number.isFinite(resolution) ? Math.max(0, resolution) : 1

  let membership: Int32Array = identity(n)
  if (base.total > 0) {
    const rng = mulberry32(SEED)
    for (let pass = 0; pass < MAX_PASSES; pass++) {
      const next = leidenPass(base, membership, gamma, rng)
      const stable = samePartition(membership, next)
      membership = next
      if (stable) break
    }
  }
  membership = splitDisconnected(base, membership)

  const groups = new Map<number, number[]>()
  for (let i = 0; i < n; i++) {
    const list = groups.get(membership[i])
    if (list) list.push(i)
    else groups.set(membership[i], [i])
  }
  const ranked = [...groups.values()].sort((a, b) => b.length - a.length || a[0] - b[0])
  const cluster: Record<string, number> = {}
  ranked.forEach((members, rank) => {
    for (const i of members) cluster[ids[i]] = rank
  })
  return cluster
}
