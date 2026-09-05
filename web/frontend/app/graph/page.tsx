'use client'

import { useEffect, useState, useRef, useCallback, useMemo } from 'react'
import { ChevronLeft, Maximize2, XCircle, Search, Share2, RefreshCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PageHeader } from '@/components/layout/page-header'
import { FilterBar } from '@/components/shared/filter-bar'
import { DateRange } from 'react-day-picker'
import { EditPersonaDialog, EditImpressionDialog } from '@/components/graph/persona-dialogs'
import { ReanalyzeMethodDialog, type ReanalyzeMethod } from '@/components/shared/reanalyze-method-dialog'
import { NetworkGraph, GRAPH_VIEWPORT_ID, type NetworkGraphHandle } from '@/components/graph/network-graph'
import { ParamsPanel, type GraphExportFormat } from '@/components/graph/params-panel'
import { NodeDetail } from '@/components/graph/node-detail'
import { EdgeDetail } from '@/components/graph/edge-detail'
import { GroupCardList } from '@/components/graph/group-card-list'
import { PersonaSupernodeGrid } from '@/components/graph/persona-supernode-grid'
import { RefreshButton } from '@/components/shared/refresh-button'
import { PageEmptyOverlay } from '@/components/shared/page-empty-overlay'
import { useApp } from '@/lib/store'
import { getStored, removeStored, setStored } from '@/lib/safe-storage'
import * as api from '@/lib/api'
import {
  DEFAULT_PHYSICS_PARAMS,
  DEFAULT_VISUAL_PARAMS,
  autoPhysicsSettings,
  countAutoChanges,
  type EdgePair,
  type PhysicsParams,
  type VisualParams,
  type ViewMode,
  type GroupCard,
} from '@/lib/graph-types'
import {
  buildGroupCards, computeNodeRadius, degreeMap, mockCluster,
  GROUP_ID_GLOBAL, GROUP_ID_PRIVATE,
} from '@/lib/graph-utils'
import {
  buildExportGraph, downloadText, exportFilename, exportPng, exportSvg,
  toEdgesCsv, toGexf, toNodesCsv,
} from '@/lib/graph-export'
import { getPaletteColor } from '@/lib/colors'
import { useForceSimulation } from '@/hooks/use-force-simulation'
import { useRouter } from 'next/navigation'

