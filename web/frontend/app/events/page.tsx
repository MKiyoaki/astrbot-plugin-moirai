'use client'

import { useEffect, useState, useCallback, useRef, useMemo } from 'react'
import { ChevronLeft, Plus, Trash2, Archive, Search, X, MessageSquareOff } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { PageHeader } from '@/components/layout/page-header'
import { SpindleGrid } from '@/components/events/spindle-grid'
import { EventThread } from '@/components/events/event-thread'
import { DetailPanel } from '@/components/events/detail-panel'
import {
  CreateEventDialog, EditEventDialog, RecycleBinDialog, ArchiveEventsDialog, type EventFormData,
} from '@/components/events/event-dialogs'
import { RefreshButton } from '@/components/shared/refresh-button'
import { PageEmptyOverlay } from '@/components/shared/page-empty-overlay'
import { TimeGapSelector } from '@/components/shared/time-gap-selector'
import { FilterBar } from '@/components/shared/filter-bar'
import { useApp } from '@/lib/store'
import { getStored, removeStored } from '@/lib/safe-storage'
import { buildSpindleCards, eventGroupId } from '@/lib/events-aggregator'
import * as api from '@/lib/api'
import { DateRange } from 'react-day-picker'

// ── Page ───────────────────────────────────────────────────────────────────────

