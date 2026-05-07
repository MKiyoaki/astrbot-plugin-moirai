'use client'

import { useEffect, useState, useRef, useCallback, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { UserPlus, RefreshCw, ChevronLeft, Maximize2, XCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageHeader } from '@/components/layout/page-header'
import { FilterBar } from '@/components/shared/filter-bar'
import { DateRange } from 'react-day-picker'
import { CreatePersonaDialog, EditPersonaDialog, EditImpressionDialog } from '@/components/graph/persona-dialogs'
import { NetworkGraph } from '@/components/graph/network-graph'
import { ParamsPanel } from '@/components/graph/params-panel'
import { NodeDetail } from '@/components/graph/node-detail'
import { EdgeDetail } from '@/components/graph/edge-detail'
import { GroupCardList } from '@/components/graph/group-card-list'
import { useApp } from '@/lib/store'
import * as api from '@/lib/api'
import { i18n } from '@/lib/i18n'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
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

export default function GraphPage() {
  const router = useRouter()
  const app = useApp()

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

  // ── Data loading ────────────────────────────────────────────────────────────
  const loadGraph = useCallback(async () => {
    setLoading(true)
    setIsRefreshing(true)
    try {
      const data = await api.graph.get()
      if (data.enabled === false) {
        setRelationEnabled(false)
        return
      }
      setRelationEnabled(true)
      app.setRawGraph(data)
      const cards = buildGroupCards(data.nodes, data.edges, physics.biWeight)
      setGroupCards(cards)
    } catch {
      app.toast('关系图加载失败', 'destructive')
    } finally {
      setLoading(false)
      setTimeout(() => setIsRefreshing(false), 600)
    }
  }, [app.setRawGraph, app.toast, physics.biWeight])

  useEffect(() => {
    loadGraph().then(() => {
      const focusId = sessionStorage.getItem('em_focus_persona')
      if (focusId) {
        sessionStorage.removeItem('em_focus_persona')
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
  }, [groupCards, activeTags, dateRange])

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
    app.toast('人格已创建')
    await loadGraph()
    await app.refreshStats()
  }

  const handleUpdatePersona = async (uid: string, data: Record<string, unknown>) => {
    await api.graph.updatePersona(uid, data)
    app.toast('人格已更新')
    setSelectedNodeId(null)
    await loadGraph()
  }

  const handleDeletePersona = async (uid: string, name: string) => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    if (!confirm(`确认删除人格「${name}」？`)) return
    try {
      await api.graph.deletePersona(uid)
      setSelectedNodeId(null)
      app.toast('人格已删除')
      await loadGraph()
      await app.refreshStats()
    } catch (e: unknown) {
      app.toast('删除失败：' + (e as api.ApiError).body, 'destructive')
    }
  }

  const handleUpdateImpression = async (
    observer: string, subject: string, scope: string, data: Record<string, unknown>,
  ) => {
    await api.graph.updateImpression(observer, subject, scope, data)
    app.toast('印象已更新')
    setEditEdge(null)
    await loadGraph()
  }

  const handleJumpToEvent = (eventId: string) => {
    router.push('/events')
    sessionStorage.setItem('em_highlight_events', JSON.stringify([eventId]))
  }

  // ── Group list view ─────────────────────────────────────────────────────────
  if (!expandedGroupId) {
    return (
      <div className="flex h-screen flex-col overflow-hidden">
        <PageHeader
          title={i18n.page.graph.title}
          description={`${groupCards.length} 个群组`}
          actions={
            <div className="flex items-center gap-2">
              <Button size="sm" onClick={() => setCreateOpen(true)} disabled={!app.sudo}>
                <UserPlus className="mr-1 size-3.5" />{i18n.graph.createPersona}
              </Button>
              <Button variant="ghost" size="icon" onClick={loadGraph} title={i18n.common.refresh}>
                <RefreshCw className={cn("size-4 transition-transform duration-500", isRefreshing && "animate-spin")} />
              </Button>
            </div>
          }
        />
        <FilterBar 
          tags={tagList} 
          activeTags={activeTags} 
          onTagsChange={setActiveTags} 
          dateRange={dateRange}
          onDateRangeChange={setDateRange}
        />
        <div className="flex-1 overflow-y-auto">
          <GroupCardList groups={filteredGroups} onOpen={handleOpenGroup} loading={loading} />
        </div>

        <CreatePersonaDialog
          open={createOpen}
          onClose={() => setCreateOpen(false)}
          onSubmit={handleCreatePersona}
          defaultConfidence={app.defaultPersonaConfidence}
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
      />
    )
  })()

  if (relationEnabled === false) {
    return (
      <div className="flex h-screen flex-col overflow-hidden">
        <PageHeader title={i18n.page.graph.title} description={i18n.page.graph.description} />
        <div className="flex flex-1 items-center justify-center p-8">
          <Card className="max-w-md w-full">
            <CardHeader>
              <CardTitle>{i18n.page.graph.disabledTitle}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">{i18n.page.graph.disabledDescription}</p>
            </CardContent>
          </Card>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <PageHeader
        title={currentGroup?.name ?? i18n.page.graph.title}
        description={`${i18n.graph.nodeCount} ${activeNodes.length} · ${i18n.graph.edgePairCount} ${activePairs.length}`}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={handleBackToList}>
              <ChevronLeft className="mr-1 size-3.5" />{i18n.graph.backToList}
            </Button>
            <Button size="sm" onClick={() => setCreateOpen(true)} disabled={!app.sudo}>
              <UserPlus className="mr-1 size-3.5" />{i18n.graph.createPersona}
            </Button>
            <Button variant="ghost" size="icon" onClick={loadGraph} title={i18n.common.refresh}>
              <RefreshCw className={cn("size-4 transition-transform duration-500", isRefreshing && "animate-spin")} />
            </Button>
          </div>
        }
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
          <div className="absolute bottom-3 left-1/2 -translate-x-1/2 flex gap-1.5">
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

        {/* Right panel (fixed 272px) */}
        <div className="w-[272px] shrink-0 border-l overflow-hidden">
          {rightPanelContent}
        </div>
      </div>

      {/* Dialogs */}
      <CreatePersonaDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSubmit={handleCreatePersona}
        defaultConfidence={app.defaultPersonaConfidence}
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
