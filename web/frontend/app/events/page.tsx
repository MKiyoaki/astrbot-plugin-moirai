'use client'

import { useEffect, useState, useCallback } from 'react'
import { Plus, RefreshCw, Trash2, CircleMinus } from 'lucide-react'
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
import { cn } from '@/lib/utils'

export default function EventsPage() {
  const app = useApp()
  const [search, setSearch] = useState('')
  const [density, setDensity] = useState(200)
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
      const data = await api.events.list(500)
      app.setRawEvents(data.items)
    } catch {
      app.toast('事件流加载失败', 'destructive')
    }
  }, [app])

  useEffect(() => {
    loadEvents().then(() => {
      const focusId = sessionStorage.getItem('em_focus_event')
      if (focusId) {
        sessionStorage.removeItem('em_focus_event')
        setHighlightIds(new Set([focusId]))
        const ev = app.rawEvents.find(e => e.id === focusId)
        if (ev) setDetailEvent(ev)
      }
      const highlightRaw = sessionStorage.getItem('em_highlight_events')
      if (highlightRaw) {
        sessionStorage.removeItem('em_highlight_events')
        try { setHighlightIds(new Set(JSON.parse(highlightRaw))) } catch {}
      }
    })
    api.tags.list().then(r => {
      setTagList(r.tags)
      setTagSuggestions(r.tags.map(t => t.name))
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const filtered = app.rawEvents.filter(ev => {
    if (!search) return true
    const q = search.toLowerCase()
    return (
      (ev.content || '').toLowerCase().includes(q) ||
      (ev.topic || '').toLowerCase().includes(q) ||
      (ev.group || '').toLowerCase().includes(q) ||
      (ev.tags || []).some(t => t.toLowerCase().includes(q)) ||
      (ev.participants || []).some(p => p.toLowerCase().includes(q))
    )
  })

  const handleDelete = async (ev: api.ApiEvent) => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    if (!confirm(`确认删除事件「${ev.content}」？将移入回收站。`)) return
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
    }
    await api.events.update(id, body)
    app.toast('事件已更新')
    setDetailEvent(null)
    await loadEvents()
  }

  const handleDeleteSelected = async () => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    if (!selectedIds.size) { app.toast('未选择任何事件', 'destructive'); return }
    if (!confirm(`确认删除选中的 ${selectedIds.size} 条事件？`)) return
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
    app.toast('事件已还原')
    await loadEvents()
    const d = await api.events.recycleBin()
    setBinItems(d.items)
  }

  const handleClearBin = async () => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    if (!confirm('确认清空回收站？此操作不可撤销。')) return
    await api.events.clearBin()
    app.toast('回收站已清空')
    setBinItems([])
  }

  const toggleSelect = (id: string) => {
    const next = new Set(selectedIds)
    if (next.has(id)) next.delete(id); else next.add(id)
    setSelectedIds(next)
  }

  const actions = (
    <div className="flex flex-wrap items-center gap-2">
      {/* Search */}
      <div className="relative">
        <Input
          className="h-7 w-48 pl-7 text-xs"
          placeholder={i18n.events.search}
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <span className="text-muted-foreground pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-xs">🔍</span>
      </div>

      {/* Density */}
      <div className="flex items-center gap-2">
        <span className="text-muted-foreground text-xs">{i18n.events.density}</span>
        <div className="w-24">
          <Slider
            value={[density]}
            onValueChange={v => setDensity(Array.isArray(v) ? v[0] : v)}
            min={20} max={500} step={10}
          />
        </div>
        <span className="text-muted-foreground w-8 text-xs">{density}</span>
      </div>

      {/* Actions */}
      <Button variant="ghost" size="icon-sm" onClick={openBin} title={i18n.events.recycleBin}>
        <Trash2 />
      </Button>
      <Button variant="ghost" size="icon-sm" onClick={handleDeleteSelected} title={i18n.events.deleteSelected}>
        <CircleMinus />
      </Button>
      <Button size="sm" onClick={() => setCreateOpen(true)} disabled={!app.sudo}>
        <Plus className="mr-1 size-3.5" />{i18n.common.create}
      </Button>
      <Button variant="ghost" size="icon-sm" onClick={loadEvents} title={i18n.common.refresh}>
        <RefreshCw />
      </Button>
    </div>
  )

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <PageHeader
        title={i18n.page.events.title}
        description={i18n.page.events.description}
        actions={actions}
      />

      <div className="flex flex-1 overflow-hidden">
        {/* Main content */}
        <div className="flex flex-1 flex-col overflow-hidden">
          <EventTimeline
            events={filtered}
            maxCount={density}
            highlightIds={highlightIds}
            tagList={tagList}
            onEventClick={setDetailEvent}
            onEdit={ev => { if (app.sudo) setEditEvent(ev); else app.toast(i18n.common.needSudo, 'destructive') }}
            onDelete={handleDelete}
          />
        </div>

        {/* Detail side panel */}
        {detailEvent && (
          <div className="bg-card ring-foreground/10 flex h-full w-72 shrink-0 flex-col gap-3 overflow-y-auto border-l p-4 ring-1">
            <div className="flex items-center justify-between">
              <h3 className="font-medium">{i18n.events.detailTitle}</h3>
              <Button variant="ghost" size="icon-xs" onClick={() => setDetailEvent(null)}>✕</Button>
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
