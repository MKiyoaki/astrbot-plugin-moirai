'use client'

import { useEffect, useState, useCallback, useDeferredValue, useMemo } from 'react'
import { Search, Pencil, Trash2, Archive, Activity, Clock, Users, Building2 } from 'lucide-react'
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
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { buttonVariants } from '@/components/ui/button'
import { PageHeader } from '@/components/layout/page-header'
import { FilterBar } from '@/components/shared/filter-bar'
import { RefreshButton } from '@/components/shared/refresh-button'
import { EditPersonaDialog } from '@/components/graph/persona-dialogs'
import { EditEventDialog, RecycleBinDialog, ArchiveEventsDialog, type EventFormData } from '@/components/events/event-dialogs'
import { EventRow } from '@/components/library/event-row'
import { PersonaRow } from '@/components/library/persona-row'
import { GroupRow, type GroupInfo } from '@/components/library/group-row'
import { PaginationFooter } from '@/components/library/pagination-footer'
import { DateRange } from 'react-day-picker'
import { useApp } from '@/lib/store'
import { setStored } from '@/lib/safe-storage'
import * as api from '@/lib/api'
import { cn } from '@/lib/utils'
import { useRouter } from 'next/navigation'

/** Start time in ms. Prefers the numeric start_ts the API already sends,
 *  so hot paths never re-parse the ISO string. */
function eventStartMsOf(ev: api.ApiEvent): number {
  return ev.start_ts ? ev.start_ts * 1000 : new Date(ev.start).getTime()
}

/** Months rendered per batch in the Time tab. */
const MONTH_PAGE = 12

