'use client'

import { useEffect, useState, useCallback, SetStateAction, useRef } from 'react'
import { Plus, RefreshCw, Trash2, CircleMinus, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Slider } from '@/components/ui/slider'
import { PageHeader } from '@/components/layout/page-header'
import { EventTimeline } from '@/components/events/event-timeline'
import {
  CreateEventDialog, EditEventDialog, RecycleBinDialog, EventDetailCard,
  type EventFormData,
} from '@/components/events/event-dialogs'
import { useApp } from '@/lib/store'
import * as api from '@/lib/api'
import { i18n } from '@/lib/i18n'

import { DateRange } from 'react-day-picker'
import { DateRangePicker } from '@/components/shared/date-range-picker'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

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
  const [search, setSearch] = useState('')
  const [timeGap, setTimeGap] = useState(7200000)
  const [dateRange, setDateRange] = useState<DateRange | undefined>()
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [highlightIds, setHighlightIds] = useState<Set<string>>(new Set())
  const [detailEvent, setDetailEvent] = useState<api.ApiEvent | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [editEvent, setEditEvent] = useState<api.ApiEvent | null>(null)
  const [binOpen, setBinOpen] = useState(false)
  const [binItems, setBinItems] = useState<(api.ApiEvent & { deleted_at?: string })[]>([])
  const [binLoading, setBinLoading] = useState(false)
  const [tagSuggestions, setTagSuggestions] = useState<string[]>([])
  const [tagList, setTagList] = useState<{ name: string; count: number }[]>([])

  const loadEvents = useCallback(async () => {
    try {
      const data = await api.events.list(1000)
      app.setRawEvents(data.items)
    } catch {
      app.toast(i18n.events.loadError, 'destructive')
    }
  }, [app])

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

  const filtered = app.rawEvents.filter(ev => {
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

    return true
  })

  const handleDelete = async (ev: api.ApiEvent) => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    if (!confirm(i18n.events.deleteConfirm.replace('{name}', ev.content || ev.topic || ev.id))) return
    try {
      await api.events.delete(ev.id)
      setDetailEvent(null)
      app.toast('事件已移入回收站')
      await loadEvents()
    } catch (e: unknown) {
      app.toast('删除失败：' + (e as api.ApiError).body, 'destructive')
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
    app.toast('事件已创建')
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

  const handleDeleteSelected = async () => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    if (!selectedIds.size) { app.toast('未选择任何事件', 'destructive'); return }
    if (!confirm(i18n.events.deleteSelectedConfirm.replace('{count}', selectedIds.size.toString()))) return
    let ok = 0
    for (const id of selectedIds) {
      try { await api.events.delete(id); ok++ } catch {}
    }
    setSelectedIds(new Set())
    app.toast(`已删除 ${ok} 条事件`)
    await loadEvents()
  }

  const openBin = async () => {
    setBinOpen(true)
    setBinLoading(true)
    try {
      const d = await api.events.recycleBin()
      setBinItems(d.items)
    } catch { app.toast('回收站加载失败', 'destructive') }
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
    app.toast('回收站已清空')
    setBinItems([])
  }

  const actions = (
    <div className="flex items-center gap-2">
      <div className="relative">
        <Search className="text-muted-foreground pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2" />
        <Input
          className="h-7 w-48 pl-7 text-xs"
          placeholder={i18n.events.search}
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>
      <Button variant="ghost" size="sm" onClick={() => setCreateOpen(true)} disabled={!app.sudo}>
        <Plus className="mr-1.5 size-3.5" />{i18n.common.create}
      </Button>
      <Button variant="ghost" size="icon" onClick={loadEvents} title={i18n.common.refresh}>
        <RefreshCw className="size-4" />
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

      {/* Sub-header for page-specific controls */}
      <div className="flex items-center justify-between border-b bg-muted/5 px-6 py-2">
        <div className="flex items-center gap-4">
          <div className="flex w-48 flex-col gap-1.5 px-2">
            <div className="flex items-center justify-between text-[10px] text-muted-foreground uppercase font-bold tracking-tight">
              <span>时间跨度 (缩放)</span>
              <span>{GAP_OPTIONS.find(o => o.value === timeGap)?.label}</span>
            </div>
            <Slider
              value={[GAP_OPTIONS.findIndex(o => o.value === timeGap)]}
              min={0}
              max={GAP_OPTIONS.length - 1}
              step={1}
              onValueChange={([val]) => setTimeGap(GAP_OPTIONS[val].value)}
              className="py-1"
            />
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <Button variant="outline" size="sm" className="h-7 px-2 text-xs" onClick={openBin}>
            <Trash2 className="mr-1.5 size-3.5" />{i18n.events.recycleBin}
          </Button>
          <Button 
            variant="outline" 
            size="sm" 
            className="h-7 px-2 text-xs text-destructive hover:text-destructive" 
            onClick={handleDeleteSelected}
            disabled={selectedIds.size === 0}
          >
            <CircleMinus className="mr-1.5 size-3.5" />{i18n.events.deleteSelected} ({selectedIds.size})
          </Button>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        <div className="flex flex-1 flex-col overflow-hidden">
          <EventTimeline
            events={filtered}
            timeGap={timeGap}
            dateRange={dateRange}
            onDateRangeChange={setDateRange}
            highlightIds={highlightIds}
            tagList={tagList}
            onEventClick={setDetailEvent}
            onEdit={ev => { if (app.sudo) setEditEvent(ev); else app.toast(i18n.common.needSudo, 'destructive') }}
            onDelete={handleDelete}
          />
        </div>

        {detailEvent && (
          <div className="bg-card ring-foreground/10 flex h-full w-72 shrink-0 flex-col gap-3 overflow-y-auto border-l p-4 ring-1">
            <div className="flex items-center justify-between">
              <h3 className="font-medium text-sm">{i18n.events.detailTitle}</h3>
              <Button variant="ghost" size="icon" onClick={() => setDetailEvent(null)}>✕</Button>
            </div>
            <EventDetailCard
              event={detailEvent}
              onEdit={ev => setEditEvent(ev)}
              onDelete={handleDelete}
              sudoMode={app.sudo}
            />
          </div>
        )}
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
