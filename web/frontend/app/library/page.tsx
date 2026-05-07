'use client'

import { useEffect, useState, useCallback, Suspense, Fragment } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import {
  Users, Building2, Activity, Clock, Search,
  ChevronDown, ChevronRight, Pencil, Trash2,
  Network, GitBranch, RefreshCw
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
import { FilterBar } from '@/components/shared/filter-bar'
import { DateRange } from 'react-day-picker'
import { EditPersonaDialog } from '@/components/graph/persona-dialogs'
import { EditEventDialog, type EventFormData } from '@/components/events/event-dialogs'
import { useApp } from '@/lib/store'
import * as api from '@/lib/api'
import { i18n } from '@/lib/i18n'

// ── Local UI strings ──────────────────────────────────────────────────────
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

// ── Shared Sub-components ─────────────────────────────────────────────────

function PaginationFooter({ 
  totalItems, totalPages, pageSize, currentPage, onPageChange, onPageSizeChange 
}: { 
  totalItems: number, totalPages: number, pageSize: number, currentPage: number,
  onPageChange: (p: number) => void, onPageSizeChange: (sz: number) => void
}) {
  return (
    <div className="flex items-center justify-between border-t px-2 py-3 mt-4 shrink-0">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span>每页显示</span>
        <Select value={pageSize.toString()} onValueChange={(v) => onPageSizeChange(Number(v))}>
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
                onClick={(e) => { e.preventDefault(); if (currentPage > 1) onPageChange(currentPage - 1) }}
                className={currentPage === 1 ? "pointer-events-none opacity-50" : "cursor-pointer"}
              />
            </PaginationItem>
            <PaginationItem>
              <PaginationNext
                href="#"
                size="sm"
                onClick={(e) => { e.preventDefault(); if (currentPage < totalPages) onPageChange(currentPage + 1) }}
                className={currentPage === totalPages ? "pointer-events-none opacity-50" : "cursor-pointer"}
              />
            </PaginationItem>
          </PaginationContent>
        </Pagination>
      </div>
    </div>
  )
}

function PersonaDetailRow({ 
  node, editMode, onGoToGraph, onEdit, onDelete, sudoMode 
}: { 
  node: api.PersonaNode, editMode: boolean, onGoToGraph: (uid: string) => void,
  onEdit: (n: api.PersonaNode) => void, onDelete: (id: string, label: string) => void,
  sudoMode: boolean
}) {
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
            <Button size="sm" variant="outline" onClick={() => onGoToGraph(d.id)}>
              <Network className="mr-1.5 size-3.5" />{L.viewInGraph}
            </Button>
            <Button size="sm" variant="ghost" disabled={!sudoMode} onClick={() => onEdit(node)}>
              <Pencil className="mr-1.5 size-3.5" />{i18n.common.edit}
            </Button>
            <Button size="sm" variant="destructive" disabled={!sudoMode} onClick={() => onDelete(d.id, d.label)}>
              <Trash2 className="mr-1.5 size-3.5" />{i18n.common.delete}
            </Button>
          </div>
        </div>
      </TableCell>
    </TableRow>
  )
}

function EventDetailRow({ 
  ev, editMode, onGoToEvents, onEdit, onDelete, sudoMode 
}: { 
  ev: api.ApiEvent, editMode: boolean, onGoToEvents: (id: string) => void,
  onEdit: (e: api.ApiEvent) => void, onDelete: (e: api.ApiEvent) => void,
  sudoMode: boolean
}) {
  return (
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
                    <Badge key={id} variant="outline" className="cursor-pointer text-xs" onClick={() => onGoToEvents(id)}>
                      {id.slice(0, 12)}…
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => onGoToEvents(ev.id)}>
              <GitBranch className="mr-1.5 size-3.5" />{L.viewInEvents}
            </Button>
            <Button size="sm" variant="ghost" disabled={!sudoMode} onClick={() => onEdit(ev)}>
              <Pencil className="mr-1.5 size-3.5" />{i18n.common.edit}
            </Button>
            <Button size="sm" variant="destructive" disabled={!sudoMode} onClick={() => onDelete(ev)}>
              <Trash2 className="mr-1.5 size-3.5" />{i18n.common.delete}
            </Button>
          </div>
        </div>
      </TableCell>
    </TableRow>
  )
}

