'use client'

import { useEffect, useState, useCallback, useRef, useMemo } from 'react'
import { Plus, RefreshCw, Trash2, Search, Info } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Slider } from '@/components/ui/slider'
import { Separator } from '@/components/ui/separator'
import { PageHeader } from '@/components/layout/page-header'
import { EventTimeline } from '@/components/events/event-timeline'
import { FilterBar } from '@/components/shared/filter-bar'
import {
  CreateEventDialog, EditEventDialog, RecycleBinDialog, EventDetailCard,
  type EventFormData,
} from '@/components/events/event-dialogs'
import { useApp } from '@/lib/store'
import * as api from '@/lib/api'
import { cn } from '@/lib/utils'

import { DateRange } from 'react-day-picker'

const GAP_OPTIONS = [
  { label: '30m', value: 1800000 },
  { label: '1h', value: 3600000 },
  { label: '2h', value: 7200000 },
  { label: '4h', value: 14400000 },
  { label: '8h', value: 28800000 },
  { label: '24h', value: 86400000 },
  { label: '7d', value: 604800000 },
]

export default function EventsPage() {
  const app = useApp()
  const { i18n } = app
  const [search, setSearch] = useState('')
  const [timeGap, setTimeGap] = useState(7200000)
  const [dateRange, setDateRange] = useState<DateRange | undefined>()
  const [activeTags, setActiveTags] = useState<Set<string>>(new Set())
  const [highlightIds, setHighlightIds] = useState<Set<string>>(new Set())
  const [detailEvent, setDetailEvent] = useState<api.ApiEvent | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [editEvent, setEditEvent] = useState<api.ApiEvent | null>(null)
  const [binOpen, setBinOpen] = useState(false)
  const [binItems, setBinItems] = useState<(api.ApiEvent & { deleted_at?: string })[]>([])
  const [binLoading, setBinLoading] = useState(false)
  const [tagSuggestions, setTagSuggestions] = useState<string[]>([])
  const [tagList, setTagList] = useState<{ name: string; count: number }[]>([])

  const loadEvents = useCallback(async () => {
    setIsRefreshing(true)
    try {
      const data = await api.events.list(1000)
      app.setRawEvents(data.items)
    } catch {
      app.toast(i18n.events.loadError, 'destructive')
    } finally {
      setTimeout(() => setIsRefreshing(false), 600)
    }
  }, [app.setRawEvents, app.toast])

  useEffect(() => {
    loadEvents()
    api.tags.list().then(r => {
      setTagList(r.tags)
      setTagSuggestions(r.tags.map(t => t.name))
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const hasHandledFocusRef = useRef(false)
  useEffect(() => {
    if (app.rawEvents.length > 0 && !hasHandledFocusRef.current) {
      const focusId = sessionStorage.getItem('em_focus_event')
      const highlightRaw = sessionStorage.getItem('em_highlight_events')
      
      setTimeout(() => {
        if (focusId) {
          sessionStorage.removeItem('em_focus_event')
          setHighlightIds(new Set([focusId]))
          const ev = app.rawEvents.find(e => e.id === focusId)
          if (ev) setDetailEvent(ev)
        }
        if (highlightRaw) {
          sessionStorage.removeItem('em_highlight_events')
          try { setHighlightIds(new Set(JSON.parse(highlightRaw))) } catch {}
        }
      }, 0)
      hasHandledFocusRef.current = true
    }
  }, [app.rawEvents])

  const filtered = useMemo(() => {
    return app.rawEvents.filter(ev => {
      if (search) {
        const q = search.toLowerCase()
        const matchSearch = (
          (ev.content || '').toLowerCase().includes(q) ||
          (ev.topic || '').toLowerCase().includes(q) ||
          (ev.group || '').toLowerCase().includes(q) ||
          (ev.tags || []).some(t => t.toLowerCase().includes(q)) ||
          (ev.participants || []).some(p => p.toLowerCase().includes(q))
        )
        if (!matchSearch) return false
      }

      if (dateRange?.from) {
        const start = new Date(ev.start).getTime()
        if (start < dateRange.from.getTime()) return false
        if (dateRange.to && start > dateRange.to.getTime() + 86400000) return false
      }

      if (activeTags.size > 0) {
        if (!(ev.tags ?? []).some(t => activeTags.has(t))) return false
      }

      return true
    })
  }, [app.rawEvents, search, dateRange, activeTags])

  const handleDelete = async (ev: api.ApiEvent) => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    if (!confirm(i18n.events.deleteConfirm.replace('{name}', ev.content || ev.topic || ev.id))) return
    try {
      await api.events.delete(ev.id)
      setDetailEvent(null)
      app.toast(i18n.events.moveBinSuccess)
      await loadEvents()
    } catch (e: unknown) {
      app.toast(i18n.events.deleteFailed + '：' + (e as api.ApiError).body, 'destructive')
    }
  }

  const handleCreate = async (data: EventFormData) => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    const body = {
      topic:             data.topic,
      group_id:          data.group_id || null,
      start_time:        Math.floor(new Date(data.start_time).getTime() / 1000),
      end_time:          Math.floor(new Date(data.end_time).getTime() / 1000),
      salience:          data.salience,
      chat_content_tags: data.tags,
      participants:      data.participants,
      inherit_from:      data.inherit_from,
    }
    await api.events.create(body)
    app.toast(i18n.events.createSuccess)
    await loadEvents()
    await app.refreshStats()
  }

  const handleUpdate = async (id: string, data: EventFormData) => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    const body = {
      topic:             data.topic,
      group_id:          data.group_id || null,
      start_time:        Math.floor(new Date(data.start_time).getTime() / 1000),
      end_time:          Math.floor(new Date(data.end_time).getTime() / 1000),
      salience:          data.salience,
      chat_content_tags: data.tags,
      participants:      data.participants,
      inherit_from:      data.inherit_from,
      is_locked:         data.is_locked,
    }
    await api.events.update(id, body)
    app.toast(i18n.common.updateOk)
    setDetailEvent(null)
    await loadEvents()
  }

  const openBin = async () => {
    setBinOpen(true)
    setBinLoading(true)
    try {
      const d = await api.events.recycleBin()
      setBinItems(d.items)
    } catch { app.toast(i18n.events.binLoadError, 'destructive') }
    finally { setBinLoading(false) }
  }

  const handleRestore = async (id: string) => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    await api.events.restore(id)
    app.toast(i18n.events.restoreSuccess)
    await loadEvents()
    const d = await api.events.recycleBin()
    setBinItems(d.items)
  }

  const handleClearBin = async () => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    if (!confirm(i18n.events.clearBinConfirm)) return
    await api.events.clearBin()
    app.toast(i18n.events.binClearSuccess)
    setBinItems([])
  }

  const actions = (
    <div className="flex items-center gap-2">
      <div className="relative">
        <Search className="text-muted-foreground pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2" />
        <Input
          className="h-8 w-48 pl-8 text-xs sm:w-64"
          placeholder={i18n.events.search}
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>
      <Button size="sm" onClick={() => setCreateOpen(true)} disabled={!app.sudo} className="h-8">
        <Plus className="mr-1.5 size-3.5" />{i18n.common.create}
      </Button>
      <Button variant="outline" size="icon" onClick={loadEvents} title={i18n.common.refresh} className="h-8 w-8">
        <RefreshCw className={cn("size-3.5 transition-transform duration-500", isRefreshing && "animate-spin")} />
      </Button>
    </div>
  )

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <PageHeader
        title={i18n.page.events.title}
        description={i18n.page.events.description}
        actions={actions}
      />

      {/* Full-width Filter Bar */}
      <FilterBar
        tags={tagList}
        activeTags={activeTags}
        onTagsChange={setActiveTags}
        dateRange={dateRange}
        onDateRangeChange={setDateRange}
      />

      <div className="flex flex-1 overflow-hidden relative">
        {/* Main Timeline View */}
        <div className="flex flex-1 flex-col overflow-hidden">
          <EventTimeline
            events={filtered}
            timeGap={timeGap}
            highlightIds={highlightIds}
            onEventClick={setDetailEvent}
            selectedEventId={detailEvent?.id || null}
            onSelectionChange={(id) => {
              if (!id) setDetailEvent(null);
            }}
            onEdit={ev => { if (app.sudo) setEditEvent(ev); else app.toast(i18n.common.needSudo, 'destructive') }}
            onDelete={handleDelete}
          />
        </div>

        {/* Permanent Control & Info Sidebar */}
        <aside className="w-80 flex flex-col border-l bg-muted/5">
          <div className="p-4 space-y-6">
            {/* Timeline Controls */}
            <div className="space-y-3">
              <div className="flex items-center justify-between text-[11px] text-muted-foreground uppercase font-bold tracking-tight px-1">
                <span>{i18n.events.threadScale}</span>
                <span className="text-primary">{GAP_OPTIONS.find(o => o.value === timeGap)?.label}</span>
              </div>
              <Slider
                value={[GAP_OPTIONS.findIndex(o => o.value === timeGap)]}
                min={0}
                max={GAP_OPTIONS.length - 1}
                step={1}
                onValueChange={([val]) => setTimeGap(GAP_OPTIONS[val].value)}
                className="py-1"
              />
              <Button variant="outline" size="sm" className="w-full h-8 text-xs" onClick={openBin}>
                <Trash2 className="mr-1.5 size-3.5" />{i18n.events.recycleBin}
              </Button>
            </div>

            <Separator />

            {/* Event Detail / Selection View */}
            <div className="flex-1">
              {detailEvent ? (
                <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="font-semibold text-sm">{i18n.events.detailTitle}</h3>
                    <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setDetailEvent(null)}>✕</Button>
                  </div>
                  <EventDetailCard
                    event={detailEvent}
                    onEdit={ev => setEditEvent(ev)}
                    onDelete={handleDelete}
                    sudoMode={app.sudo}
                  />
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-12 px-6 text-center text-muted-foreground animate-in fade-in duration-500">
                  <div className="bg-muted rounded-full p-4 mb-4">
                    <Info className="size-8 opacity-40" />
                  </div>
                  <h3 className="font-medium text-sm mb-1">{i18n.events.detailTitle}</h3>
                  <p className="text-xs leading-relaxed opacity-60">
                    {i18n.events.selectEventHint}
                  </p>
                </div>
              )}
            </div>
          </div>
        </aside>
      </div>

      <CreateEventDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSubmit={handleCreate}
        tagSuggestions={tagSuggestions}
        events={app.rawEvents}
      />
      <EditEventDialog
        open={!!editEvent}
        event={editEvent}
        onClose={() => setEditEvent(null)}
        onSubmit={handleUpdate}
        tagSuggestions={tagSuggestions}
        events={app.rawEvents}
      />
      <RecycleBinDialog
        open={binOpen}
        items={binItems}
        loading={binLoading}
        onClose={() => setBinOpen(false)}
        onRestore={handleRestore}
        onClear={handleClearBin}
        sudoMode={app.sudo}
      />
    </div>
  )
}
