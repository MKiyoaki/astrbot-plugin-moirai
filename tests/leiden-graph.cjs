const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { createRequire } = require('node:module')
const { test } = require('node:test')
const root = path.resolve(__dirname, '../web/frontend')
const requireFrontend = createRequire(path.join(root, 'package.json'))
const ts = requireFrontend('typescript')
const cache = new Map()
function load(file) {
  const filename = ['', '.ts', '.tsx', '/index.ts'].map(ext => file + ext).find(candidate => fs.existsSync(candidate) && fs.statSync(candidate).isFile())
  if (!filename) throw new Error(`Missing module: ${file}`)
  if (cache.has(filename)) return cache.get(filename).exports
  const module = { exports: {} }
  cache.set(filename, module)
  const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true },
  }).outputText
  const localRequire = spec => {
    if (spec.startsWith('@/')) return load(path.join(root, spec.slice(2)))
    if (spec.startsWith('.')) return load(path.resolve(path.dirname(filename), spec))
    return requireFrontend(spec)
  }
  new Function('require', 'module', 'exports', code)(localRequire, module, module.exports)
  return module.exports
}
const { leidenCluster } = load(path.join(root, 'lib/leiden.ts'))
const { buildExportGraph, toGexf, toNodesCsv } = load(path.join(root, 'lib/graph-export'))
const { clusterHueOffset, getClusterColor } = load(path.join(root, 'lib/colors.ts'))
const sentiment = load(path.join(root, 'lib/sentiment-color.ts'))