export default function GraphPage() {
  const app = useApp()
  const { i18n, currentPersonaName, scopeMode, setRawGraph, toast } = app
  const personaFilter = scopeMode === 'single' ? (currentPersonaName ?? api.LEGACY_PERSONA_TOKEN) : null
  const router = useRouter()

  // ── Tag & Date filter ──────────────────────────────────────────────────────
  const [activeTags, setActiveTags] = useState<Set<string>>(new Set())
  const [dateRange, setDateRange] = useState<DateRange | undefined>()
  const [tagList, setTagList] = useState<{ name: string; count: number }[]>([])

  // ── Feature flag ────────────────────────────────────────────────────────────
  const [relationEnabled, setRelationEnabled] = useState<boolean | null>(null)

  // ── Group / view state ──────────────────────────────────────────────────────
  const [groupCards, setGroupCards] = useState<GroupCard[]>([])
  const [botSupernodes, setBotSupernodes] = useState<api.BotPersonaItem[]>([])
  const [expandedGroupId, setExpandedGroupId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [isReanalyzing, setIsReanalyzing] = useState(false)
  const [reanalyzeDialogOpen, setReanalyzeDialogOpen] = useState(false)
  const [pendingReanalyzeScope, setPendingReanalyzeScope] = useState<string>('global')
  const [search, setSearch] = useState('')

  // ── Graph interaction state ─────────────────────────────────────────────────
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [selectedPairKey, setSelectedPairKey] = useState<string | null>(null)
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null)

  // ── Physics & visual params ─────────────────────────────────────────────────
  const [physics, setPhysics] = useState<PhysicsParams>(DEFAULT_PHYSICS_PARAMS)
  const [visual, setVisual] = useState<VisualParams>(DEFAULT_VISUAL_PARAMS)
  const [viewMode, setViewMode] = useState<ViewMode>('all')
  const [selectedMemberId, setSelectedMemberId] = useState<string | null>(null)
  const [memberSort, setMemberSort] = useState('msgs-desc')

  // ── Container size ──────────────────────────────────────────────────────────
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 })
  const svgRef = useRef<SVGSVGElement | null>(null)
  const graphHandleRef = useRef<NetworkGraphHandle | null>(null)

  // ── Dialogs ─────────────────────────────────────────────────────────────────
  const [editNode, setEditNode] = useState<api.PersonaNode | null>(null)
  const [editEdge, setEditEdge] = useState<api.ImpressionEdge | null>(null)
  const [defaultConfidence, setDefaultConfidence] = useState(0.5)

  // ── Data loading ────────────────────────────────────────────────────────────
  const loadGraph = useCallback(async () => {
    setLoading(true)
    setIsRefreshing(true)
    try {
      const [data, cfg] = await Promise.all([
        api.graph.get(personaFilter),
        api.pluginConfig.get(),
      ])
      const bots = scopeMode === 'all' ? await api.graph.listBots() : { items: [] }
      if (data.enabled === false) {
        setRelationEnabled(false)
        return
      }
      setRelationEnabled(true)
      setBotSupernodes(bots.items)
      setRawGraph(data)
      setDefaultConfidence(cfg.values.persona_default_confidence as number ?? 0.5)
      const cards = buildGroupCards(data.nodes, data.edges, physics.biWeight, data.group_members)
      setGroupCards(cards)
    } catch {
      toast(i18n.graph.loadError, 'destructive')
    } finally {
      setLoading(false)
      setTimeout(() => setIsRefreshing(false), 600)
    }
  }, [setRawGraph, toast, physics.biWeight, i18n.graph.loadError, personaFilter, scopeMode])

  const pendingFocusRef = useRef<string | null>(null)

  useEffect(() => {
    loadGraph().then(() => {
      const focusId = getStored('em_focus_persona', null, 'session')
      if (focusId) {
        removeStored('em_focus_persona', 'session')
        pendingFocusRef.current = focusId
      }
    })
  }, [loadGraph])

  useEffect(() => {
    api.tags.list().then(r => setTagList(r.tags)).catch(() => {})
  }, [])

  // After group cards are available, handle pending sessionStorage focus
  useEffect(() => {
    if (groupCards.length > 0 && pendingFocusRef.current) {
      const focusId = pendingFocusRef.current
      pendingFocusRef.current = null
      const card = groupCards.find(g => g.nodes.some(n => n.data.id === focusId))
      if (card) {
        setExpandedGroupId(card.group_id)
        setFocusNodeId(focusId)
      }
    }
  }, [groupCards])

  // ── Current group data ──────────────────────────────────────────────────────
  const currentGroup = useMemo(
    () => groupCards.find(g => g.group_id === expandedGroupId) ?? null,
    [groupCards, expandedGroupId],
  )

  // ── Active node/edge filtering ──────────────────────────────────────────────
  const visibleNodeIds = useMemo<Set<string> | null>(() => {
    if (viewMode === 'all' || !selectedMemberId) return null
    const connected = new Set([selectedMemberId])
    currentGroup?.edgePairs.forEach(p => {
      if (p.srcId === selectedMemberId) connected.add(p.tgtId)
      if (p.tgtId === selectedMemberId) connected.add(p.srcId)
    })
    return connected
  }, [viewMode, selectedMemberId, currentGroup])

  const activeNodes = useMemo(() =>
    (currentGroup?.nodes ?? []).filter(n =>
      (visual.showBot || !n.data.is_bot) &&
      (visibleNodeIds === null || visibleNodeIds.has(n.data.id))
    ),
    [currentGroup, visual.showBot, visibleNodeIds],
  )

  const activePairs = useMemo(() => {
    const activeIds = new Set(activeNodes.map(n => n.data.id))
    return (currentGroup?.edgePairs ?? []).filter(p =>
      activeIds.has(p.srcId) && activeIds.has(p.tgtId)
    )
  }, [currentGroup, activeNodes])

  // ── Force simulation ────────────────────────────────────────────────────────
  const [exportMode, setExportMode] = useState(false)

  const { positions, refresh: refreshLayout, layoutVersion } = useForceSimulation({
    nodes: activeNodes,
    edgePairs: activePairs,
    params: physics,
    containerSize,
    enabled: !!expandedGroupId,
  })

  // ── Tag & Date-filtered group cards ─────────────────────────────────────────
  const filteredGroups = useMemo(() => {
    let gs = groupCards
    if (search) {
      const q = search.toLowerCase()
      gs = gs.filter(g => (g.name || '').toLowerCase().includes(q) || g.group_id.toLowerCase().includes(q))
    }
    if (activeTags.size > 0) {
      gs = gs.filter(g =>
        g.nodes.some(n =>
          (n.data.attrs?.content_tags ?? []).some(t => activeTags.has(t))
        )
      )
    }
    if (dateRange?.from) {
      const fromTs = dateRange.from.getTime()
      const toTs = dateRange.to ? dateRange.to.getTime() + 86400000 : fromTs + 86400000
      gs = gs.filter(g =>
        g.nodes.some(n => {
          if (!n.data.last_active_at) return false
          const ts = new Date(n.data.last_active_at).getTime()
          return ts >= fromTs && ts <= toTs
        })
      )
    }
    return gs
  }, [groupCards, activeTags, dateRange, search])

  const filteredSupernodes = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return botSupernodes
    return botSupernodes.filter(item =>
      (item.name ?? i18n.personaSelector.defaultPersona).toLowerCase().includes(q)
    )
  }, [botSupernodes, search, i18n.personaSelector.defaultPersona])

  // ── Open group ──────────────────────────────────────────────────────────────
  const handleOpenGroup = (groupId: string) => {
    setExpandedGroupId(groupId)
    setSelectedNodeId(null)
    setSelectedPairKey(null)
    setFocusNodeId(null)
    setViewMode('all')
    setSelectedMemberId(null)
  }

  // ── Back to list ────────────────────────────────────────────────────────────
  const handleBackToList = () => {
    setExpandedGroupId(null)
    setSelectedNodeId(null)
    setSelectedPairKey(null)
    setFocusNodeId(null)
  }

  // ── Node selection ──────────────────────────────────────────────────────────
  const handleSelectNode = useCallback((id: string | null) => {
    setSelectedNodeId(id)
    if (id) setSelectedPairKey(null)
  }, [])

  const handleSelectPair = useCallback((key: string | null) => {
    setSelectedPairKey(key)
    if (key) setSelectedNodeId(null)
  }, [])

  // ── Auto settings ───────────────────────────────────────────────────────────
  // Settings picked for the visible node count. The toast reports the size of
  // the diff rather than just echoing the button's own label: this used to be a
  // no-op on any graph under 100 nodes and said "done" all the same, which is
  // indistinguishable from success and is exactly how the bug stayed hidden.
  const handleAutoSettings = useCallback(() => {
    const next = autoPhysicsSettings(activeNodes.length)
    // Diffed against the live state, not inside the updater: a functional
    // setState runs in the render phase, so its result is not available to the
    // toast on this tick.
    const changed = countAutoChanges(physics, next)
    if (changed > 0) setPhysics(p => ({ ...p, ...next }))
    toast(changed === 0
      ? i18n.graph.params.autoSettingsNoChange
      : i18n.graph.params.autoSettingsApplied.replace('{n}', String(changed)))
  }, [
    activeNodes.length, physics, toast,
    i18n.graph.params.autoSettingsApplied, i18n.graph.params.autoSettingsNoChange,
  ])

  // ── Export ──────────────────────────────────────────────────────────────────
  const clusterMap = useMemo(() => {
    if (!visual.leidenEnabled) return {}
    return mockCluster(activeNodes, activePairs, visual.leidenResolution)
  }, [visual.leidenEnabled, visual.leidenResolution, activeNodes, activePairs])

  const exportRadius = useMemo(() => {
    const degrees = degreeMap(activeNodes, activePairs)
    let minDeg = Infinity
    let maxDeg = 1
    for (const d of degrees.values()) {
      minDeg = Math.min(minDeg, d)
      maxDeg = Math.max(maxDeg, d)
    }
    if (!Number.isFinite(minDeg)) minDeg = 0
    const radii = new Map<string, number>()
    for (const [id, deg] of degrees) radii.set(id, computeNodeRadius(deg, minDeg, maxDeg))
    return radii
  }, [activeNodes, activePairs])

  const handleExport = useCallback(async (
    format: GraphExportFormat,
    options: { scale: number; transparent: boolean },
  ) => {
    const name = currentGroup?.name ?? 'graph'

    if (format === 'gexf' || format === 'csv') {
      const graph = buildExportGraph({
        name,
        nodes: activeNodes,
        edgePairs: activePairs,
        positions,
        edgeWeightSource: physics.edgeWeightSource,
        nodeRadius: id => exportRadius.get(id) ?? 12,
        nodeColor: n => {
          if (n.data.is_bot) return 'var(--primary)'
          if (visual.leidenEnabled) return getPaletteColor(clusterMap[n.data.id] ?? 0)
          return 'var(--muted)'
        },
        edgeColor: (pair: EdgePair) => {
          if (!visual.sentimentEnabled) return '#aaaaaa'
          const pick = (e: api.ImpressionEdge) =>
            visual.sentimentAxis === 'power' ? e.data.power : e.data.affect
          const avg = pair.isBidirectional && pair.bwd
            ? (pick(pair.fwd) + pick(pair.bwd)) / 2
            : pick(pair.fwd)
          if (avg > 0.3) return '#2d7d46'
          if (avg < -0.1) return '#c0392b'
          return '#aaaaaa'
        },
        clusterOf: id => (visual.leidenEnabled ? clusterMap[id] : undefined),
      })

      if (graph.nodes.length === 0) {
        toast(i18n.graph.params.exportFailed, 'destructive')
        return
      }
      if (format === 'gexf') {
        downloadText(toGexf(graph), exportFilename(name, 'gexf'), 'application/xml')
      } else {
        downloadText(toNodesCsv(graph), exportFilename(`${name}_nodes`, 'csv'), 'text/csv')
        downloadText(toEdgesCsv(graph), exportFilename(`${name}_edges`, 'csv'), 'text/csv')
      }
      return
    }

    // Image formats need a repaint with every label shown and no hover dimming.
    const svg = svgRef.current
    if (!svg) return
    setExportMode(true)
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
    try {
      const imageOpts = {
        viewportGroupId: GRAPH_VIEWPORT_ID,
        background: options.transparent ? null : 'var(--background)',
        scale: options.scale,
      }
      const ok = format === 'png'
        ? await exportPng(svg, exportFilename(name, 'png'), imageOpts)
        : exportSvg(svg, exportFilename(name, 'svg'), imageOpts)
      if (!ok) toast(i18n.graph.params.exportFailed, 'destructive')
    } finally {
      setExportMode(false)
    }
  }, [
    currentGroup, activeNodes, activePairs, positions, physics.edgeWeightSource,
    exportRadius, clusterMap, visual.leidenEnabled, visual.sentimentEnabled,
    visual.sentimentAxis, toast, i18n.graph.params.exportFailed,
  ])

  // ── Fit view ────────────────────────────────────────────────────────────────
  const graphContainerRef = useRef<HTMLDivElement>(null)
  const handleFit = () => graphHandleRef.current?.fitView()

  // ── CRUD handlers ───────────────────────────────────────────────────────────
  const handleUpdatePersona = async (uid: string, data: Record<string, unknown>) => {
    await api.graph.updatePersona(uid, data)
    app.toast(i18n.graph.updateSuccess)
    setSelectedNodeId(null)
    await loadGraph()
  }

  const handleDeletePersona = async (uid: string, name: string) => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    if (!confirm(i18n.graph.deleteConfirm.replace('{name}', name))) return
    try {
      await api.graph.deletePersona(uid)
      setSelectedNodeId(null)
      app.toast(i18n.graph.deleteSuccess)
      await loadGraph()
      await app.refreshStats()
    } catch (e: unknown) {
      app.toast(i18n.common.deleteFailed + '：' + (e as api.ApiError).body, 'destructive')
    }
  }

  const handleUpdateImpression = async (
    observer: string, subject: string, scope: string, data: Record<string, unknown>,
  ) => {
    await api.graph.updateImpression(observer, subject, scope, data, personaFilter)
    app.toast(i18n.graph.impressionUpdateSuccess)
    setEditEdge(null)
    await loadGraph()
  }

  const handleOpenSupernode = (name: string | null) => {
    app.setCurrentPersona(name, 'single')
    setExpandedGroupId(null)
    setSelectedNodeId(null)
    setSelectedPairKey(null)
    setFocusNodeId(null)
  }

  const handleDeleteImpression = async (edge: api.ImpressionEdge) => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    if (!confirm(i18n.graph.deleteImpressionConfirm)) return
    try {
      await api.graph.deleteImpression(
        edge.data.source, edge.data.target, edge.data.scope, personaFilter,
      )
      setSelectedPairKey(null)
      app.toast(i18n.graph.impressionDeleteSuccess)
      await loadGraph()
      await app.refreshStats()
    } catch (e: unknown) {
      app.toast(i18n.common.deleteFailed + '：' + (e as api.ApiError).body, 'destructive')
    }
  }

  const handleClearCurrentScopeImpressions = async () => {
    if (!currentGroup) return
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    const scope = currentGroup.group_id === GROUP_ID_PRIVATE ? 'global' : currentGroup.group_id
    if (!confirm(i18n.graph.clearScopeImpressionsConfirm.replace('{name}', currentGroup.name))) return
    try {
      const result = await api.graph.deleteImpressionsByScope(scope, personaFilter)
      setSelectedPairKey(null)
      setSelectedNodeId(null)
      app.toast(i18n.graph.clearScopeImpressionsSuccess.replace('{count}', String(result.deleted)))
      await loadGraph()
      await app.refreshStats()
    } catch (e: unknown) {
      app.toast(i18n.common.deleteFailed + '：' + (e as api.ApiError).body, 'destructive')
    }
  }

  const handleReanalyzeImpressions = (scopeOverride?: string) => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    const scope = scopeOverride ?? (currentGroup
      ? (currentGroup.group_id === GROUP_ID_PRIVATE ? 'global' : currentGroup.group_id)
      : 'global')
    setPendingReanalyzeScope(scope)
    setReanalyzeDialogOpen(true)
  }

  const handleReanalyzeConfirm = async (method: ReanalyzeMethod) => {
    setIsReanalyzing(true)
    try {
      await app.runTask(
        i18n.tasks.reanalyzeImpressions,
        () => api.graph.reanalyzeImpressions(pendingReanalyzeScope, personaFilter, method),
      )
      await loadGraph()
      await app.refreshStats()
    } catch {
      /* running / failure state surfaced by the TaskDock */
    } finally {
      setIsReanalyzing(false)
    }
  }

  const handleJumpToEvent = (eventId: string) => {
    setStored('em_highlight_events', JSON.stringify([eventId]), 'session')
    router.push('/events')
  }

  // ── Standard Utilities ──────────────────────────────────────────────────────
  const globalActions = (
    <RefreshButton 
      onClick={loadGraph} 
      loading={isRefreshing} 
    />
  )


  // ── Group list view ─────────────────────────────────────────────────────────
  if (!expandedGroupId) {
    const listActions = (
      <div className="flex items-center gap-2">
        <div className="relative hidden md:block">
          <Search className="text-muted-foreground pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2" />
          <Input
            className="h-8 w-48 pl-8 text-xs lg:w-64"
            placeholder={i18n.common.searchPlaceholder}
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <Button size="sm" variant="outline" onClick={() => handleReanalyzeImpressions('global')} disabled={!app.sudo || isReanalyzing} className="h-8 gap-1.5">
          <RefreshCcw className={`size-3.5 ${isReanalyzing ? 'animate-spin' : ''}`} />
          <span className="hidden sm:inline">{i18n.graph.reanalyzeImpressions}</span>
        </Button>
      </div>
    )

    return (
      <div className="flex h-screen flex-col overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-500 ease-out fill-mode-both">
        <PageHeader
          variant="loom"
          loomIssue="ΓΡΑΦΟΣ"
          loomWindow={i18n.page.graph.loomWindow}
          title={i18n.page.graph.title}
          actions={listActions}
          globalActions={globalActions}
          noToolbarBorder={true}
        />
        <FilterBar 
          tags={tagList} 
          activeTags={activeTags} 
          onTagsChange={setActiveTags} 
          dateRange={dateRange}
          onDateRangeChange={setDateRange}
        />
        <div className="flex-1 overflow-y-auto animate-in fade-in duration-700 delay-150 fill-mode-both">
          {scopeMode === 'all' ? (
            <PersonaSupernodeGrid
              items={filteredSupernodes}
              onOpen={handleOpenSupernode}
              loading={loading}
              isFiltered={botSupernodes.length > 0 && search !== ''}
            />
          ) : (
            <GroupCardList 
              groups={filteredGroups} 
              onOpen={handleOpenGroup} 
              loading={loading} 
              isFiltered={groupCards.length > 0 && (search !== '' || activeTags.size > 0 || !!dateRange?.from)}
            />
          )}
        </div>

      </div>
    )
  }

  // ── Expanded graph view ─────────────────────────────────────────────────────
  const rightPanelContent = (() => {
    if (selectedNodeId) {
      const node = activeNodes.find(n => n.data.id === selectedNodeId)
      if (node) return (
        <NodeDetail
          node={node}
          allNodes={activeNodes}
          edgePairs={activePairs}
          onBack={() => setSelectedNodeId(null)}
          onEdit={n => { if (app.sudo) setEditNode(n); else app.toast(i18n.common.needSudo, 'destructive') }}
          onDelete={handleDeletePersona}
          sudoMode={app.sudo}
        />
      )
    }
    if (selectedPairKey) {
      return (
        <EdgeDetail
          pairKey={selectedPairKey}
          edgePairs={activePairs}
          allNodes={activeNodes}
          onBack={() => setSelectedPairKey(null)}
          onEditForward={edge => { if (app.sudo) setEditEdge(edge); else app.toast(i18n.common.needSudo, 'destructive') }}
          onEditBackward={edge => { if (app.sudo) setEditEdge(edge); else app.toast(i18n.common.needSudo, 'destructive') }}
          onDelete={handleDeleteImpression}
          onJumpToEvent={handleJumpToEvent}
          sudoMode={app.sudo}
        />
      )
    }
    return (
      <ParamsPanel
        physics={physics}
        visual={visual}
        onPhysics={(k, v) => setPhysics(p => ({ ...p, [k]: v }))}
        onVisual={(k, v) => setVisual(p => ({ ...p, [k]: v }))}
        viewMode={viewMode}
        onViewMode={setViewMode}
        selectedMemberId={selectedMemberId}
        onSelectedMemberId={setSelectedMemberId}
        memberSort={memberSort}
        onMemberSort={setMemberSort}
        groupNodes={currentGroup?.nodes ?? []}
        onFocusNode={setFocusNodeId}
        onRefreshLayout={refreshLayout}
        onAutoSettings={handleAutoSettings}
        onExport={handleExport}
        svgEl={svgRef.current}
        groupName={currentGroup?.name}
        onClearScope={handleClearCurrentScopeImpressions}
        canClearScope={!!currentGroup && currentGroup.group_id !== GROUP_ID_GLOBAL}
        sudoMode={app.sudo}
      />
    )
  })()

  if (relationEnabled === false) {
    return (
      <div className="flex h-screen flex-col overflow-hidden animate-in fade-in duration-500">
        <PageHeader variant="loom" loomIssue="ΓΡΑΦΟΣ"
          loomWindow={i18n.page.graph.loomWindow} title={i18n.page.graph.title} />
        <PageEmptyOverlay
          icon={Share2}
          title={i18n.page.graph.disabledTitle}
          description={i18n.page.graph.disabledDescription}
        />
      </div>
    )
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-400 ease-out fill-mode-both">
      <PageHeader
        variant="loom"
        loomIssue="ΓΡΑΦΟΣ"
          loomWindow={i18n.page.graph.loomWindow}
        title={currentGroup?.name ?? i18n.page.graph.title}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" className="h-8 gap-1.5 px-2" onClick={handleBackToList}>
              <ChevronLeft className="size-3.5" />
              <span className="hidden sm:inline">{i18n.graph.backToList}</span>
            </Button>
            <Button size="sm" variant="outline" onClick={() => handleReanalyzeImpressions()} disabled={!app.sudo || isReanalyzing} className="h-8 gap-1.5">
              <RefreshCcw className={`size-3.5 ${isReanalyzing ? 'animate-spin' : ''}`} />
              <span className="hidden sm:inline">{i18n.graph.reanalyzeImpressions}</span>
            </Button>
          </div>
        }
        globalActions={globalActions}
      />

      <div className="flex flex-1 overflow-hidden">
        {/* SVG graph area */}
        <div className="relative flex-1 overflow-hidden" ref={graphContainerRef}>
          <NetworkGraph
            nodes={activeNodes}
            edgePairs={activePairs}
            positions={positions}
            params={{ ...physics, ...visual }}
            selectedNodeId={selectedNodeId}
            selectedPairKey={selectedPairKey}
            focusNodeId={focusNodeId}
            exportMode={exportMode}
            onSelectNode={handleSelectNode}
            onSelectPair={handleSelectPair}
            onSizeChange={setContainerSize}
            svgRef={svgRef}
            handleRef={graphHandleRef}
            layoutVersion={layoutVersion}
          />

          {/* Bottom toolbar overlay */}
          <div className="absolute bottom-3 left-1/2 -translate-x-1/2 flex gap-1.5 animate-in slide-in-from-bottom-2 duration-500 delay-300 fill-mode-both">
            <Button size="sm" variant="secondary" className="text-xs h-7 shadow-sm" onClick={handleFit}>
              <Maximize2 className="mr-1 h-3 w-3" />{i18n.graph.fit}
            </Button>
            <Button size="sm" variant="secondary" className="text-xs h-7 shadow-sm"
              onClick={() => { setSelectedNodeId(null); setSelectedPairKey(null) }}>
              <XCircle className="mr-1 h-3 w-3" />{i18n.graph.clearHighlight}
            </Button>
            <Button size="sm" variant="secondary" className="text-xs h-7 shadow-sm"
              disabled={physics.locked || physics.layoutMode === 'circular'}
              onClick={refreshLayout}>
              {i18n.graph.recalcLayout}
            </Button>
          </div>
        </div>

        {/* Right panel (fixed 340px) */}
        <div className="w-[340px] shrink-0 border-l overflow-hidden animate-in slide-in-from-right-4 duration-400 ease-out fill-mode-both">
          {rightPanelContent}
        </div>
      </div>

      {/* Dialogs */}
      <ReanalyzeMethodDialog
        open={reanalyzeDialogOpen}
        onClose={() => setReanalyzeDialogOpen(false)}
        onConfirm={handleReanalyzeConfirm}
      />
      <EditPersonaDialog
        open={!!editNode}
        node={editNode}
        onClose={() => setEditNode(null)}
        onSubmit={handleUpdatePersona}
      />
      <EditImpressionDialog
        open={!!editEdge}
        edge={editEdge}
        onClose={() => setEditEdge(null)}
        onSubmit={handleUpdateImpression}
      />

      {/* Keep onJumpToEvent accessible from impressionDetail if needed */}
      <span className="hidden" data-jump-handler={String(!!handleJumpToEvent)} />
    </div>
  )
}