export default function EventsPage() {
  const appCtx = useApp()
  const { i18n } = appCtx
  // Destructure stable callbacks so loadEvents doesn't depend on the whole app object
  // (app object identity changes on every stats poll, which would re-trigger loadEvents)
  const { toast: appToast, setRawEvents, currentPersonaName, scopeMode } = appCtx
  const app = appCtx
  const personaFilter = scopeMode === 'single' ? (currentPersonaName ?? api.LEGACY_PERSONA_TOKEN) : null

  const [search, setSearch]             = useState('')
  const [timeGap, setTimeGap]           = useState(7200000) // Default 2h
  const [dateRange, setDateRange]       = useState<DateRange | undefined>()
  const [activeTags, setActiveTags]     = useState<Set<string>>(new Set())
  const [tagList, setTagList] = useState<{ name: string; count: number }[]>([])
  const [highlightIds, setHighlightIds]       = useState<Set<string>>(new Set())
  const [detailEvent, setDetailEvent]         = useState<api.ApiEvent | null>(null)
  const [isRefreshing, setIsRefreshing]       = useState(false)
  const [expandedGroupId, setExpandedGroupId] = useState<string | null>(null)

  // CRUD dialogs
  const [createOpen, setCreateOpen]           = useState(false)
  const [editEvent, setEditEvent]             = useState<api.ApiEvent | null>(null)
  const [binOpen, setBinOpen]                 = useState(false)
  const [binItems, setBinItems]               = useState<api.ApiEvent[]>([])
  const [binLoading, setBinLoading]           = useState(false)
  const [archiveBinOpen, setArchiveBinOpen]   = useState(false)
  const [archiveBinItems, setArchiveBinItems] = useState<api.ApiEvent[]>([])
  const [archiveBinLoading, setArchiveBinLoading] = useState(false)

  // ── Confirm dialog (replaces native window.confirm) ────────────────────────
  const [confirmDialog, setConfirmDialog] = useState<{
    title: string; description: string; onConfirm: () => void
  } | null>(null)

  const askConfirm = (title: string, description: string, onConfirm: () => void) => {
    setConfirmDialog({ title, description, onConfirm })
  }

  // ── Data loading ───────────────────────────────────────────────────────────

  const loadEvents = useCallback(async () => {
    setIsRefreshing(true)
    try {
      const data = await api.events.list(1000, personaFilter)
      setRawEvents(data.items)
    } catch {
      appToast(i18n.events.loadError, 'destructive')
    } finally {
      setTimeout(() => setIsRefreshing(false), 600)
    }
  }, [setRawEvents, appToast, i18n.events.loadError, personaFilter])

  useEffect(() => {
    loadEvents()
    api.tags.list().then(r => {
      setTagList(r.tags)
    })
  }, [loadEvents])

  // Restore focus from sessionStorage
  const hasHandledFocusRef = useRef(false)

  useEffect(() => {
    if (app.rawEvents.length > 0 && !hasHandledFocusRef.current) {
      const focusId    = getStored('em_focus_event', null, 'session')
      const highlightRaw = getStored('em_highlight_events', null, 'session')
      setTimeout(() => {
        if (focusId) {
          removeStored('em_focus_event', 'session')
          setHighlightIds(new Set([focusId]))
          const ev = app.rawEvents.find(e => e.id === focusId)
          if (ev) {
            setExpandedGroupId(eventGroupId(ev))
            setDetailEvent(ev)
          }
        }
        if (highlightRaw) {
          removeStored('em_highlight_events', 'session')
          try {
            const ids = JSON.parse(highlightRaw) as string[]
            setHighlightIds(new Set(ids))
            const ev = app.rawEvents.find(e => ids.includes(e.id))
            if (ev) {
              setExpandedGroupId(eventGroupId(ev))
              setDetailEvent(ev)
            }
          } catch {}
        }
      }, 0)
      hasHandledFocusRef.current = true
    }
  }, [app.rawEvents])

  // ── Filtering ──────────────────────────────────────────────────────────────

  const filtered = useMemo(() => {
    return app.rawEvents.filter(ev => {
      if (search) {
        const q = search.toLowerCase()
        const hit =
          (ev.content || '').toLowerCase().includes(q) ||
          (ev.topic || '').toLowerCase().includes(q) ||
          (ev.group || '').toLowerCase().includes(q) ||
          (ev.tags || []).some(t => t.toLowerCase().includes(q)) ||
          (ev.participants || []).some(p => p.toLowerCase().includes(q))
        if (!hit) return false
      }
      if (dateRange?.from) {
        const start = new Date(ev.start).getTime()
        const from = dateRange.from.getTime()
        const to = dateRange.to ? dateRange.to.getTime() + 86400000 : from + 86400000
        if (start < from || start > to) return false
      }
      if (activeTags.size > 0) {
        if (!(ev.tags ?? []).some(t => activeTags.has(t))) return false
      }
      return true
    })
  }, [app.rawEvents, search, dateRange, activeTags])

  const hasActiveFilters = search || activeTags.size > 0 || !!dateRange
  const spindles = useMemo(
    () => buildSpindleCards(app.rawEvents, i18n.events.privateChat),
    [app.rawEvents, i18n.events.privateChat]
  )
  const currentSpindle = useMemo(
    () => spindles.find(spindle => spindle.groupId === expandedGroupId) ?? null,
    [spindles, expandedGroupId]
  )
  const threadEvents = useMemo(() => {
    if (!expandedGroupId) return filtered
    return filtered
      .filter(ev => eventGroupId(ev) === expandedGroupId)
      .sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime())
  }, [filtered, expandedGroupId])

  const axisEvents = useMemo(() => {
    if (!detailEvent) return currentSpindle?.events ?? []
    return app.rawEvents
      .filter(e => eventGroupId(e) === eventGroupId(detailEvent))
      .sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime())
  }, [app.rawEvents, currentSpindle, detailEvent])

  // ── CRUD handlers ───────────────────────────────────────────────────────────

  const handleCreate = async (data: EventFormData) => {
    await api.events.create({
      ...data,
      start_time: Math.floor(new Date(data.start_time).getTime() / 1000),
      end_time:   Math.floor(new Date(data.end_time).getTime() / 1000),
      confidence: 0.9,
    })
    app.toast(i18n.events.createSuccess)
    setCreateOpen(false)
    loadEvents(); app.refreshStats()
  }

  const handleUpdate = async (id: string, data: EventFormData) => {
    await api.events.update(id, {
      ...data,
      start_time: Math.floor(new Date(data.start_time).getTime() / 1000),
      end_time:   Math.floor(new Date(data.end_time).getTime() / 1000),
      confidence: editEvent?.confidence ?? 0.8,
    })
    app.toast(i18n.common.updateOk)
    setEditEvent(null); loadEvents()
  }

  const handleDelete = (ev: api.ApiEvent) => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    askConfirm(
      i18n.common.delete,
      i18n.events.deleteConfirm.replace('{name}', ev.content || ev.topic || ev.id),
      async () => {
        try {
          await api.events.delete(ev.id)
          app.toast(i18n.events.moveBinSuccess)
          if (detailEvent?.id === ev.id) setDetailEvent(null)
          loadEvents(); app.refreshStats()
        } catch (e: any) {
          app.toast(e?.body || e?.message || i18n.common.deleteFailed, 'destructive')
        }
      }
    )
  }

  const handleLockToggle = async (ev: api.ApiEvent) => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    try {
      await api.events.update(ev.id, { is_locked: !ev.is_locked })
      app.toast((ev.is_locked ? i18n.events.unlock : i18n.events.lock) + ' ' + i18n.common.success)
      loadEvents(); app.refreshStats()
    } catch (e: any) {
      app.toast(i18n.common.updateFailed + '：' + (e?.body || e?.message), 'destructive')
    }
  }

  const handleArchive = async (ev: api.ApiEvent) => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    try {
      await api.events.archive(ev.id)
      app.toast(i18n.events.archiveSuccess)
      if (detailEvent?.id === ev.id) setDetailEvent(null)
      loadEvents()
    } catch (e: any) {
      app.toast(e?.body || e?.message || i18n.common.updateFailed, 'destructive')
    }
  }

  const handleReextract = (ev: api.ApiEvent) => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    if (ev.is_locked) { app.toast(i18n.events.reextractLocked, 'destructive'); return }
    askConfirm(
      i18n.events.reextractTitle,
      i18n.events.reextractConfirm,
      async () => {
        try {
          const result = await app.runTask(i18n.tasks.reextract, () => api.events.reextract(ev.id))
          setDetailEvent(result.event)
          await loadEvents()
          app.refreshStats()
        } catch {
          /* running / failure state surfaced by the TaskDock */
        }
      }
    )
  }

  const openBin = async () => {
    setBinOpen(true); setBinLoading(true)
    try { const d = await api.events.recycleBin(); setBinItems(d.items) }
    catch { app.toast(i18n.events.binLoadError, 'destructive') }
    finally { setBinLoading(false) }
  }

  const handleRestore = async (id: string) => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    try {
      await api.events.restore(id); app.toast(i18n.events.restoreSuccess)
      await loadEvents(); const d = await api.events.recycleBin(); setBinItems(d.items)
      app.refreshStats()
    } catch (e: any) { app.toast(e?.body || e?.message || i18n.common.updateFailed, 'destructive') }
  }

  const handleClearBin = () => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    askConfirm(
      i18n.common.delete,
      i18n.events.clearBinConfirm,
      async () => {
        try { await api.events.clearBin(); app.toast(i18n.events.binClearSuccess); setBinItems([]) }
        catch (e: any) { app.toast(e?.body || e?.message || i18n.common.deleteFailed, 'destructive') }
      }
    )
  }

  const openArchiveBin = async () => {
    setArchiveBinOpen(true); setArchiveBinLoading(true)
    try { const d = await api.events.listArchived(personaFilter); setArchiveBinItems(d.items) }
    catch { app.toast(i18n.events.archiveBinLoadError, 'destructive') }
    finally { setArchiveBinLoading(false) }
  }

  const handleUnarchive = async (id: string) => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    try {
      await api.events.unarchive(id); app.toast(i18n.events.unarchiveSuccess)
      await loadEvents(); const d = await api.events.listArchived(personaFilter); setArchiveBinItems(d.items)
      app.refreshStats()
    } catch (e: any) { app.toast(e?.body || e?.message || i18n.common.updateFailed, 'destructive') }
  }

  // ── Actions ─────────────────────────────────────────────────────────────────

  const listActions = (
    <div className="flex items-center gap-2">
      {expandedGroupId && (
        <Button
          variant="ghost"
          size="sm"
          className="h-7 gap-1.5 px-2"
          onClick={() => {
            setExpandedGroupId(null)
            setDetailEvent(null)
          }}
        >
          <ChevronLeft className="size-3.5" />
          <span className="hidden sm:inline text-xs">{i18n.events.backToSpindles}</span>
        </Button>
      )}
      <div className="relative hidden md:block">
        <Search className="text-muted-foreground pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2" />
        <Input
          className="h-7 w-36 pl-8 text-xs lg:w-48"
          placeholder={i18n.common.searchPlaceholder}
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      <TimeGapSelector value={timeGap} onChange={setTimeGap} />

      <div className="h-4 w-px bg-border mx-1 hidden sm:block" />

      <Button variant="outline" size="sm" className="h-7 gap-1.5 px-2" onClick={openArchiveBin}>
        <Archive className="size-3.5" />
        <span className="hidden md:inline text-xs">{i18n.events.archivedBin}</span>
      </Button>
      <Button variant="outline" size="sm" className="h-7 gap-1.5 px-2" onClick={openBin}>
        <Trash2 className="size-3.5" />
        <span className="hidden md:inline text-xs">{i18n.events.recycleBin}</span>
      </Button>
      <Button size="sm" onClick={() => setCreateOpen(true)} disabled={!app.sudo} className="h-7">
        <Plus className="mr-1 size-3.5" />
        <span className="hidden sm:inline">{i18n.common.create}</span>
      </Button>

      {hasActiveFilters && (
        <Button variant="ghost" size="sm" className="h-7 gap-1 px-2 text-xs text-muted-foreground"
          onClick={() => { setSearch(''); setActiveTags(new Set()); setDateRange(undefined) }}>
          <X className="size-3" />{i18n.common.clearHighlight}
        </Button>
      )}
    </div>
  )

  const globalActions = (
    <RefreshButton onClick={loadEvents} loading={isRefreshing} />
  )

  return (
    <div className="flex h-svh flex-col overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-500 ease-out fill-mode-both">
      <PageHeader
        variant="loom"
        title={currentSpindle?.name ?? i18n.page.events.title}
        loomIssue="ΑΡΓΑΛΕΙΟΣ"
        loomWindow={i18n.page.events.loomWindow}
        loomLegend={expandedGroupId ? <span>{i18n.events.unspooled}</span> : undefined}
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

      {/* ── Main area ── */}
      {app.rawEvents.length === 0 ? (
        <PageEmptyOverlay
          icon={MessageSquareOff}
          title={i18n.page.events.noEvents}
          description={i18n.page.events.description}
          action={app.sudo && (
            <Button variant="outline" size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="mr-1.5 size-3.5" />{i18n.common.create}
            </Button>
          )}
        />
      ) : filtered.length === 0 ? (
        <PageEmptyOverlay
          icon={Search}
          title={i18n.page.events.noResults}
          action={
            <Button variant="ghost" size="sm" className="mt-2 text-xs"
              onClick={() => { setSearch(''); setDateRange(undefined); setActiveTags(new Set()) }}>
              {i18n.common.clearHighlight}
            </Button>
          }
        />
      ) : (
      <div className="flex flex-1 overflow-hidden" data-testid="loom-layout">
        {!expandedGroupId ? (
          <SpindleGrid
            spindles={spindles}
            search={search}
            activeTags={activeTags}
            dateRange={dateRange}
            onOpen={groupId => {
              setExpandedGroupId(groupId)
              setDetailEvent(null)
            }}
          />
        ) : (
          <>
            <div className="flex flex-1 flex-col overflow-hidden">
              <EventThread
                events={threadEvents}
                timeGap={timeGap}
                highlightIds={highlightIds}
                onEventClick={setDetailEvent}
                selectedEventId={detailEvent?.id || null}
                onSelectionChange={id => { if (!id) setDetailEvent(null) }}
                onEdit={ev => { if (app.sudo) setEditEvent(ev); else app.toast(i18n.common.needSudo, 'destructive') }}
                onDelete={handleDelete}
                onArchive={handleArchive}
                accent={currentSpindle?.accent ?? 'var(--primary)'}
              />
            </div>

            <DetailPanel
              focusedEvent={detailEvent}
              axisEvents={axisEvents}
              allEvents={currentSpindle?.events ?? threadEvents}
              onClose={() => setDetailEvent(null)}
              onEdit={ev => { if (app.sudo) setEditEvent(ev); else app.toast(i18n.common.needSudo, 'destructive') }}
              onDelete={handleDelete}
              onLockToggle={handleLockToggle}
              onArchive={handleArchive}
              onReextract={handleReextract}
              onSelect={setDetailEvent}
            />
          </>
        )}
      </div>
      )}

      <CreateEventDialog open={createOpen} onClose={() => setCreateOpen(false)}
        onSubmit={handleCreate} tagSuggestions={tagList.map(t => t.name)} events={app.rawEvents} />
      <EditEventDialog open={!!editEvent} event={editEvent} onClose={() => setEditEvent(null)}
        onSubmit={handleUpdate} tagSuggestions={tagList.map(t => t.name)} events={app.rawEvents} />
      <RecycleBinDialog open={binOpen} items={binItems} loading={binLoading}
        onClose={() => setBinOpen(false)} onRestore={handleRestore} onClear={handleClearBin} sudoMode={app.sudo} />
      <ArchiveEventsDialog open={archiveBinOpen} items={archiveBinItems} loading={archiveBinLoading}
        onClose={() => setArchiveBinOpen(false)} onUnarchive={handleUnarchive} sudoMode={app.sudo} />

      {/* Confirm dialog — replaces native window.confirm() */}
      <AlertDialog open={!!confirmDialog} onOpenChange={v => { if (!v) setConfirmDialog(null) }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{confirmDialog?.title}</AlertDialogTitle>
            <AlertDialogDescription>{confirmDialog?.description}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{i18n.common.cancel}</AlertDialogCancel>
            <AlertDialogAction onClick={() => { confirmDialog?.onConfirm(); setConfirmDialog(null) }}>
              {i18n.common.confirm}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
