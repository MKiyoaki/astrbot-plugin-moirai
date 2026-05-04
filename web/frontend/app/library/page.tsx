'use client'

import { useEffect, useState, useCallback, Suspense, Fragment, SetStateAction } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import {
  Users, Building2, Activity, Clock, Search,
  ChevronDown, ChevronRight, Pencil, Trash2,
  Network, GitBranch
} from 'lucide-react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select'
import {
  Pagination, PaginationContent, PaginationItem,
  PaginationNext, PaginationPrevious
} from '@/components/ui/pagination'
import { PageHeader } from '@/components/layout/page-header'
import { TagFilter } from '@/components/shared/tag-filter'
import { useApp } from '@/lib/store'
import * as api from '@/lib/api'
import { i18n } from '@/lib/i18n'

// Local UI strings not yet in i18n.ts
const L = {
  editMode:       '编辑模式',
  exitEditMode:   '退出编辑',
  deleteSelected: '删除所选',
  viewInGraph:    '关系图',
  viewInEvents:   '事件流',
  noSelected:     '未选择任何项目',
  confirmDelete:  (n: number) => `确认删除选中的 ${n} 项？`,
  deletedOk:      (n: number) => `已删除 ${n} 项`,
}

function LibraryContent() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const app = useApp()
  const defaultTab = searchParams.get('tab') || 'personas'
  const [tab, setTab] = useState(defaultTab)
  const [search, setSearch] = useState('')
  const [activeTags, setActiveTags] = useState<Set<string>>(new Set())

  const [tagList, setTagList] = useState<{ name: string; count: number }[]>([])
  const [personaList, setPersonaList] = useState<api.PersonaNode[]>([])
  const [groupList, setGroupList] = useState<{ id: string; event_count: number; last_active?: string }[]>([])
  const [eventList, setEventList] = useState<api.ApiEvent[]>([])

  // Expandable row detail state
  const [expandedId, setExpandedId] = useState<string | null>(null)

  // Edit mode & Pagination state
  const [editMode, setEditMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [pageSize, setPageSize] = useState<number>(25)
  const [currentPage, setCurrentPage] = useState<number>(1)

  const loadData = useCallback(async () => {
    const [tagsData, graphData, eventsData] = await Promise.allSettled([
      api.tags.list(),
      api.graph.get(),
      api.events.list(500),
    ])
    if (tagsData.status === 'fulfilled') setTagList(tagsData.value.tags)
    if (graphData.status === 'fulfilled') {
      setPersonaList(graphData.value.nodes)
      app.setRawGraph(graphData.value)
    }
    if (eventsData.status === 'fulfilled') {
      setEventList(eventsData.value.items)
      const groups = new Map<string, { id: string; event_count: number; last_active?: string }>()
      eventsData.value.items.forEach(ev => {
        if (!ev.group) return
        const existing = groups.get(ev.group)
        if (!existing) {
          groups.set(ev.group, { id: ev.group, event_count: 1, last_active: ev.start })
        } else {
          existing.event_count++
          if (!existing.last_active || ev.start > existing.last_active) {
            existing.last_active = ev.start
          }
        }
      })
      setGroupList(Array.from(groups.values()).sort((a, b) => (b.last_active || '') > (a.last_active || '') ? 1 : -1))
    }
  }, [app])

  useEffect(() => {
    loadData()
  }, [loadData])

  useEffect(() => {
    const t = searchParams.get('tab')
    if (t) setTab(t)
  }, [searchParams])

  // Reset pagination & selection when tab, search, or filters change
  useEffect(() => {
    setCurrentPage(1)
    setSelectedIds(new Set())
    setExpandedId(null)
  }, [tab, search, activeTags, pageSize])

  // Reset selection when exiting edit mode
  useEffect(() => {
    if (!editMode) setSelectedIds(new Set())
  }, [editMode])

  const q = search.toLowerCase()

  // Data Filtering
  const filteredPersonas = personaList.filter(n => {
    if (q && !(n.data.label || '').toLowerCase().includes(q) &&
        !(n.data.attrs?.description || '').toLowerCase().includes(q)) return false
    if (activeTags.size > 0) {
      const tags: string[] = n.data.attrs?.content_tags ?? []
      if (!tags.some(t => activeTags.has(t))) return false
    }
    return true
  })

  const filteredEvents = eventList.filter(ev => {
    if (q && !(ev.content || '').toLowerCase().includes(q) &&
        !(ev.topic || '').toLowerCase().includes(q) &&
        !(ev.group || '').toLowerCase().includes(q) &&
        !(ev.tags || []).some(t => t.toLowerCase().includes(q))) return false
    if (activeTags.size > 0) {
      if (!(ev.tags || []).some(t => activeTags.has(t))) return false
    }
    return true
  })

  const tagMatchedGroupIds = activeTags.size > 0
    ? new Set(filteredEvents.filter(ev => ev.group).map(ev => ev.group as string))
    : null

  const filteredGroups = groupList.filter(g => {
    if (q && !g.id.toLowerCase().includes(q)) return false
    if (tagMatchedGroupIds && !tagMatchedGroupIds.has(g.id)) return false
    return true
  })

  // Pagination Logic
  const paginate = <T,>(items: T[]) => items.slice((currentPage - 1) * pageSize, currentPage * pageSize)
  
  const paginatedPersonas = paginate(filteredPersonas)
  const totalPersonaPages = Math.max(1, Math.ceil(filteredPersonas.length / pageSize))

  const paginatedGroups = paginate(filteredGroups)
  const totalGroupPages = Math.max(1, Math.ceil(filteredGroups.length / pageSize))

  const sortedEvents = [...filteredEvents].sort((a, b) => new Date(b.start).getTime() - new Date(a.start).getTime())
  const paginatedEvents = paginate(sortedEvents)
  const totalEventPages = Math.max(1, Math.ceil(sortedEvents.length / pageSize))

  // Row toggle helpers
  const toggleExpand = (id: string) => {
    if (editMode) return
    setExpandedId(prev => prev === id ? null : id)
  }

  const toggleSelect = (id: string) => {
    const next = new Set(selectedIds)
    if (next.has(id)) next.delete(id); else next.add(id)
    setSelectedIds(next)
  }

  // Bulk delete
  const handleDeleteSelected = async () => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    if (!selectedIds.size) { app.toast(L.noSelected, 'destructive'); return }
    if (!confirm(L.confirmDelete(selectedIds.size))) return

    let ok = 0
    if (tab === 'personas') {
      for (const uid of selectedIds) {
        try { await api.graph.deletePersona(uid); ok++ } catch {}
      }
    } else if (tab === 'events') {
      for (const id of selectedIds) {
        try { await api.events.delete(id); ok++ } catch {}
      }
    }
    setSelectedIds(new Set())
    app.toast(L.deletedOk(ok))
    await loadData()
    await app.refreshStats()
  }

  const goToGraph = (uid: string) => {
    sessionStorage.setItem('em_focus_persona', uid)
    router.push('/graph')
  }

  const goToEvents = (eventId: string) => {
    sessionStorage.setItem('em_focus_event', eventId)
    router.push('/events')
  }

  // Select-all logic (applied to the current paginated view)
  const currentIds = tab === 'personas' ? paginatedPersonas.map(n => n.data.id) : tab === 'events' ? paginatedEvents.map(ev => ev.id) : []
  const allSelected = currentIds.length > 0 && currentIds.every(id => selectedIds.has(id))
  const someSelected = currentIds.some(id => selectedIds.has(id))

  const toggleAll = () => {
    if (allSelected) {
      const next = new Set(selectedIds)
      currentIds.forEach(id => next.delete(id))
      setSelectedIds(next)
    } else {
      const next = new Set(selectedIds)
      currentIds.forEach(id => next.add(id))
      setSelectedIds(next)
    }
  }

  const actions = (
    <div className="flex items-center gap-2">
      {editMode && selectedIds.size > 0 && (
        <Button variant="destructive" size="sm" onClick={handleDeleteSelected}>
          <Trash2 className="mr-1 size-3.5" />{L.deleteSelected} ({selectedIds.size})
        </Button>
      )}
      {(tab === 'personas' || tab === 'events') && (
        <Button
          variant={editMode ? 'default' : 'outline'}
          size="sm"
          onClick={() => setEditMode(v => !v)}
        >
          {editMode ? L.exitEditMode : L.editMode}
        </Button>
      )}
      <div className="relative">
        <Search className="text-muted-foreground pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2" />
        <Input
          className="h-7 w-48 pl-7 text-xs"
          placeholder={i18n.common.search + '…'}
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>
    </div>
  )

  // ── Pagination Footer Component ────────────────────────────────────────────
  const PaginationFooter = ({ totalItems, totalPages }: { totalItems: number, totalPages: number }) => (
    <div className="flex items-center justify-between border-t px-2 py-3 mt-4 shrink-0">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span>每页显示</span>
        <Select value={pageSize.toString()} onValueChange={(v: any) => setPageSize(Number(v))}>
          <SelectTrigger className="h-8 w-[70px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="25">25</SelectItem>
            <SelectItem value="50">50</SelectItem>
            <SelectItem value="100">100</SelectItem>
          </SelectContent>
        </Select>
        <span>项</span>
      </div>
      <div className="flex items-center gap-4">
        <span className="text-sm text-muted-foreground">
          {totalItems} Items (Page {currentPage}/{totalPages})
        </span>
        <Pagination className="justify-end w-auto mx-0">
          <PaginationContent>
            <PaginationItem>
              <PaginationPrevious
                href="#"
                size="sm"
                onClick={(e) => { e.preventDefault(); if (currentPage > 1) setCurrentPage(p => p - 1) }}
                className={currentPage === 1 ? "pointer-events-none opacity-50" : "cursor-pointer"}
              />
            </PaginationItem>
            <PaginationItem>
              <PaginationNext
                href="#"
                size="sm"
                onClick={(e) => { e.preventDefault(); if (currentPage < totalPages) setCurrentPage(p => p + 1) }}
                className={currentPage === totalPages ? "pointer-events-none opacity-50" : "cursor-pointer"}
              />
            </PaginationItem>
          </PaginationContent>
        </Pagination>
      </div>
    </div>
  )

  // ── Persona detail expand row ────────────────────────────────────────────
  const PersonaDetail = ({ node }: { node: api.PersonaNode }) => {
    const d = node.data
    const attrs = d.attrs || {}
    return (
      <TableRow className="bg-muted/40 hover:bg-muted/40">
        <TableCell colSpan={editMode ? 7 : 6} className="py-3">
          <div className="flex flex-col gap-3 px-2">
            <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-3">
              <div>
                <span className="text-muted-foreground text-xs">UID</span>
                <p className="font-mono text-xs">{d.id}</p>
              </div>
              {attrs.description && (
                <div className="col-span-2">
                  <span className="text-muted-foreground text-xs">{i18n.graph.description}</span>
                  <p className="text-sm">{attrs.description}</p>
                </div>
              )}
              {d.bound_identities?.length > 0 && (
                <div className="col-span-2">
                  <span className="text-muted-foreground text-xs">{i18n.graph.bindings}</span>
                  <div className="mt-0.5 flex flex-wrap gap-1">
                    {d.bound_identities.map(b => (
                      <Badge key={`${b.platform}:${b.physical_id}`} variant="outline" className="text-xs">
                        {b.platform}:{b.physical_id}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => goToGraph(d.id)}>
                <Network className="mr-1 size-3.5" />{L.viewInGraph}
              </Button>
              <Button size="sm" variant="ghost" disabled={!app.sudo}
                onClick={() => { app.toast('请在关系图页面编辑人格', 'destructive') }}>
                <Pencil className="mr-1 size-3.5" />{i18n.common.edit}
              </Button>
              <Button size="sm" variant="destructive" disabled={!app.sudo}
                onClick={async () => {
                  if (!confirm(`确认删除人格「${d.label}」？`)) return
                  try {
                    await api.graph.deletePersona(d.id)
                    app.toast('人格已删除')
                    setExpandedId(null)
                    await loadData()
                    await app.refreshStats()
                  } catch (e: unknown) {
                    app.toast('删除失败：' + (e as api.ApiError).body, 'destructive')
                  }
                }}>
                <Trash2 className="mr-1 size-3.5" />{i18n.common.delete}
              </Button>
            </div>
          </div>
        </TableCell>
      </TableRow>
    )
  }

  // ── Event detail expand row ──────────────────────────────────────────────
  const EventDetail = ({ ev }: { ev: api.ApiEvent }) => (
    <TableRow className="bg-muted/40 hover:bg-muted/40">
      <TableCell colSpan={editMode ? 6 : 5} className="py-3">
        <div className="flex flex-col gap-3 px-2">
          <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-3">
            <div>
              <span className="text-muted-foreground text-xs">ID</span>
              <p className="font-mono text-xs">{ev.id}</p>
            </div>
            <div>
              <span className="text-muted-foreground text-xs">{i18n.events.confidence}</span>
              <p className="text-sm">{(ev.confidence * 100).toFixed(0)}%</p>
            </div>
            {(ev.participants?.length ?? 0) > 0 && (
              <div className="col-span-2">
                <span className="text-muted-foreground text-xs">{i18n.events.participants}</span>
                <p className="text-sm">{ev.participants!.join(', ')}</p>
              </div>
            )}
            {(ev.inherit_from?.length ?? 0) > 0 && (
              <div className="col-span-2">
                <span className="text-muted-foreground text-xs">{i18n.events.inheritFrom}</span>
                <div className="mt-0.5 flex flex-wrap gap-1">
                  {ev.inherit_from!.map(id => (
                    <Badge key={id} variant="outline" className="cursor-pointer text-xs"
                      onClick={() => goToEvents(id)}>
                      {id.slice(0, 12)}…
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => goToEvents(ev.id)}>
              <GitBranch className="mr-1 size-3.5" />{L.viewInEvents}
            </Button>
            <Button size="sm" variant="destructive" disabled={!app.sudo}
              onClick={async () => {
                if (!confirm(`确认删除事件「${ev.content || ev.topic}」？`)) return
                try {
                  await api.events.delete(ev.id)
                  app.toast('事件已移入回收站')
                  setExpandedId(null)
                  await loadData()
                  await app.refreshStats()
                } catch (e: unknown) {
                  app.toast('删除失败：' + (e as api.ApiError).body, 'destructive')
                }
              }}>
              <Trash2 className="mr-1 size-3.5" />{i18n.common.delete}
            </Button>
          </div>
        </div>
      </TableCell>
    </TableRow>
  )

  // ── Checkbox cell ────────────────────────────────────────────────────────
  const SelectCell = ({ id }: { id: string }) => (
    <TableCell className="w-8 pr-0" onClick={e => { e.stopPropagation(); toggleSelect(id) }}>
      <Checkbox
        checked={selectedIds.has(id)}
        onCheckedChange={() => toggleSelect(id)}
        aria-label="选择此项"
      />
    </TableCell>
  )

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <PageHeader
        title={i18n.page.library.title}
        description={i18n.page.library.description}
        actions={actions}
      />

      <TagFilter tags={tagList} value={activeTags} onChange={setActiveTags} />

      <div className="flex flex-1 flex-col overflow-hidden p-6 pt-4">
        <Tabs value={tab} onValueChange={(t: SetStateAction<string>) => { setEditMode(false); setTab(t) }} className="flex flex-1 flex-col overflow-hidden">
          <TabsList className="mb-4 shrink-0">
            <TabsTrigger value="personas">
              <Users className="mr-1.5 size-3.5" />{i18n.library.tabs.personas}
            </TabsTrigger>
            <TabsTrigger value="groups">
              <Building2 className="mr-1.5 size-3.5" />{i18n.library.tabs.groups}
            </TabsTrigger>
            <TabsTrigger value="events">
              <Activity className="mr-1.5 size-3.5" />{i18n.library.tabs.events}
            </TabsTrigger>
            <TabsTrigger value="time">
              <Clock className="mr-1.5 size-3.5" />{i18n.library.tabs.time}
            </TabsTrigger>
          </TabsList>

          {/* PERSONAS */}
          <TabsContent value="personas" className="flex-1 overflow-hidden flex flex-col">
            <ScrollArea className="flex-1">
              <div className="overflow-hidden rounded-xl ring-1 ring-foreground/10">
                <Table>
                  <TableHeader>
                    <TableRow>
                      {editMode && (
                        <TableHead className="w-8 pr-0" onClick={toggleAll}>
                          <Checkbox
                            checked={allSelected ? true : (someSelected ? 'indeterminate' : false)}
                            onCheckedChange={toggleAll}
                            aria-label="选择全部"
                          />
                        </TableHead>
                      )}
                      <TableHead className="w-4"></TableHead>
                      <TableHead>名称</TableHead>
                      <TableHead>{i18n.graph.description}</TableHead>
                      <TableHead>{i18n.graph.affectType}</TableHead>
                      <TableHead>{i18n.graph.confidence}</TableHead>
                      <TableHead>{i18n.events.tags}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {paginatedPersonas.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={editMode ? 7 : 6} className="text-muted-foreground text-center py-8">
                          {i18n.library.personas.noPersonas}
                        </TableCell>
                      </TableRow>
                    ) : paginatedPersonas.map(n => {
                      const d = n.data
                      const attrs = d.attrs || {}
                      const isExpanded = expandedId === d.id
                      return (
                        <Fragment key={d.id}>
                          <TableRow
                            className="cursor-pointer"
                            onClick={() => editMode ? toggleSelect(d.id) : toggleExpand(d.id)}
                          >
                            {editMode && <SelectCell id={d.id} />}
                            <TableCell className="w-4 pr-0 text-muted-foreground">
                              {!editMode && (isExpanded
                                ? <ChevronDown className="size-3.5" />
                                : <ChevronRight className="size-3.5" />)}
                            </TableCell>
                            <TableCell className="font-medium">
                              {d.label}
                              {d.is_bot && (
                                <Badge variant="secondary" className="ml-1.5 text-xs">Bot</Badge>
                              )}
                            </TableCell>
                            <TableCell className="max-w-48 truncate text-sm">
                              {attrs.description || '—'}
                            </TableCell>
                            <TableCell className="text-sm">{attrs.affect_type || '—'}</TableCell>
                            <TableCell className="text-sm">{(d.confidence * 100).toFixed(0)}%</TableCell>
                            <TableCell>
                              <div className="flex flex-wrap gap-1">
                                {(attrs.content_tags || []).slice(0, 3).map((t: string) => (
                                  <Badge
                                    key={t}
                                    variant={activeTags.has(t) ? 'default' : 'secondary'}
                                    className="cursor-pointer text-xs"
                                    onClick={(e: { stopPropagation: () => void }) => {
                                      e.stopPropagation()
                                      const next = new Set(activeTags)
                                      if (next.has(t)) next.delete(t); else next.add(t)
                                      setActiveTags(next)
                                    }}
                                  >
                                    {t}
                                  </Badge>
                                ))}
                              </div>
                            </TableCell>
                          </TableRow>
                          {isExpanded && <PersonaDetail node={n} />}
                        </Fragment>
                      )
                    })}
                  </TableBody>
                </Table>
              </div>
            </ScrollArea>
            <PaginationFooter totalItems={filteredPersonas.length} totalPages={totalPersonaPages} />
          </TabsContent>

          {/* GROUPS */}
          <TabsContent value="groups" className="flex-1 overflow-hidden flex flex-col">
            <ScrollArea className="flex-1">
              <div className="overflow-hidden rounded-xl ring-1 ring-foreground/10">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{i18n.library.groups.groupId}</TableHead>
                      <TableHead>{i18n.library.groups.events}</TableHead>
                      <TableHead>{i18n.library.groups.lastActive}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {paginatedGroups.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={3} className="text-muted-foreground text-center py-8">
                          {i18n.library.groups.noGroups}
                        </TableCell>
                      </TableRow>
                    ) : paginatedGroups.map(g => (
                      <TableRow key={g.id}>
                        <TableCell className="font-mono text-sm">{g.id}</TableCell>
                        <TableCell className="text-sm">{g.event_count}</TableCell>
                        <TableCell className="text-sm">
                          {g.last_active ? new Date(g.last_active).toLocaleDateString('zh-CN') : '—'}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </ScrollArea>
            <PaginationFooter totalItems={filteredGroups.length} totalPages={totalGroupPages} />
          </TabsContent>

          {/* EVENTS */}
          <TabsContent value="events" className="flex-1 overflow-hidden flex flex-col">
            <ScrollArea className="flex-1">
              <div className="overflow-hidden rounded-xl ring-1 ring-foreground/10">
                <Table>
                  <TableHeader>
                    <TableRow>
                      {editMode && (
                        <TableHead className="w-8 pr-0" onClick={toggleAll}>
                          <Checkbox
                            checked={allSelected ? true : (someSelected ? 'indeterminate' : false)}
                            onCheckedChange={toggleAll}
                            aria-label="选择全部"
                          />
                        </TableHead>
                      )}
                      <TableHead className="w-4"></TableHead>
                      <TableHead>{i18n.events.topic}</TableHead>
                      <TableHead>{i18n.events.group}</TableHead>
                      <TableHead>{i18n.events.time}</TableHead>
                      <TableHead>{i18n.events.salience}</TableHead>
                      <TableHead>{i18n.events.tags}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {paginatedEvents.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={editMode ? 7 : 6} className="text-muted-foreground text-center py-8">
                          {i18n.common.noData}
                        </TableCell>
                      </TableRow>
                    ) : paginatedEvents.map(ev => {
                        const isExpanded = expandedId === ev.id
                        return (
                          <Fragment key={ev.id}>
                            <TableRow
                              className="cursor-pointer"
                              onClick={() => editMode ? toggleSelect(ev.id) : toggleExpand(ev.id)}
                            >
                              {editMode && <SelectCell id={ev.id} />}
                              <TableCell className="w-4 pr-0 text-muted-foreground">
                                {!editMode && (isExpanded
                                  ? <ChevronDown className="size-3.5" />
                                  : <ChevronRight className="size-3.5" />)}
                              </TableCell>
                              <TableCell className="max-w-60 truncate font-medium">
                                {ev.content || ev.topic || ev.id}
                              </TableCell>
                              <TableCell className="text-sm">{ev.group || i18n.events.privateChat}</TableCell>
                              <TableCell className="text-sm">
                                {new Date(ev.start).toLocaleDateString('zh-CN')}
                              </TableCell>
                              <TableCell className="text-sm">{(ev.salience * 100).toFixed(0)}%</TableCell>
                              <TableCell>
                                <div className="flex flex-wrap gap-1">
                                  {(ev.tags || []).slice(0, 3).map(t => (
                                    <Badge
                                      key={t}
                                      variant={activeTags.has(t) ? 'default' : 'secondary'}
                                      className="cursor-pointer text-xs"
                                      onClick={(e: { stopPropagation: () => void }) => {
                                        e.stopPropagation()
                                        const next = new Set(activeTags)
                                        if (next.has(t)) next.delete(t); else next.add(t)
                                        setActiveTags(next)
                                      }}
                                    >
                                      {t}
                                    </Badge>
                                  ))}
                                </div>
                              </TableCell>
                            </TableRow>
                            {isExpanded && <EventDetail ev={ev} />}
                          </Fragment>
                        )
                      })}
                  </TableBody>
                </Table>
              </div>
            </ScrollArea>
            <PaginationFooter totalItems={sortedEvents.length} totalPages={totalEventPages} />
          </TabsContent>

          {/* TIME */}
          <TabsContent value="time" className="flex-1 overflow-hidden">
            <ScrollArea className="h-full">
              <div className="flex flex-col gap-4">
                <p className="text-muted-foreground text-sm">{i18n.library.time.description}</p>
                {(() => {
                  const byMonth = new Map<string, api.ApiEvent[]>()
                  filteredEvents.forEach(ev => {
                    const month = ev.start.slice(0, 7)
                    if (!byMonth.has(month)) byMonth.set(month, [])
                    byMonth.get(month)!.push(ev)
                  })
                  const months = Array.from(byMonth.entries()).sort(([a], [b]) => b.localeCompare(a))
                  return months.map(([month, evs]) => (
                    <div key={month}>
                      <div className="mb-2 flex items-center gap-2">
                        <span className="font-mono text-sm font-semibold">{month}</span>
                        <Badge variant="secondary" className="text-xs">{evs.length} 事件</Badge>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {evs.slice(0, 20).map(ev => (
                          <Badge
                            key={ev.id}
                            variant="outline"
                            className="cursor-pointer text-xs"
                            onClick={() => goToEvents(ev.id)}
                          >
                            {ev.start.slice(5, 10)} {ev.content?.slice(0, 12) || ev.id.slice(0, 8)}
                          </Badge>
                        ))}
                        {evs.length > 20 && (
                          <Badge variant="outline" className="text-xs">+{evs.length - 20}</Badge>
                        )}
                      </div>
                    </div>
                  ))
                })()}
              </div>
            </ScrollArea>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}

export default function LibraryPage() {
  return (
    <Suspense fallback={<div className="text-muted-foreground flex h-screen items-center justify-center text-sm">加载中…</div>}>
      <LibraryContent />
    </Suspense>
  )
}