function LibraryContent() {
  const { i18n, lang, refreshStats, setRawGraph, toast, sudo, currentPersonaName, scopeMode } = useApp()
  const personaFilter = scopeMode === 'single' ? (currentPersonaName ?? api.LEGACY_PERSONA_TOKEN) : null
  const router = useRouter()

  const L = useMemo(() => ({
    editMode:       lang === 'zh' ? '编辑模式' : lang === 'ja' ? '編集モード' : 'Edit Mode',
    exitEditMode:   lang === 'zh' ? '退出编辑' : lang === 'ja' ? '編集終了' : 'Exit Edit',
    deleteSelected: lang === 'zh' ? '删除所选' : lang === 'ja' ? '選択削除' : 'Delete Selected',
    noSelected:     lang === 'zh' ? '未选择任何项目' : lang === 'ja' ? '選択なし' : 'No items selected',
    confirmDelete:  (n: number) => lang === 'zh' ? `确认删除选中的 ${n} 项？` : lang === 'ja' ? `選択した ${n} 件を削除しますか？` : `Confirm deleting ${n} items?`,
    deletedOk:      (n: number) => lang === 'zh' ? `已删除 ${n} 项` : lang === 'ja' ? `${n} 件を削除しました` : `Deleted ${n} items`,
    confirmDeleteTitle: lang === 'zh' ? '确认删除' : lang === 'ja' ? '削除の確認' : 'Confirm Delete',
    cancel: lang === 'zh' ? '取消' : lang === 'ja' ? 'キャンセル' : 'Cancel',
    delete: lang === 'zh' ? '删除' : lang === 'ja' ? '削除' : 'Delete',
    loading: lang === 'zh' ? '加载中…' : lang === 'ja' ? '読み込み中…' : 'Loading…',
    actionsHead: lang === 'zh' ? '操作' : lang === 'ja' ? '操作' : 'Actions',
    nameHead: lang === 'zh' ? '名称' : lang === 'ja' ? '名前' : 'Name',
    loadMoreMonths: (n: number) => lang === 'zh' ? `加载更早的月份（还有 ${n} 个）` : lang === 'ja' ? `さらに読み込む（残り ${n} ヶ月）` : `Load earlier months (${n} left)`,
  }), [lang])

  const [tab, setTab] = useState(() => {
    if (typeof window !== 'undefined') {
      const p = new URLSearchParams(window.location.search).get('tab')
      if (p) return p
    }
    return 'events'
  })
  const [search, setSearch] = useState('')
  // Input stays responsive; filtering runs at lower priority.
  const deferredSearch = useDeferredValue(search)
  const [monthLimit, setMonthLimit] = useState(MONTH_PAGE)
  const [activeTags, setActiveTags] = useState<Set<string>>(new Set())
  const [dateRange, setDateRange] = useState<DateRange | undefined>()
  const [tagList, setTagList] = useState<{ name: string; count: number }[]>([])
  const [personaList, setPersonaList] = useState<api.PersonaNode[]>([])
  const [eventList, setEventList] = useState<api.ApiEvent[]>([])
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [editMode, setEditMode] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [pageSize, setPageSize] = useState<number>(25)
  const [currentPage, setCurrentPage] = useState<number>(1)
  const [editPersona, setEditPersona] = useState<api.PersonaNode | null>(null)
  const [editEvent, setEditEvent] = useState<api.ApiEvent | null>(null)
  const [deleteDialog, setDeleteDialog] = useState<{
    open: boolean; title: string; onConfirm: () => void
  }>({ open: false, title: '', onConfirm: () => {} })

  const [binOpen, setBinOpen] = useState(false)
  const [binItems, setBinItems] = useState<any[]>([])
  const [binLoading, setBinLoading] = useState(false)
  const [archiveBinOpen, setArchiveBinOpen] = useState(false)
  const [archiveBinItems, setArchiveBinItems] = useState<api.ApiEvent[]>([])
  const [archiveBinLoading, setArchiveBinLoading] = useState(false)

  const openBin = useCallback(async () => {
    setBinOpen(true)
    setBinLoading(true)
    try {
      const res = await api.events.recycleBin()
      setBinItems(res.items)
    } catch {
      toast(i18n.events.binLoadError, 'destructive')
    } finally {
      setBinLoading(false)
    }
  }, [toast, i18n])

  const handleRestore = async (eventId: string) => {
    if (!sudo) { toast(i18n.common.needSudo, 'destructive'); return }
    try {
      await api.events.restore(eventId)
      toast(i18n.events.restoreSuccess)
      setBinItems(prev => prev.filter(x => x.id !== eventId))
      loadEvents()
      refreshStats()
    } catch (e: any) {
      toast(e?.body || e?.message || i18n.common.updateFailed, 'destructive')
    }
  }

  const handleClearBin = async () => {
    if (!sudo) { toast(i18n.common.needSudo, 'destructive'); return }
    if (!confirm(i18n.events.clearBinConfirm)) return
    try {
      await api.events.clearBin()
      toast(i18n.events.binClearSuccess)
      setBinItems([])
    } catch {
      toast(i18n.common.deleteFailed, 'destructive')
    }
  }

  const openArchiveBin = useCallback(async () => {
    setArchiveBinOpen(true)
    setArchiveBinLoading(true)
    try {
      const res = await api.events.listArchived()
      setArchiveBinItems(res.items)
    } catch {
      toast(i18n.events.archiveBinLoadError, 'destructive')
    } finally {
      setArchiveBinLoading(false)
    }
  }, [toast, i18n])

  const handleUnarchive = async (eventId: string) => {
    if (!sudo) { toast(i18n.common.needSudo, 'destructive'); return }
    try {
      await api.events.unarchive(eventId)
      toast(i18n.events.unarchiveSuccess)
      setArchiveBinItems(prev => prev.filter(x => x.id !== eventId))
      loadEvents()
      refreshStats()
    } catch (e: any) {
      toast(e?.body || e?.message || i18n.common.updateFailed, 'destructive')
    }
  }

  /** Tags + events only. /api/graph issues one impression query per persona and one
   *  message-count query per impression, so the list must not wait on it. */
  const loadEvents = useCallback(async () => {
    setIsRefreshing(true)
    try {
      const [tagsData, eventsData] = await Promise.allSettled([
        api.tags.list(),
        api.events.list(1000, personaFilter),
      ])
      if (tagsData.status === 'fulfilled') setTagList(tagsData.value.tags)
      if (eventsData.status === 'fulfilled') {
        // Sorted once here so render-time filtering stays order-preserving.
        setEventList([...eventsData.value.items].sort((a, b) => eventStartMsOf(b) - eventStartMsOf(a)))
      }
    } finally {
      setTimeout(() => setIsRefreshing(false), 600)
    }
  }, [personaFilter])

  /** Personas + graph. Only the Personas tab and group member names need it. */
  const loadGraph = useCallback(async () => {
    try {
      const graph = await api.graph.get(personaFilter)
      setPersonaList(graph.nodes)
      setRawGraph(graph)
    } catch {
      /* Missing personas only degrade display names */
    }
  }, [setRawGraph, personaFilter])

  const loadData = useCallback(async () => {
    await Promise.allSettled([loadEvents(), loadGraph()])
  }, [loadEvents, loadGraph])

  useEffect(() => { loadData() }, [loadData])

  // Reset paging/selection on filter change; equality-guarded to avoid no-op renders.
  useEffect(() => {
    setCurrentPage(prev => (prev === 1 ? prev : 1))
    setSelectedIds(prev => (prev.size === 0 ? prev : new Set()))
    setExpandedId(prev => (prev === null ? prev : null))
    setMonthLimit(prev => (prev === MONTH_PAGE ? prev : MONTH_PAGE))
  }, [tab, deferredSearch, activeTags, dateRange, pageSize])

  useEffect(() => {
    if (!editMode) setSelectedIds(prev => (prev.size === 0 ? prev : new Set()))
  }, [editMode])

  // ── Derived data ──────────────────────────────────────────────────────────

  /** Group rows + event→group index, built in one pass. Derived rather than stored
   *  so it recomputes once personas arrive. */
  const { groupList, eventGroupIndex } = useMemo(() => {
    const groups = new Map<string, GroupInfo>()
    const index = new Map<string, string>()
    const botUids = new Set(personaList.filter(n => n.data.is_bot).map(n => n.data.id))
    const labelByUid = new Map(personaList.map(n => [n.data.id, n.data.label]))

    for (const ev of eventList) {
      let groupId = ev.group
      let type: 'group' | 'private' = 'group'
      let displayName = ev.group || ''

      if (!groupId) {
        const other = ev.participants.find(p => !botUids.has(p))
        if (other) {
          groupId = `private:${other}`
          type = 'private'
          displayName = labelByUid.get(other) ?? other
        } else {
          groupId = 'private:unknown'
          type = 'private'
          displayName = i18n.events.privateChat
        }
      }
      index.set(ev.id, groupId)

      const existing = groups.get(groupId)
      if (!existing) {
        groups.set(groupId, { id: groupId, displayName, type, event_count: 1, last_active: ev.start, participants: [...ev.participants] })
      } else {
        existing.event_count++
        if (!existing.last_active || ev.start > existing.last_active) existing.last_active = ev.start
        ev.participants.forEach(p => { if (!existing.participants.includes(p)) existing.participants.push(p) })
      }
    }

    return {
      groupList: Array.from(groups.values())
        .sort((a, b) => (b.last_active || '') > (a.last_active || '') ? 1 : -1),
      eventGroupIndex: index,
    }
  }, [eventList, personaList, i18n.events.privateChat])

  // Cached against their sources: typing, paging and store updates no longer
  // re-lowercase, re-parse or re-sort the full event set.

  const q = deferredSearch.trim().toLowerCase()

  /** Event id → prebuilt lowercase haystack; search does one includes per row. */
  const eventHaystack = useMemo(() => {
    const index = new Map<string, string>()
    for (const ev of eventList) {
      index.set(ev.id, [ev.content, ev.topic, ev.group, ...(ev.tags ?? [])]
        .filter(Boolean).join(' ').toLowerCase())
    }
    return index
  }, [eventList])

  /** Persona uid → lowercase haystack. */
  const personaHaystack = useMemo(() => {
    const index = new Map<string, string>()
    for (const n of personaList) {
      index.set(n.data.id, `${n.data.label ?? ''} ${n.data.attrs?.description ?? ''}`.toLowerCase())
    }
    return index
  }, [personaList])

  /** Persona uid → last_active in ms. */
  const personaActiveMs = useMemo(() => {
    const index = new Map<string, number>()
    for (const n of personaList) {
      index.set(n.data.id, new Date(n.data.last_active_at || 0).getTime())
    }
    return index
  }, [personaList])

  /** Range bounds computed once. */
  const dateBounds = useMemo(() => {
    if (!dateRange?.from) return null
    const fromTs = dateRange.from.getTime()
    return { fromTs, toTs: dateRange.to ? dateRange.to.getTime() + 86400000 : fromTs + 86400000 }
  }, [dateRange])

  const filteredPersonas = useMemo(() => {
    if (!q && activeTags.size === 0 && !dateBounds) return personaList
    return personaList.filter(n => {
      if (q && !(personaHaystack.get(n.data.id) ?? '').includes(q)) return false
      if (activeTags.size > 0 && !(n.data.attrs?.content_tags ?? []).some(t => activeTags.has(t))) return false
      if (dateBounds) {
        const ts = personaActiveMs.get(n.data.id) ?? 0
        if (ts < dateBounds.fromTs || ts > dateBounds.toTs) return false
      }
      return true
    })
  }, [personaList, personaHaystack, personaActiveMs, q, activeTags, dateBounds])

  // eventList is already sorted at load time and filtering preserves order.
  const filteredEvents = useMemo(() => {
    if (!q && activeTags.size === 0 && !dateBounds) return eventList
    return eventList.filter(ev => {
      if (q && !(eventHaystack.get(ev.id) ?? '').includes(q)) return false
      if (activeTags.size > 0 && !(ev.tags ?? []).some(t => activeTags.has(t))) return false
      if (dateBounds) {
        const ts = eventStartMsOf(ev)
        if (ts < dateBounds.fromTs || ts > dateBounds.toTs) return false
      }
      return true
    })
  }, [eventList, eventHaystack, q, activeTags, dateBounds])

  const tagMatchedGroupIds = useMemo(() => {
    if (activeTags.size === 0) return null
    const ids = new Set<string>()
    for (const ev of filteredEvents) {
      ids.add(eventGroupIndex.get(ev.id) ?? (ev.group || 'private:unknown'))
    }
    return ids
  }, [activeTags, filteredEvents, eventGroupIndex])

  const filteredGroups = useMemo(() => {
    if (!q && !tagMatchedGroupIds) return groupList
    return groupList.filter(g => {
      if (q && !g.id.toLowerCase().includes(q) && !g.displayName.toLowerCase().includes(q)) return false
      if (tagMatchedGroupIds && !tagMatchedGroupIds.has(g.id)) return false
      return true
    })
  }, [groupList, q, tagMatchedGroupIds])

  const sliceStart = (currentPage - 1) * pageSize
  const paginatedPersonas = useMemo(
    () => filteredPersonas.slice(sliceStart, sliceStart + pageSize),
    [filteredPersonas, sliceStart, pageSize])
  const totalPersonaPages = Math.max(1, Math.ceil(filteredPersonas.length / pageSize))
  const paginatedGroups = useMemo(
    () => filteredGroups.slice(sliceStart, sliceStart + pageSize),
    [filteredGroups, sliceStart, pageSize])
  const totalGroupPages = Math.max(1, Math.ceil(filteredGroups.length / pageSize))
  const paginatedEvents = useMemo(
    () => filteredEvents.slice(sliceStart, sliceStart + pageSize),
    [filteredEvents, sliceStart, pageSize])
  const totalEventPages = Math.max(1, Math.ceil(filteredEvents.length / pageSize))

  /** Time tab: bucket by month only when the filtered set changes. */
  const eventsByMonth = useMemo(() => {
    const byMonth = new Map<string, api.ApiEvent[]>()
    for (const ev of filteredEvents) {
      const month = ev.start.slice(0, 7)
      const bucket = byMonth.get(month)
      if (bucket) bucket.push(ev)
      else byMonth.set(month, [ev])
    }
    return Array.from(byMonth.entries()).sort(([a], [b]) => b.localeCompare(a))
  }, [filteredEvents])

  const visibleMonths = useMemo(
    () => eventsByMonth.slice(0, monthLimit),
    [eventsByMonth, monthLimit])

  // Row components are memoised — these must keep a stable identity.
  const toggleExpand = useCallback((id: string) => {
    if (!editMode) setExpandedId(prev => prev === id ? null : id)
  }, [editMode])

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }, [])

  const currentIds = useMemo(() => (
    tab === 'personas'
      ? paginatedPersonas.map(n => n.data.id)
      : (tab === 'events' || tab === 'time') ? paginatedEvents.map(ev => ev.id) : []
  ), [tab, paginatedPersonas, paginatedEvents])

  const allSelected = currentIds.length > 0 && currentIds.every(id => selectedIds.has(id))
  const someSelected = currentIds.some(id => selectedIds.has(id))
  const toggleAll = useCallback(() => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      const isAll = currentIds.length > 0 && currentIds.every(id => next.has(id))
      if (isAll) currentIds.forEach(id => next.delete(id))
      else currentIds.forEach(id => next.add(id))
      return next
    })
  }, [currentIds])

  const handleDeleteSelected = async () => {
    if (!sudo) { toast(i18n.common.needSudo, 'destructive'); return }
    if (!selectedIds.size) { toast(L.noSelected, 'destructive'); return }
    setDeleteDialog({
      open: true,
      title: L.confirmDelete(selectedIds.size),
      onConfirm: async () => {
        let ok = 0
        if (tab === 'personas') { for (const uid of selectedIds) { try { await api.graph.deletePersona(uid); ok++ } catch {} } }
        else if (tab === 'events' || tab === 'time') { for (const id of selectedIds) { try { await api.events.delete(id); ok++ } catch {} } }
        setSelectedIds(new Set())
        toast(L.deletedOk(ok))
        loadData()
        refreshStats()
      },
    })
  }

  const handleEditPersonaSubmit = async (uid: string, data: Record<string, unknown>) => {
    if (!sudo) { toast(i18n.common.needSudo, 'destructive'); return }
    await api.graph.updatePersona(uid, data)
    toast(i18n.common.updateOk)
    loadData()
    setEditPersona(null)
  }

  const handleEditEventSubmit = async (id: string, data: EventFormData) => {
    if (!sudo) { toast(i18n.common.needSudo, 'destructive'); return }
    await api.events.update(id, {
      topic:             data.topic,
      summary:           data.summary,
      group_id:          data.group_id || null,
      start_time:        Math.floor(new Date(data.start_time).getTime() / 1000),
      end_time:          Math.floor(new Date(data.end_time).getTime() / 1000),
      salience:          data.salience,
      chat_content_tags: data.tags,
      participants:      data.participants,
      inherit_from:      data.inherit_from,
      is_locked:         data.is_locked,
      status:            data.status,
      confidence:        editEvent?.confidence ?? 0.8,
    })
    toast(i18n.common.updateOk)
    loadEvents()
    setEditEvent(null)
  }

  const handleLockToggle = useCallback(async (ev: api.ApiEvent) => {
    if (!sudo) { toast(i18n.common.needSudo, 'destructive'); return }
    try {
      const res = await api.events.update(ev.id, { is_locked: !ev.is_locked }) as any
      const updated = res.event || { ...ev, is_locked: !ev.is_locked }
      toast((updated.is_locked ? i18n.events.lock : i18n.events.unlock) + ' ' + i18n.common.success)
      setEventList(prev => prev.map(e => e.id === ev.id ? updated : e))
      refreshStats()
    } catch (e: unknown) {
      toast(i18n.common.updateFailed + '：' + (e as api.ApiError).body, 'destructive')
    }
  }, [sudo, toast, i18n, refreshStats])

  const handleDeletePersona = useCallback((id: string, label: string) => {
    if (!sudo) { toast(i18n.common.needSudo, 'destructive'); return }
    setDeleteDialog({
      open: true,
      title: i18n.graph.deleteConfirm.replace('{name}', label),
      onConfirm: async () => {
        try {
          await api.graph.deletePersona(id)
          toast(i18n.common.success)
          setExpandedId(null)
          loadData()
          refreshStats()
        } catch (e: unknown) {
          toast(i18n.common.deleteFailed + '：' + (e as api.ApiError).body, 'destructive')
        }
      },
    })
  }, [sudo, toast, i18n, loadData, refreshStats])

  const handleDeleteEvent = useCallback((ev: api.ApiEvent) => {
    if (!sudo) { toast(i18n.common.needSudo, 'destructive'); return }
    setDeleteDialog({
      open: true,
      title: i18n.events.deleteConfirm.replace('{name}', ev.topic || ev.content || ev.id),
      onConfirm: async () => {
        try {
          await api.events.delete(ev.id)
          toast(i18n.events.moveBinSuccess)
          setExpandedId(null)
          loadEvents()
          refreshStats()
        } catch (e: unknown) {
          toast(i18n.common.deleteFailed + '：' + (e as api.ApiError).body, 'destructive')
        }
      },
    })
  }, [sudo, toast, i18n, loadEvents, refreshStats])

  const handleArchiveEvent = useCallback(async (ev: api.ApiEvent) => {
    if (!sudo) { toast(i18n.common.needSudo, 'destructive'); return }
    try {
      await api.events.archive(ev.id)
      toast(i18n.events.archiveSuccess)
      setExpandedId(prev => prev === ev.id ? null : prev)
      loadEvents()
      refreshStats()
    } catch (e: any) {
      toast(e?.body || e?.message || i18n.common.updateFailed, 'destructive')
    }
  }, [sudo, toast, i18n, loadEvents, refreshStats])

  const goToGraph = useCallback((uid: string) => {
    setStored('em_focus_persona', uid, 'session'); router.push('/graph')
  }, [router])
  const goToEvents = useCallback((eventId: string) => {
    setStored('em_focus_event', eventId, 'session'); router.push('/events')
  }, [router])
  const handleTagClick = useCallback((t: string) => {
    setActiveTags(prev => {
      const next = new Set(prev)
      if (next.has(t)) next.delete(t); else next.add(t)
      return next
    })
  }, [])

  const actions = (
    <div className="flex items-center gap-2">
      <div className="relative hidden md:block">
        <Search className="text-muted-foreground pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2" />
        <Input
          className="h-8 w-48 pl-8 text-xs lg:w-64"
          placeholder={i18n.common.search + '…'}
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      <Button variant="outline" size="sm" className="h-8 gap-1.5 px-2" onClick={openArchiveBin}>
        <Archive className="size-3.5" />
        <span className="hidden sm:inline">{i18n.events.archivedBin}</span>
      </Button>

      <Button variant="outline" size="sm" className="h-8 gap-1.5 px-2" onClick={openBin}>
        <Trash2 className="size-3.5" />
        <span className="hidden sm:inline">{i18n.events.recycleBin}</span>
      </Button>

      {editMode && selectedIds.size > 0 && (
        <Button variant="destructive" size="sm" className="h-8" onClick={handleDeleteSelected}>
          <Trash2 className="mr-1.5 size-3.5" />
          <span className="hidden sm:inline">{L.deleteSelected}</span> ({selectedIds.size})
        </Button>
      )}

      {(tab === 'personas' || tab === 'events' || tab === 'time') && (
        <Button
          variant={editMode ? 'default' : 'outline'}
          size="sm"
          className="h-8 gap-1.5 px-2"
          onClick={() => setEditMode(v => !v)}
        >
          <Pencil className="size-3.5" />
          <span className="hidden sm:inline">{editMode ? L.exitEditMode : L.editMode}</span>
        </Button>
      )}
    </div>
  )

  const globalActions = (
    <RefreshButton onClick={loadData} loading={isRefreshing} />
  )

  const tableHeadCls = 'font-mono text-[10px] uppercase tracking-wider text-muted-foreground'

  return (
    <div className="flex h-full flex-col overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-500 ease-out fill-mode-both">
      <PageHeader
        variant="loom"
        loomIssue="ΒΙΒΛΙΟΘΗΚΗ"
          loomWindow={i18n.page.library.loomWindow}
        title={i18n.page.library.title}
        actions={actions}
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

      <div className="flex flex-1 flex-col overflow-hidden p-6 pt-2">
        <Tabs value={tab} onValueChange={t => { setEditMode(false); setTab(t) }} className="flex flex-1 flex-col overflow-hidden">
          <div className="mb-4 shrink-0">
            <TabsList>
              <TabsTrigger value="events" className="gap-2"><Activity className="size-3.5" />{i18n.library.tabs.events}</TabsTrigger>
              <TabsTrigger value="time" className="gap-2"><Clock className="size-3.5" />{i18n.library.tabs.time}</TabsTrigger>
              <TabsTrigger value="personas" className="gap-2"><Users className="size-3.5" />{i18n.library.tabs.personas}</TabsTrigger>
              <TabsTrigger value="groups" className="gap-2"><Building2 className="size-3.5" />{i18n.library.tabs.groups}</TabsTrigger>
            </TabsList>
          </div>

          {/* ── Events Tab ── */}
          <TabsContent value="events" className="flex-1 overflow-hidden flex flex-col">
            <ScrollArea className="flex-1">
              <div className="overflow-hidden border-y border-border/50">
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent border-b border-border/50">
                      {editMode && (
                        <TableHead className="w-8 pr-0" onClick={toggleAll}>
                          <Checkbox
                            checked={allSelected ? true : (someSelected ? 'indeterminate' : false)}
                            onCheckedChange={toggleAll}
                          />
                        </TableHead>
                      )}
                      <TableHead className="w-4" />
                      <TableHead className={tableHeadCls}>{i18n.events.topic}</TableHead>
                      <TableHead className={tableHeadCls}>{i18n.events.group}</TableHead>
                      <TableHead className={tableHeadCls}>{i18n.events.time}</TableHead>
                      <TableHead className={tableHeadCls}>{i18n.events.salience}</TableHead>
                      <TableHead className={tableHeadCls}>{i18n.events.tags}</TableHead>
                      {!editMode && <TableHead className={cn(tableHeadCls, 'text-right')}>{L.actionsHead}</TableHead>}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {paginatedEvents.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={editMode ? 7 : 8} className="text-muted-foreground text-center py-12 text-sm">
                          {i18n.common.noData}
                        </TableCell>
                      </TableRow>
                    ) : paginatedEvents.map(ev => (
                      <EventRow
                        key={ev.id}
                        ev={ev}
                        expanded={expandedId === ev.id}
                        editMode={editMode}
                        selected={selectedIds.has(ev.id)}
                        sudoMode={sudo}
                        activeTags={activeTags}
                        lang={lang}
                        onToggleExpand={toggleExpand}
                        onToggleSelect={toggleSelect}
                        onEdit={setEditEvent}
                        onDelete={handleDeleteEvent}
                        onLockToggle={handleLockToggle}
                        onArchive={handleArchiveEvent}
                        onGoToEvents={goToEvents}
                        onTagClick={handleTagClick}
                      />
                    ))}
                  </TableBody>
                </Table>
              </div>
            </ScrollArea>
            <PaginationFooter
              totalItems={filteredEvents.length}
              totalPages={totalEventPages}
              pageSize={pageSize}
              currentPage={currentPage}
              onPageChange={setCurrentPage}
              onPageSizeChange={setPageSize}
            />
          </TabsContent>

          {/* ── Time Tab ── */}
          <TabsContent value="time" className="flex-1 overflow-hidden">
            <ScrollArea className="h-full">
              <div className="flex flex-col gap-6 pb-6">
                <p className="text-muted-foreground text-sm">{i18n.library.time.description}</p>
                {visibleMonths.map(([month, evs]) => (
                  <div key={month} className="flex flex-col gap-2">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-semibold">{month}</span>
                      <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4">
                        {evs.length} {i18n.library.tabs.events}
                      </Badge>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {evs.slice(0, 50).map(ev => (
                        <Badge
                          key={ev.id}
                          variant={selectedIds.has(ev.id) ? 'default' : 'outline'}
                          className="cursor-pointer text-[10px] py-1 transition-colors hover:bg-accent"
                          onClick={() => editMode ? toggleSelect(ev.id) : goToEvents(ev.id)}
                        >
                          {ev.start.slice(5, 10)} {(ev.topic || ev.content)?.slice(0, 12) || ev.id.slice(0, 8)}
                        </Badge>
                      ))}
                      {evs.length > 50 && (
                        <Badge variant="outline" className="text-[10px]">+{evs.length - 50}</Badge>
                      )}
                    </div>
                  </div>
                ))}
                {eventsByMonth.length > visibleMonths.length && (
                  <Button
                    variant="outline" size="sm"
                    className="self-start h-7 text-xs"
                    onClick={() => setMonthLimit(n => n + MONTH_PAGE)}
                  >
                    {L.loadMoreMonths(eventsByMonth.length - visibleMonths.length)}
                  </Button>
                )}
              </div>
            </ScrollArea>
          </TabsContent>

          {/* ── Personas Tab ── */}
          <TabsContent value="personas" className="flex-1 overflow-hidden flex flex-col">
            <ScrollArea className="flex-1">
              <div className="overflow-hidden border-y border-border/50">
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent border-b border-border/50">
                      {editMode && (
                        <TableHead className="w-8 pr-0" onClick={toggleAll}>
                          <Checkbox
                            checked={allSelected ? true : (someSelected ? 'indeterminate' : false)}
                            onCheckedChange={toggleAll}
                          />
                        </TableHead>
                      )}
                      <TableHead className="w-4" />
                      <TableHead className={tableHeadCls}>{L.nameHead}</TableHead>
                      <TableHead className={tableHeadCls}>{i18n.graph.description}</TableHead>
                      <TableHead className={tableHeadCls}>{i18n.graph.inferredPersonality}</TableHead>
                      <TableHead className={tableHeadCls}>{i18n.graph.confidence}</TableHead>
                      <TableHead className={tableHeadCls}>{i18n.events.tags}</TableHead>
                      {!editMode && <TableHead className={cn(tableHeadCls, 'text-right')}>{L.actionsHead}</TableHead>}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {paginatedPersonas.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={editMode ? 7 : 8} className="text-muted-foreground text-center py-12 text-sm">
                          {i18n.library.personas.noPersonas}
                        </TableCell>
                      </TableRow>
                    ) : paginatedPersonas.map(n => (
                      <PersonaRow
                        key={n.data.id}
                        node={n}
                        expanded={expandedId === n.data.id}
                        editMode={editMode}
                        selected={selectedIds.has(n.data.id)}
                        sudoMode={sudo}
                        activeTags={activeTags}
                        onToggleExpand={toggleExpand}
                        onToggleSelect={toggleSelect}
                        onEdit={setEditPersona}
                        onDelete={handleDeletePersona}
                        onGoToGraph={goToGraph}
                        onTagClick={handleTagClick}
                      />
                    ))}
                  </TableBody>
                </Table>
              </div>
            </ScrollArea>
            <PaginationFooter
              totalItems={filteredPersonas.length}
              totalPages={totalPersonaPages}
              pageSize={pageSize}
              currentPage={currentPage}
              onPageChange={setCurrentPage}
              onPageSizeChange={setPageSize}
            />
          </TabsContent>

          {/* ── Groups Tab ── */}
          <TabsContent value="groups" className="flex-1 overflow-hidden flex flex-col">
            <ScrollArea className="flex-1">
              <div className="overflow-hidden border-y border-border/50">
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent border-b border-border/50">
                      <TableHead className="w-4" />
                      <TableHead className={tableHeadCls}>{i18n.library.groups.groupId}</TableHead>
                      <TableHead className={tableHeadCls}>{i18n.library.groups.events}</TableHead>
                      <TableHead className={tableHeadCls}>{i18n.library.groups.lastActive}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {paginatedGroups.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={4} className="text-muted-foreground text-center py-12 text-sm">
                          {i18n.library.groups.noGroups}
                        </TableCell>
                      </TableRow>
                    ) : paginatedGroups.map(g => (
                      <GroupRow
                        key={g.id}
                        group={g}
                        personas={personaList}
                        expanded={expandedId === g.id}
                        lang={lang}
                        onToggleExpand={toggleExpand}
                        onGoToEvents={id => { setTab('events'); setSearch(id) }}
                      />
                    ))}
                  </TableBody>
                </Table>
              </div>
            </ScrollArea>
            <PaginationFooter
              totalItems={filteredGroups.length}
              totalPages={totalGroupPages}
              pageSize={pageSize}
              currentPage={currentPage}
              onPageChange={setCurrentPage}
              onPageSizeChange={setPageSize}
            />
          </TabsContent>
        </Tabs>
      </div>

      <EditPersonaDialog
        open={!!editPersona} node={editPersona}
        onClose={() => setEditPersona(null)} onSubmit={handleEditPersonaSubmit}
      />
      <EditEventDialog
        open={!!editEvent} event={editEvent}
        onClose={() => setEditEvent(null)} onSubmit={handleEditEventSubmit}
        tagSuggestions={tagList.map(t => t.name)} events={eventList}
      />
      <RecycleBinDialog
        open={binOpen} items={binItems} loading={binLoading}
        onClose={() => setBinOpen(false)} onRestore={handleRestore}
        onClear={handleClearBin} sudoMode={sudo}
      />
      <ArchiveEventsDialog
        open={archiveBinOpen} items={archiveBinItems} loading={archiveBinLoading}
        onClose={() => setArchiveBinOpen(false)} onUnarchive={handleUnarchive}
        sudoMode={sudo}
      />

      <AlertDialog open={deleteDialog.open} onOpenChange={o => setDeleteDialog(prev => ({ ...prev, open: o }))}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{L.confirmDeleteTitle}</AlertDialogTitle>
            <AlertDialogDescription>{deleteDialog.title}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{L.cancel}</AlertDialogCancel>
            <AlertDialogAction
              onClick={deleteDialog.onConfirm}
              className={buttonVariants({ variant: 'destructive' })}
            >
              {L.delete}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

export default function LibraryPage() {
  return <LibraryContent />
}