// ── Main Content Component ────────────────────────────────────────────────

function LibraryContent() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const app = useApp()

  const [tab, setTab] = useState(searchParams.get('tab') || 'events')
  const [search, setSearch] = useState('')
  const [activeTags, setActiveTags] = useState<Set<string>>(new Set())
  const [dateRange, setDateRange] = useState<DateRange | undefined>()
  const [tagList, setTagList] = useState<{ name: string; count: number }[]>([])
  const [personaList, setPersonaList] = useState<api.PersonaNode[]>([])
  const [groupList, setGroupList] = useState<{ id: string; event_count: number; last_active?: string }[]>([])
  const [eventList, setEventList] = useState<api.ApiEvent[]>([])
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [editMode, setEditMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [pageSize, setPageSize] = useState<number>(25)
  const [currentPage, setCurrentPage] = useState<number>(1)
  const [editPersona, setEditPersona] = useState<api.PersonaNode | null>(null)
  const [editEvent, setEditEvent] = useState<api.ApiEvent | null>(null)

  const loadData = useCallback(async () => {
    const [tagsData, graphData, eventsData] = await Promise.allSettled([
      api.tags.list(),
      api.graph.get(),
      api.events.list(1000),
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
    setTimeout(() => loadData(), 0)
  }, [loadData])

  useEffect(() => {
    const t = searchParams.get('tab')
    if (t) setTimeout(() => setTab(t), 0)
  }, [searchParams])

  useEffect(() => {
    setTimeout(() => {
      setCurrentPage(1)
      setSelectedIds(new Set())
      setExpandedId(null)
    }, 0)
  }, [tab, search, activeTags, dateRange, pageSize])

  useEffect(() => {
    if (!editMode) setTimeout(() => setSelectedIds(new Set()), 0)
  }, [editMode])

  const q = search.toLowerCase()
  const filteredPersonas = personaList.filter(n => {
    if (q && !(n.data.label || '').toLowerCase().includes(q) && !(n.data.attrs?.description || '').toLowerCase().includes(q)) return false
    if (activeTags.size > 0 && !(n.data.attrs?.content_tags ?? []).some(t => activeTags.has(t))) return false
    if (dateRange?.from) {
      const fromTs = dateRange.from.getTime()
      const toTs = dateRange.to ? dateRange.to.getTime() + 86400000 : fromTs + 86400000
      const ts = new Date(n.data.last_active_at || 0).getTime()
      if (ts < fromTs || ts > toTs) return false
    }
    return true
  })

  const filteredEvents = eventList.filter(ev => {
    if (q && !(ev.content || '').toLowerCase().includes(q) && !(ev.topic || '').toLowerCase().includes(q) && !(ev.group || '').toLowerCase().includes(q) && !(ev.tags || []).some(t => t.toLowerCase().includes(q))) return false
    if (activeTags.size > 0 && !(ev.tags || []).some(t => activeTags.has(t))) return false
    if (dateRange?.from) {
      const fromTs = dateRange.from.getTime()
      const toTs = dateRange.to ? dateRange.to.getTime() + 86400000 : fromTs + 86400000
      const ts = new Date(ev.start).getTime()
      if (ts < fromTs || ts > toTs) return false
    }
    return true
  })

  const tagMatchedGroupIds = activeTags.size > 0 ? new Set(filteredEvents.filter(ev => ev.group).map(ev => ev.group as string)) : null
  const filteredGroups = groupList.filter(g => {
    if (q && !g.id.toLowerCase().includes(q)) return false
    if (tagMatchedGroupIds && !tagMatchedGroupIds.has(g.id)) return false
    return true
  })

  const paginate = <T,>(items: T[]) => items.slice((currentPage - 1) * pageSize, currentPage * pageSize)
  const paginatedPersonas = paginate(filteredPersonas)
  const totalPersonaPages = Math.max(1, Math.ceil(filteredPersonas.length / pageSize))
  const paginatedGroups = paginate(filteredGroups)
  const totalGroupPages = Math.max(1, Math.ceil(filteredGroups.length / pageSize))
  const sortedEvents = [...filteredEvents].sort((a, b) => new Date(b.start).getTime() - new Date(a.start).getTime())
  const paginatedEvents = paginate(sortedEvents)
  const totalEventPages = Math.max(1, Math.ceil(sortedEvents.length / pageSize))

  const toggleExpand = (id: string) => { if (!editMode) setExpandedId(prev => prev === id ? null : id) }
  const toggleSelect = (id: string) => { const next = new Set(selectedIds); if (next.has(id)) next.delete(id); else next.add(id); setSelectedIds(next) }

  const handleDeleteSelected = async () => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    if (!selectedIds.size) { app.toast(L.noSelected, 'destructive'); return }
    if (!confirm(L.confirmDelete(selectedIds.size))) return
    let ok = 0
    if (tab === 'personas') { for (const uid of selectedIds) { try { await api.graph.deletePersona(uid); ok++ } catch {} } }
    else if (tab === 'events') { for (const id of selectedIds) { try { await api.events.delete(id); ok++ } catch {} } }
    setSelectedIds(new Set())
    app.toast(L.deletedOk(ok))
    loadData()
    app.refreshStats()
  }

  const handleEditPersonaSubmit = async (uid: string, data: Record<string, unknown>) => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    await api.graph.updatePersona(uid, data)
    app.toast(i18n.common.updateOk)
    loadData()
    setEditPersona(null)
  }

  const handleEditEventSubmit = async (id: string, data: EventFormData) => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    await api.events.update(id, {
      topic:             data.topic,
      group_id:          data.group_id || null,
      start_time:        Math.floor(new Date(data.start_time).getTime() / 1000),
      end_time:          Math.floor(new Date(data.end_time).getTime() / 1000),
      salience:          data.salience,
      chat_content_tags: data.tags,
      participants:      data.participants,
      inherit_from:      data.inherit_from,
      is_locked:         data.is_locked,
      confidence:        editEvent?.confidence ?? 0.8,
    })
    app.toast(i18n.common.updateOk)
    loadData()
    setEditEvent(null)
  }

  const goToGraph = (uid: string) => { sessionStorage.setItem('em_focus_persona', uid); router.push('/graph') }
  const goToEvents = (eventId: string) => { sessionStorage.setItem('em_focus_event', eventId); router.push('/events') }

  const currentIds = tab === 'personas' ? paginatedPersonas.map(n => n.data.id) : tab === 'events' ? paginatedEvents.map(ev => ev.id) : []
  const allSelected = currentIds.length > 0 && currentIds.every(id => selectedIds.has(id))
  const someSelected = currentIds.some(id => selectedIds.has(id))

  const toggleAll = () => {
    const next = new Set(selectedIds)
    if (allSelected) currentIds.forEach(id => next.delete(id))
    else currentIds.forEach(id => next.add(id))
    setSelectedIds(next)
  }

  const handleDeletePersona = async (id: string, label: string) => {
    if (!confirm(`确认删除人格「${label}」？`)) return
    try {
      await api.graph.deletePersona(id)
      app.toast('人格已删除')
      setExpandedId(null)
      loadData()
      app.refreshStats()
    } catch (e: unknown) {
      app.toast('删除失败：' + (e as api.ApiError).body, 'destructive')
    }
  }

  const handleDeleteEvent = async (ev: api.ApiEvent) => {
    if (!confirm(`确认删除事件「${ev.content || ev.topic}」？`)) return
    try {
      await api.events.delete(ev.id)
      app.toast('事件已移入回收站')
      setExpandedId(null)
      loadData()
      app.refreshStats()
    } catch (e: unknown) {
      app.toast('删除失败：' + (e as api.ApiError).body, 'destructive')
    }
  }

  const actions = (
    <div className="flex items-center gap-2">
      <div className="relative">
        <Search className="text-muted-foreground pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2" />
        <Input
          className="h-7 w-48 pl-7 text-xs"
          placeholder={i18n.common.search + '…'}
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>
      {editMode && selectedIds.size > 0 && (
        <Button variant="destructive" size="sm" onClick={handleDeleteSelected}>
          <Trash2 className="mr-1.5 size-3.5" />{L.deleteSelected} ({selectedIds.size})
        </Button>
      )}
      {(tab === 'personas' || tab === 'events') && (
        <Button variant={editMode ? 'default' : 'outline'} size="sm" onClick={() => setEditMode(v => !v)}>
          <Pencil className="mr-1.5 size-3.5" />{editMode ? L.exitEditMode : L.editMode}
        </Button>
      )}
      <Button variant="ghost" size="icon" onClick={loadData} title={i18n.common.refresh}>
        <RefreshCw className="size-4" />
      </Button>
    </div>
  )

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <PageHeader
        title={i18n.page.library.title}
        description={i18n.page.library.description}
        actions={actions}
      />

      <FilterBar
        tags={tagList}
        activeTags={activeTags}
        onTagsChange={setActiveTags}
        dateRange={dateRange}
        onDateRangeChange={setDateRange}
      />

      <div className="flex flex-1 flex-col overflow-hidden p-6 pt-2">
        <Tabs value={tab} onValueChange={(t) => { setEditMode(false); setTab(t) }} className="flex flex-1 flex-col overflow-hidden">
          <TabsList className="mb-4 shrink-0">
            <TabsTrigger value="events"><Activity className="mr-1.5 size-3.5" />{i18n.library.tabs.events}</TabsTrigger>
            <TabsTrigger value="time"><Clock className="mr-1.5 size-3.5" />{i18n.library.tabs.time}</TabsTrigger>
            <TabsTrigger value="personas"><Users className="mr-1.5 size-3.5" />{i18n.library.tabs.personas}</TabsTrigger>
            <TabsTrigger value="groups"><Building2 className="mr-1.5 size-3.5" />{i18n.library.tabs.groups}</TabsTrigger>
          </TabsList>

          <TabsContent value="events" className="flex-1 overflow-hidden flex flex-col">
            <ScrollArea className="flex-1">
              <div className="overflow-hidden border-y">
                <Table>
                  <TableHeader>
                    <TableRow>
                      {editMode && (
                        <TableHead className="w-8 pr-0" onClick={toggleAll}>
                          <Checkbox checked={allSelected ? true : (someSelected ? 'indeterminate' : false)} onCheckedChange={toggleAll} aria-label="选择全部" />
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
                    {paginatedEvents.length === 0 ? (<TableRow><TableCell colSpan={editMode ? 7 : 6} className="text-muted-foreground text-center py-8">{i18n.common.noData}</TableCell></TableRow>)
                    : paginatedEvents.map(ev => (
                      <Fragment key={ev.id}>
                        <TableRow className="cursor-pointer" onClick={() => editMode ? toggleSelect(ev.id) : toggleExpand(ev.id)}>
                          {editMode && (
                            <TableCell className="w-8 pr-0" onClick={e => { e.stopPropagation(); toggleSelect(ev.id) }}>
                              <Checkbox checked={selectedIds.has(ev.id)} onCheckedChange={() => toggleSelect(ev.id)} aria-label="选择此项" />
                            </TableCell>
                          )}
                          <TableCell className="w-4 pr-0 text-muted-foreground">{!editMode && (expandedId === ev.id ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />)}</TableCell>
                          <TableCell className="max-w-60 truncate font-medium">{ev.content || ev.topic || ev.id}</TableCell>
                          <TableCell className="text-sm">{ev.group || i18n.events.privateChat}</TableCell>
                          <TableCell className="text-sm">{new Date(ev.start).toLocaleDateString('zh-CN')}</TableCell>
                          <TableCell className="text-sm">{(ev.salience * 100).toFixed(0)}%</TableCell>
                          <TableCell>
                            <div className="flex flex-wrap gap-1">{(ev.tags || []).slice(0, 3).map(t => (
                              <Badge key={t} variant={activeTags.has(t) ? 'default' : 'secondary'} className="cursor-pointer text-xs" onClick={(e) => { e.stopPropagation(); const next = new Set(activeTags); if (next.has(t)) next.delete(t); else next.add(t); setActiveTags(next) }}>{t}</Badge>
                            ))}</div>
                          </TableCell>
                        </TableRow>
                        {expandedId === ev.id && (
                          <EventDetailRow ev={ev} editMode={editMode} onGoToEvents={goToEvents} onEdit={setEditEvent} onDelete={handleDeleteEvent} sudoMode={app.sudo} />
                        )}
                      </Fragment>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </ScrollArea>
            <PaginationFooter totalItems={sortedEvents.length} totalPages={totalEventPages} pageSize={pageSize} currentPage={currentPage} onPageChange={setCurrentPage} onPageSizeChange={setPageSize} />
          </TabsContent>

          <TabsContent value="time" className="flex-1 overflow-hidden">
            <ScrollArea className="h-full">
              <div className="flex flex-col gap-4">
                <p className="text-muted-foreground text-sm">{i18n.library.time.description}</p>
                {(() => {
                  const byMonth = new Map<string, api.ApiEvent[]>()
                  filteredEvents.forEach(ev => { const month = ev.start.slice(0, 7); if (!byMonth.has(month)) byMonth.set(month, []); byMonth.get(month)!.push(ev) })
                  return Array.from(byMonth.entries()).sort(([a], [b]) => b.localeCompare(a)).map(([month, evs]) => (
                    <div key={month}>
                      <div className="mb-2 flex items-center gap-2"><span className="font-mono text-sm font-semibold">{month}</span><Badge variant="secondary" className="text-xs">{evs.length} 事件</Badge></div>
                      <div className="flex flex-wrap gap-1.5">{evs.slice(0, 20).map(ev => (
                        <Badge key={ev.id} variant="outline" className="cursor-pointer text-xs" onClick={() => goToEvents(ev.id)}>{ev.start.slice(5, 10)} {ev.content?.slice(0, 12) || ev.id.slice(0, 8)}</Badge>
                      ))}{evs.length > 20 && <Badge variant="outline" className="text-xs">+{evs.length - 20}</Badge>}</div>
                    </div>
                  ))
                })()}
              </div>
            </ScrollArea>
          </TabsContent>

          <TabsContent value="personas" className="flex-1 overflow-hidden flex flex-col">
            <ScrollArea className="flex-1">
              <div className="overflow-hidden border-y">
                <Table>
                  <TableHeader>
                    <TableRow>
                      {editMode && (
                        <TableHead className="w-8 pr-0" onClick={toggleAll}>
                          <Checkbox checked={allSelected ? true : (someSelected ? 'indeterminate' : false)} onCheckedChange={toggleAll} aria-label="选择全部" />
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
                      <TableRow><TableCell colSpan={editMode ? 7 : 6} className="text-muted-foreground text-center py-8">{i18n.library.personas.noPersonas}</TableCell></TableRow>
                    ) : paginatedPersonas.map(n => (
                      <Fragment key={n.data.id}>
                        <TableRow className="cursor-pointer" onClick={() => editMode ? toggleSelect(n.data.id) : toggleExpand(n.data.id)}>
                          {editMode && (
                            <TableCell className="w-8 pr-0" onClick={e => { e.stopPropagation(); toggleSelect(n.data.id) }}>
                              <Checkbox checked={selectedIds.has(n.data.id)} onCheckedChange={() => toggleSelect(n.data.id)} aria-label="选择此项" />
                            </TableCell>
                          )}
                          <TableCell className="w-4 pr-0 text-muted-foreground">
                            {!editMode && (expandedId === n.data.id ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />)}
                          </TableCell>
                          <TableCell className="font-medium">{n.data.label}{n.data.is_bot && <Badge variant="secondary" className="ml-1.5 text-xs">Bot</Badge>}</TableCell>
                          <TableCell className="max-w-48 truncate text-sm">{n.data.attrs?.description || '—'}</TableCell>
                          <TableCell className="text-sm">{n.data.attrs?.affect_type || '—'}</TableCell>
                          <TableCell className="text-sm">{(n.data.confidence * 100).toFixed(0)}%</TableCell>
                          <TableCell>
                            <div className="flex flex-wrap gap-1">{(n.data.attrs?.content_tags || []).slice(0, 3).map(t => (
                              <Badge key={t} variant={activeTags.has(t) ? 'default' : 'secondary'} className="cursor-pointer text-xs" onClick={(e) => { e.stopPropagation(); const next = new Set(activeTags); if (next.has(t)) next.delete(t); else next.add(t); setActiveTags(next) }}>{t}</Badge>
                            ))}</div>
                          </TableCell>
                        </TableRow>
                        {expandedId === n.data.id && (
                          <PersonaDetailRow node={n} editMode={editMode} onGoToGraph={goToGraph} onEdit={setEditPersona} onDelete={handleDeletePersona} sudoMode={app.sudo} />
                        )}
                      </Fragment>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </ScrollArea>
            <PaginationFooter totalItems={filteredPersonas.length} totalPages={totalPersonaPages} pageSize={pageSize} currentPage={currentPage} onPageChange={setCurrentPage} onPageSizeChange={setPageSize} />
          </TabsContent>

          <TabsContent value="groups" className="flex-1 overflow-hidden flex flex-col">
            <ScrollArea className="flex-1">
              <div className="overflow-hidden border-y">
                <Table>
                  <TableHeader><TableRow><TableHead>{i18n.library.groups.groupId}</TableHead><TableHead>{i18n.library.groups.events}</TableHead><TableHead>{i18n.library.groups.lastActive}</TableHead></TableRow></TableHeader>
                  <TableBody>
                    {paginatedGroups.length === 0 ? (<TableRow><TableCell colSpan={3} className="text-muted-foreground text-center py-8">{i18n.library.groups.noGroups}</TableCell></TableRow>) 
                    : paginatedGroups.map(g => (<TableRow key={g.id}><TableCell className="font-mono text-sm">{g.id}</TableCell><TableCell className="text-sm">{g.event_count}</TableCell><TableCell className="text-sm">{g.last_active ? new Date(g.last_active).toLocaleDateString('zh-CN') : '—'}</TableCell></TableRow>))}
                  </TableBody>
                </Table>
              </div>
            </ScrollArea>
            <PaginationFooter totalItems={filteredGroups.length} totalPages={totalGroupPages} pageSize={pageSize} currentPage={currentPage} onPageChange={setCurrentPage} onPageSizeChange={setPageSize} />
          </TabsContent>
        </Tabs>
      </div>

      <EditPersonaDialog open={!!editPersona} node={editPersona} onClose={() => setEditPersona(null)} onSubmit={handleEditPersonaSubmit} />
      <EditEventDialog open={!!editEvent} event={editEvent} onClose={() => setEditEvent(null)} onSubmit={handleEditEventSubmit} tagSuggestions={tagList.map(t => t.name)} events={eventList} />
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
