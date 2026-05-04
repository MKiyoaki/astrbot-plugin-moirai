'use client'

import { useEffect, useState, useRef, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { UserPlus, RefreshCw, Maximize2, XCircle } from 'lucide-react'
import dynamic from 'next/dynamic'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PageHeader } from '@/components/layout/page-header'
import { TagFilter } from '@/components/shared/tag-filter'
import {
  CreatePersonaDialog, EditPersonaDialog, EditImpressionDialog,
  PersonaDetailCard, ImpressionDetailCard,
} from '@/components/graph/persona-dialogs'
import { useApp } from '@/lib/store'
import * as api from '@/lib/api'
import { i18n } from '@/lib/i18n'

const CytoscapeGraph = dynamic(
  () => import('@/components/graph/cytoscape-graph').then(m => m.CytoscapeGraph),
  { ssr: false, loading: () => <div className="text-muted-foreground flex h-full items-center justify-center text-sm">{i18n.common.loading}</div> },
)

export default function GraphPage() {
  const router = useRouter()
  const app = useApp()
  const cyRef = useRef<unknown>(null)
  const [search, setSearch] = useState('')
  const [activeTags, setActiveTags] = useState<Set<string>>(new Set())
  const [tagList, setTagList] = useState<{ name: string; count: number }[]>([])
  const [detailNode, setDetailNode] = useState<api.PersonaNode | null>(null)
  const [detailEdge, setDetailEdge] = useState<api.ImpressionEdge | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [editNode, setEditNode] = useState<api.PersonaNode | null>(null)
  const [editEdge, setEditEdge] = useState<api.ImpressionEdge | null>(null)

  const loadGraph = useCallback(async () => {
    try {
      const data = await api.graph.get()
      app.setRawGraph(data)
    } catch {
      app.toast('关系图加载失败', 'destructive')
    }
  }, [app])

  useEffect(() => {
    loadGraph()
    api.tags.list().then(r => setTagList(r.tags))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleNodeClick = (data: api.PersonaNode['data']) => {
    setDetailEdge(null)
    const node = app.rawGraph.nodes.find(n => n.data.id === data.id) ?? null
    setDetailNode(node)
  }

  const handleEdgeClick = (data: api.ImpressionEdge['data']) => {
    setDetailNode(null)
    const edge = app.rawGraph.edges.find(e => e.data.id === data.id) ?? null
    setDetailEdge(edge)
  }

  const handleClear = () => {
    setDetailNode(null)
    setDetailEdge(null)
    if (cyRef.current) {
      (cyRef.current as { elements: () => { removeClass: (c: string) => void } })
        .elements().removeClass('dim focused')
    }
  }

  const handleFit = () => {
    if (cyRef.current) {
      (cyRef.current as { fit: () => void }).fit()
    }
  }

  const handleCreatePersona = async (data: Record<string, unknown>) => {
    await api.graph.createPersona(data)
    app.toast('人格已创建')
    await loadGraph()
    await app.refreshStats()
  }

  const handleUpdatePersona = async (uid: string, data: Record<string, unknown>) => {
    await api.graph.updatePersona(uid, data)
    app.toast('人格已更新')
    setDetailNode(null)
    await loadGraph()
  }

  const handleDeletePersona = async (uid: string, name: string) => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    if (!confirm(`确认删除人格「${name}」？`)) return
    try {
      await api.graph.deletePersona(uid)
      setDetailNode(null)
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
    setDetailEdge(null)
    await loadGraph()
  }

  const handleJumpToEvent = (eventId: string) => {
    router.push('/events')
    // store in sessionStorage to highlight after navigation
    sessionStorage.setItem('em_highlight_events', JSON.stringify([eventId]))
  }

  const filteredNodes = app.rawGraph.nodes.filter(n => {
    if (search && !n.data.label?.toLowerCase().includes(search.toLowerCase())) return false
    if (activeTags.size > 0) {
      const tags: string[] = n.data.attrs?.content_tags ?? []
      if (!tags.some(t => activeTags.has(t))) return false
    }
    return true
  })
  const filteredNodeIds = new Set(filteredNodes.map(n => n.data.id))
  const filteredEdges = app.rawGraph.edges.filter(e =>
    filteredNodeIds.has(e.data.source) && filteredNodeIds.has(e.data.target),
  )

  const actions = (
    <div className="flex flex-wrap items-center gap-2">
      <div className="relative">
        <Input
          className="h-7 w-44 pl-7 text-xs"
          placeholder={i18n.graph.search}
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <span className="text-muted-foreground pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-xs">🔍</span>
      </div>

      <Button variant="ghost" size="icon-sm" onClick={handleFit} title={i18n.graph.fit}>
        <Maximize2 />
      </Button>
      <Button variant="ghost" size="icon-sm" onClick={handleClear} title={i18n.graph.clearHighlight}>
        <XCircle />
      </Button>
      <Button size="sm" onClick={() => setCreateOpen(true)} disabled={!app.sudo}>
        <UserPlus className="mr-1 size-3.5" />{i18n.graph.createPersona}
      </Button>
      <Button variant="ghost" size="icon-sm" onClick={loadGraph} title={i18n.common.refresh}>
        <RefreshCw />
      </Button>
    </div>
  )

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <PageHeader
        title={i18n.page.graph.title}
        description={i18n.page.graph.description}
        actions={actions}
      />

      <div className="flex flex-1 overflow-hidden">
        {/* Graph canvas + tag filter */}
        <div className="flex flex-1 flex-col overflow-hidden">
          <TagFilter tags={tagList} value={activeTags} onChange={setActiveTags} />
          <div className="flex-1 overflow-hidden">
          <CytoscapeGraph
            nodes={filteredNodes}
            edges={filteredEdges}
            onNodeClick={handleNodeClick}
            onEdgeClick={handleEdgeClick}
            onBackgroundClick={handleClear}
            instanceRef={cyRef}
          />
          </div>
        </div>

        {/* Detail side panel */}
        {(detailNode || detailEdge) && (
          <div className="bg-card ring-foreground/10 flex h-full w-72 shrink-0 flex-col gap-3 overflow-y-auto border-l p-4 ring-1">
            <div className="flex items-center justify-between">
              <h3 className="font-medium">
                {detailNode ? i18n.graph.detailTitle : i18n.graph.impressionDetail}
              </h3>
              <Button variant="ghost" size="icon-xs" onClick={handleClear}>✕</Button>
            </div>
            {detailNode && (
              <PersonaDetailCard
                node={detailNode}
                onEdit={node => { if (app.sudo) setEditNode(node); else app.toast(i18n.common.needSudo, 'destructive') }}
                onDelete={handleDeletePersona}
                sudoMode={app.sudo}
              />
            )}
            {detailEdge && (
              <ImpressionDetailCard
                edge={detailEdge}
                onEdit={edge => { if (app.sudo) setEditEdge(edge); else app.toast(i18n.common.needSudo, 'destructive') }}
                onJumpToEvent={handleJumpToEvent}
                sudoMode={app.sudo}
              />
            )}
          </div>
        )}
      </div>

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
    </div>
  )
}