const node = id => ({ data: { id, label: id } })
const pair = (a, b, affinity = 1, totalMsgs = 120) => {
  const [lo, hi] = a < b ? [a, b] : [b, a]
  return {
    pairKey: `${lo}|${hi}`, srcId: lo, tgtId: hi, isBidirectional: false, affinity, totalMsgs,
    fwd: { data: { id: `${lo}-${hi}`, source: lo, target: hi, label: 'x', intensity: affinity, affect: 0, power: 0 } },
  }
}
const clique = (prefix, size) => {
  const ids = Array.from({ length: size }, (_, i) => `${prefix}${i}`)
  const pairs = []
  for (let i = 0; i < size; i++) for (let j = i + 1; j < size; j++) pairs.push(pair(ids[i], ids[j]))
  return { ids, pairs }
}
function mulberry32(a) {
  return () => {
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), a | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
function planted(groups, size, pIn, pOut, seed) {
  const rng = mulberry32(seed)
  const ids = []
  for (let g = 0; g < groups; g++) for (let i = 0; i < size; i++) ids.push(`g${g}_${String(i).padStart(3, '0')}`)
  const pairs = []
  for (let i = 0; i < ids.length; i++) {
    for (let j = i + 1; j < ids.length; j++) {
      const same = Math.floor(i / size) === Math.floor(j / size)
      if (rng() < (same ? pIn : pOut)) pairs.push(pair(ids[i], ids[j], 0.2 + rng()))
    }
  }
  return { nodes: ids.map(node), pairs, truth: id => id.split('_')[0] }
}
const communities = map => {
  const out = new Map()
  for (const [id, c] of Object.entries(map)) {
    if (!out.has(c)) out.set(c, [])
    out.get(c).push(id)
  }
  return out
}
function assertConnected(map, pairs) {
  const adj = new Map()
  for (const p of pairs) {
    if (!adj.has(p.srcId)) adj.set(p.srcId, [])
    if (!adj.has(p.tgtId)) adj.set(p.tgtId, [])
    adj.get(p.srcId).push(p.tgtId)
    adj.get(p.tgtId).push(p.srcId)
  }
  for (const [c, members] of communities(map)) {
    const seen = new Set([members[0]])
    const stack = [members[0]]
    while (stack.length) {
      for (const u of adj.get(stack.pop()) ?? []) {
        if (map[u] === c && !seen.has(u)) {
          seen.add(u)
          stack.push(u)
        }
      }
    }
    assert.equal(seen.size, members.length, `community ${c} is disconnected`)
  }
}

const a = clique('a', 5)
const b = clique('b', 5)
const twoCliques = { nodes: [...a.ids, ...b.ids].map(node), pairs: [...a.pairs, ...b.pairs, pair('a0', 'b0')] }

test('two 5-cliques joined by one edge split into the two cliques at γ=1', () => {
  const map = leidenCluster(twoCliques.nodes, twoCliques.pairs, 1, 'equal')
  const groups = communities(map)
  assert.equal(groups.size, 2)
  for (const members of groups.values()) {
    assert.equal(members.length, 5)
    assert.equal(new Set(members.map(id => id[0])).size, 1)
  }
  assert.equal(map.a0, 0, 'equal-size tie goes to the community holding the smallest id')
  assert.equal(map.b0, 1)
})

test('γ=0.01 merges everything and a larger γ never yields fewer communities', () => {
  const gammas = [0.01, 0.05, 0.1, 0.25, 0.5, 1, 1.5, 2, 2.5, 3, 4, 6, 10, 20]
  const counts = gammas.map(g => communities(leidenCluster(twoCliques.nodes, twoCliques.pairs, g, 'equal')).size)
  console.log('  two cliques, γ → communities:', gammas.map((g, i) => `${g}:${counts[i]}`).join(' '))
  assert.equal(counts[0], 1)
  for (let i = 1; i < counts.length; i++) assert.ok(counts[i] >= counts[i - 1], `γ=${gammas[i]} gave ${counts[i]} < ${counts[i - 1]}`)
  assert.equal(counts[counts.length - 1], 10)
})

test('identical input gives identical output, independent of input order', () => {
  const g = planted(4, 25, 0.3, 0.03, 7)
  const first = leidenCluster(g.nodes, g.pairs, 1, 'affinity')
  assert.deepEqual(leidenCluster(g.nodes, g.pairs, 1, 'affinity'), first)
  const rng = mulberry32(99)
  const shuffle = xs => xs.map(x => [rng(), x]).sort((p, q) => p[0] - q[0]).map(p => p[1])
  assert.deepEqual(leidenCluster(shuffle(g.nodes), shuffle(g.pairs), 1, 'affinity'), first)
})

test('isolated nodes are singleton communities', () => {
  const tri = clique('t', 3)
  const nodes = [...tri.ids, 'x', 'y', 'z'].map(node)
  for (const g of [0.01, 1, 5]) {
    const map = leidenCluster(nodes, tri.pairs, g, 'equal')
    assert.equal(Object.keys(map).length, 6)
    const ids = new Set(['x', 'y', 'z'].map(id => map[id]))
    assert.equal(ids.size, 3)
    for (const id of ['x', 'y', 'z']) assert.equal(communities(map).get(map[id]).length, 1)
  }
  assert.deepEqual(leidenCluster(nodes, [], 1, 'equal'), { t0: 0, t1: 1, t2: 2, x: 3, y: 4, z: 5 })
  assert.deepEqual(leidenCluster([], [], 1, 'equal'), {})
})

test('every community is connected', () => {
  const graphs = [twoCliques, planted(4, 25, 0.3, 0.03, 7), planted(6, 20, 0.15, 0.04, 11), planted(10, 12, 0.3, 0.05, 3)]
  for (const g of graphs) {
    for (const gamma of [0.01, 0.3, 1, 2, 5]) {
      for (const source of ['affinity', 'msgs', 'equal']) assertConnected(leidenCluster(g.nodes, g.pairs, gamma, source), g.pairs)
    }
  }
})

test('planted partition is recovered at γ=1', () => {
  const g = planted(4, 25, 0.3, 0.02, 5)
  const map = leidenCluster(g.nodes, g.pairs, 1, 'affinity')
  const groups = communities(map)
  assert.equal(groups.size, 4)
  for (const members of groups.values()) assert.equal(new Set(members.map(g.truth)).size, 1)
})

test('no single node move improves modularity (node optimality)', () => {
  const graphs = [twoCliques, planted(4, 25, 0.3, 0.03, 7), planted(6, 20, 0.15, 0.04, 11)]
  for (const g of graphs) {
    for (const gamma of [0.5, 1, 2]) {
      const map = leidenCluster(g.nodes, g.pairs, gamma, 'affinity')
      const k = new Map()
      const adj = new Map()
      let m2 = 0
      for (const p of g.pairs) {
        m2 += 2 * p.affinity
        for (const [x, y] of [[p.srcId, p.tgtId], [p.tgtId, p.srcId]]) {
          k.set(x, (k.get(x) ?? 0) + p.affinity)
          if (!adj.has(x)) adj.set(x, [])
          adj.get(x).push([y, p.affinity])
        }
      }
      const K = new Map()
      for (const [id, c] of Object.entries(map)) K.set(c, (K.get(c) ?? 0) + (k.get(id) ?? 0))
      for (const [v, own] of Object.entries(map)) {
        const kv = k.get(v) ?? 0
        const to = new Map()
        for (const [u, w] of adj.get(v) ?? []) to.set(map[u], (to.get(map[u]) ?? 0) + w)
        const stay = (to.get(own) ?? 0) - gamma * kv * (K.get(own) - kv) / m2
        assert.ok(stay >= -1e-9, `${v} would rather be alone at γ=${gamma}`)
        for (const [c, w] of to) if (c !== own) assert.ok(w - gamma * kv * K.get(c) / m2 <= stay + 1e-9, `${v} would rather join ${c} at γ=${gamma}`)
      }
    }
  }
})

test('edge weights follow the active weight source', () => {
  const nodes = ['a', 'b', 'c', 'd'].map(node)
  const pairs = [pair('a', 'b', 5, 1), pair('c', 'd', 5, 1), pair('b', 'c', 0.1, 600), pair('a', 'd', 0.1, 600)]
  const byAffinity = leidenCluster(nodes, pairs, 1, 'affinity')
  assert.equal(byAffinity.a, byAffinity.b)
  assert.equal(byAffinity.c, byAffinity.d)
  assert.notEqual(byAffinity.a, byAffinity.c)
  const byMsgs = leidenCluster(nodes, pairs, 1, 'msgs')
  assert.equal(byMsgs.b, byMsgs.c)
  assert.equal(byMsgs.a, byMsgs.d)
  assert.notEqual(byMsgs.a, byMsgs.b)
})

test('GEXF and CSV exports carry the community ids', () => {
  const map = leidenCluster(twoCliques.nodes, twoCliques.pairs, 1, 'equal')
  const graph = buildExportGraph({
    name: 't', nodes: twoCliques.nodes, edgePairs: twoCliques.pairs, positions: null, edgeWeightSource: 'equal',
    nodeRadius: () => 12, nodeColor: () => '#888888', edgeColor: () => '#aaaaaa', clusterOf: id => map[id],
  })
  assert.deepEqual(graph.nodes.map(n => n.cluster), twoCliques.nodes.map(n => map[n.data.id]))
  const gexf = toGexf(graph)
  const clusterAttr = gexf.match(/<attribute id="(\d+)" title="Cluster" type="integer"/)
  assert.ok(clusterAttr, 'GEXF declares the Cluster attribute')
  assert.ok(gexf.includes(`<attvalue for="${clusterAttr[1]}" value="1"`), 'GEXF carries cluster 1')
  const [header, ...rows] = toNodesCsv(graph).trim().split(/\r?\n/)
  const col = header.split(',').indexOf('Cluster')
  assert.ok(col >= 0, 'CSV has a Cluster column')
  assert.deepEqual(rows.map(r => r.split(',')[col]).sort(), ['0', '0', '0', '0', '0', '1', '1', '1', '1', '1'])
})

test('stays fast on a few thousand nodes', () => {
  const rng = mulberry32(1234)
  const n = 3000
  const ids = Array.from({ length: n }, (_, i) => `n${String(i).padStart(5, '0')}`)
  const pairs = []
  const seen = new Set()
  for (let i = 0; i < n; i++) {
    const block = Math.floor(i / 50)
    for (let k = 0; k < 5; k++) {
      const j = rng() < 0.8 ? block * 50 + Math.floor(rng() * 50) : Math.floor(rng() * n)
      if (j === i) continue
      const key = i < j ? `${i}|${j}` : `${j}|${i}`
      if (seen.has(key)) continue
      seen.add(key)
      pairs.push(pair(ids[i], ids[j], 0.1 + rng()))
    }
  }
  const nodes = ids.map(node)
  const t0 = performance.now()
  const map = leidenCluster(nodes, pairs, 1, 'affinity')
  const ms = performance.now() - t0
  console.log(`  ${n} nodes / ${pairs.length} edges: ${ms.toFixed(0)} ms, ${communities(map).size} communities`)
  assert.ok(ms < 2000, `took ${ms} ms`)
  assertConnected(map, pairs)
})

test('cluster colours split the hue wheel evenly and never repeat', () => {
  for (let k = 1; k <= 24; k++) {
    const offsets = Array.from({ length: k }, (_, i) => clusterHueOffset(i, k))
    assert.equal(offsets[0], 0)
    assert.equal(new Set(offsets).size, k, `k=${k} repeats a hue`)
    const step = 360 / k
    for (const o of offsets) {
      assert.ok(o >= 0 && o < 360)
      assert.ok(Math.abs(o / step - Math.round(o / step)) < 1e-3, `k=${k} offset ${o} is off the ${step}° grid`)
    }
    for (let i = 1; i < k && k > 6; i++) {
      const d = Math.abs(offsets[i] - offsets[i - 1])
      assert.ok(Math.min(d, 360 - d) > step + 1e-9, `k=${k}: ranks ${i - 1} and ${i} are wheel neighbours`)
    }
  }
  assert.match(getClusterColor(3, 10), /^oklch\(from var\(--color-palette-1\) l max\(c, 0\.08\) calc\(h \+ [0-9.]+\)\)$/)
  assert.equal(getClusterColor(10, 10), getClusterColor(0, 10))
})

test('sentiment colours are scaled to the pairs shown, not fixed cut-offs', () => {
  const { pairSentiment, pairSentimentScale, sentimentScale, sentimentLevel, sentimentLevelColor, SENTIMENT_LEVELS, SENTIMENT_MARKER_LEVELS, SENTIMENT_NEUTRAL_COLOR } = sentiment
  const edge = (affect, power) => ({ data: { affect, power } })
  const bi = { isBidirectional: true, fwd: edge(0.2, -0.1), bwd: edge(0.1, 0.3) }
  assert.ok(Math.abs(pairSentiment(bi, 'benevolence') - 0.15) < 1e-9)
  assert.ok(Math.abs(pairSentiment(bi, 'power') - 0.1) < 1e-9)
  assert.equal(pairSentiment({ isBidirectional: false, fwd: edge(-0.2, 0.4) }, 'power'), 0.4)

  assert.equal(sentimentLevel(0, 0.1), 0)
  assert.equal(sentimentLevel(0.1, 0.1), SENTIMENT_LEVELS)
  assert.equal(sentimentLevel(-0.5, 0.1), -SENTIMENT_LEVELS)
  assert.equal(sentimentLevel(0.01, 0.1), 0)
  assert.equal(sentimentLevelColor(0), SENTIMENT_NEUTRAL_COLOR)
  assert.equal(sentimentLevelColor(SENTIMENT_LEVELS), '#2d7d46')
  assert.equal(sentimentLevelColor(-SENTIMENT_LEVELS), '#c0392b')
  const all = [0, ...SENTIMENT_MARKER_LEVELS].map(sentimentLevelColor)
  assert.equal(new Set(all).size, 2 * SENTIMENT_LEVELS + 1)
  assert.ok(!SENTIMENT_MARKER_LEVELS.includes(0))

  assert.equal(sentimentScale([]), 0.02)
  assert.equal(sentimentScale([0.001, -0.002, 0.003]), 0.02)

  const rng = mulberry32(99)
  const values = Array.from({ length: 1400 }, () => (rng() - 0.45) * 0.12 * (rng() < 0.05 ? 4 : 1))
  const pairs = values.map(v => ({ isBidirectional: false, fwd: edge(v, v) }))
  const scale = pairSentimentScale(pairs, 'benevolence')
  const levels = values.map(v => sentimentLevel(v, scale))
  const coloured = levels.filter(l => l !== 0).length
  assert.equal(values.filter(v => v > 0.3 || v < -0.1).length < 60, true)
  assert.ok(coloured > values.length * 0.4, `only ${coloured} of ${values.length} coloured`)

  const grown = pairs.map(p => ({ ...p, fwd: edge(p.fwd.data.affect * 5, 0) }))
  const grownScale = pairSentimentScale(grown, 'benevolence')
  assert.deepEqual(grown.map(p => sentimentLevel(pairSentiment(p, 'benevolence'), grownScale)), levels)
})
