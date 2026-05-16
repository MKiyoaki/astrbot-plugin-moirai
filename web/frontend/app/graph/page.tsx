'use client'

import { useEffect, useState, useRef, useCallback, useMemo } from 'react'
import { UserPlus, ChevronLeft, Maximize2, XCircle, Search, Share2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PageHeader } from '@/components/layout/page-header'
import { FilterBar } from '@/components/shared/filter-bar'
import { DateRange } from 'react-day-picker'
import { CreatePersonaDialog, EditPersonaDialog, EditImpressionDialog } from '@/components/graph/persona-dialogs'
import { NetworkGraph } from '@/components/graph/network-graph'
import { ParamsPanel } from '@/components/graph/params-panel'
import { NodeDetail } from '@/components/graph/node-detail'
import { EdgeDetail } from '@/components/graph/edge-detail'
import { GroupCardList } from '@/components/graph/group-card-list'
import { RefreshButton } from '@/components/shared/refresh-button'
import { EmptyState } from '@/components/shared/empty-state'
import { useApp } from '@/lib/store'
import { getStored, removeStored, setStored } from '@/lib/safe-storage'
import * as api from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  DEFAULT_PHYSICS_PARAMS,
  DEFAULT_VISUAL_PARAMS,
  type PhysicsParams,
  type VisualParams,
  type ViewMode,
  type GroupCard,
} from '@/lib/graph-types'
import { buildGroupCards } from '@/lib/graph-utils'
import { useForceSimulation } from '@/hooks/use-force-simulation'
import { useRouter } from 'next/navigation'

export default function GraphPage() {
  const app = useApp()
  const { i18n } = app
  const router = useRouter()

  // ── Tag & Date filter ──────────────────────────────────────────────────────
  const [activeTags, setActiveTags] = useState<Set<string>>(new Set())
  const [dateRange, setDateRange] = useState<DateRange | undefined>()
  const [tagList, setTagList] = useState<{ name: string; count: number }[]>([])

  // ── Feature flag ────────────────────────────────────────────────────────────
  const [relationEnabled, setRelationEnabled] = useState<boolean | null>(null)

  // ── Group / view state ──────────────────────────────────────────────────────
  const [groupCards, setGroupCards] = useState<GroupCard[]>([])
  const [expandedGroupId, setExpandedGroupId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)
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

  // ── Dialogs ─────────────────────────────────────────────────────────────────
  const [createOpen, setCreateOpen] = useState(false)
  const [editNode, setEditNode] = useState<api.PersonaNode | null>(null)
  const [editEdge, setEditEdge] = useState<api.ImpressionEdge | null>(null)
  const [defaultConfidence, setDefaultConfidence] = useState(0.5)

  // ── Data loading ────────────────────────────────────────────────────────────
  const loadGraph = useCallback(async () => {
    setLoading(true)
    setIsRefreshing(true)
    try {
      const [data, cfg] = await Promise.all([
        api.graph.get(),
        api.pluginConfig.get()
      ])
      if (data.enabled === false) {
        setRelationEnabled(false)
        return
      }
      setRelationEnabled(true)
      app.setRawGraph(data)
      setDefaultConfidence(cfg.values.persona_default_confidence as number ?? 0.5)
      const cards = buildGroupCards(data.nodes, data.edges, physics.biWeight, data.group_members)
      setGroupCards(cards)
    } catch {
      app.toast(i18n.graph.loadError, 'destructive')
    } finally {
      setLoading(false)
      setTimeout(() => setIsRefreshing(false), 600)
    }
  }, [app.setRawGraph, app.toast, physics.biWeight, i18n.graph.loadError])

  useEffect(() => {
    loadGraph().then(() => {
      const focusId = getStored('em_focus_persona', null, 'session')
      if (focusId) {
        removeStored('em_focus_persona', 'session')
        // Open the first group that contains the node
        const card = groupCards.find(g => g.nodes.some(n => n.data.id === focusId))
        if (card) {
          setExpandedGroupId(card.group_id)
          setFocusNodeId(focusId)
        }
      }
    })
    api.tags.list().then(r => setTagList(r.tags)).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // After group cards are available, handle pending sessionStorage focus
  const pendingFocusRef = useRef<string | null>(null)
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
  const { positions, refresh: refreshLayout } = useForceSimulation({
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

  // ── Fit view ────────────────────────────────────────────────────────────────
  const graphContainerRef = useRef<HTMLDivElement>(null)
  const handleFit = () => {
    // @ts-expect-error custom method
    if (svgRef.current?.__fitView) (svgRef.current as SVGSVGElement & { __fitView: () => void }).__fitView()
  }

  // ── CRUD handlers ───────────────────────────────────────────────────────────
  const handleCreatePersona = async (data: Record<string, unknown>) => {
    await api.graph.createPersona(data)
    app.toast(i18n.graph.createSuccess)
    await loadGraph()
    await app.refreshStats()
  }

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
    await api.graph.updateImpression(observer, subject, scope, data)
    app.toast(i18n.graph.impressionUpdateSuccess)
    setEditEdge(null)
    await loadGraph()
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
        <Button size="sm" onClick={() => setCreateOpen(true)} disabled={!app.sudo} className="h-8 gap-1.5">
          <UserPlus className="size-3.5" />
          <span className="hidden sm:inline">{i18n.graph.createPersona}</span>
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
          <GroupCardList 
            groups={filteredGroups} 
            onOpen={handleOpenGroup} 
            loading={loading} 
            isFiltered={groupCards.length > 0 && (search !== '' || activeTags.size > 0 || !!dateRange?.from)}
          />
        </div>

        <CreatePersonaDialog
          open={createOpen}
          onClose={() => setCreateOpen(false)}
          onSubmit={handleCreatePersona}
          defaultConfidence={defaultConfidence}
        />
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
        svgEl={svgRef.current}
        groupName={currentGroup?.name}
      />
    )
  })()

  if (relationEnabled === false) {
    return (
      <div className="flex h-screen flex-col overflow-hidden animate-in fade-in duration-500">
        <PageHeader variant="loom" loomIssue="ΓΡΑΦΟΣ"
          loomWindow={i18n.page.graph.loomWindow} title={i18n.page.graph.title} />
        <EmptyState
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
            <Button size="sm" onClick={() => setCreateOpen(true)} disabled={!app.sudo} className="h-8 gap-1.5">
              <UserPlus className="size-3.5" />
              <span className="hidden sm:inline">{i18n.graph.createPersona}</span>
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
            onSelectNode={handleSelectNode}
            onSelectPair={handleSelectPair}
            onSizeChange={setContainerSize}
            svgRef={svgRef}
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
      <CreatePersonaDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSubmit={handleCreatePersona}
        defaultConfidence={defaultConfidence}
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
