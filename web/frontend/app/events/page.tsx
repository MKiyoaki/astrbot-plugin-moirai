'use client'

import { useEffect, useState, useCallback, useRef, useMemo } from 'react'
import { Plus, Trash2, Search, Info, SlidersHorizontal, X, MessageSquareOff } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Slider } from '@/components/ui/slider'
import { Separator } from '@/components/ui/separator'
import { ScrollArea } from '@/components/ui/scroll-area'
import { PageHeader } from '@/components/layout/page-header'
import { EventTimeline } from '@/components/events/event-timeline'
import { FilterBar } from '@/components/shared/filter-bar'
import {
  CreateEventDialog, EditEventDialog, RecycleBinDialog, EventDetailCard,
  type EventFormData,
} from '@/components/events/event-dialogs'
import {
  Sheet, SheetContent, SheetHeader, SheetTitle,
} from '@/components/ui/sheet'
import {
  Popover, PopoverTrigger, PopoverContent,
} from '@/components/ui/popover'
import { RefreshButton } from '@/components/shared/refresh-button'
import { EmptyState } from '@/components/shared/empty-state'
import { useApp } from '@/lib/store'
import { getStored, removeStored } from '@/lib/safe-storage'
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
  const focusedCardRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!detailEvent) return
    const id = setTimeout(() => {
      focusedCardRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    }, 350)
    return () => clearTimeout(id)
  }, [detailEvent?.id])

  useEffect(() => {
    if (app.rawEvents.length > 0 && !hasHandledFocusRef.current) {
      const focusId = getStored('em_focus_event', null, 'session')
      const highlightRaw = getStored('em_highlight_events', null, 'session')
      
      setTimeout(() => {
        if (focusId) {
          removeStored('em_focus_event', 'session')
          setHighlightIds(new Set([focusId]))
          const ev = app.rawEvents.find(e => e.id === focusId)
          if (ev) setDetailEvent(ev)
        }
        if (highlightRaw) {
          removeStored('em_highlight_events', 'session')
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
      summary:           data.summary,
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
    }
    await api.events.update(id, body)
    app.toast(i18n.common.updateOk)
    setDetailEvent(null)
    await loadEvents()
  }

  const handleLockToggle = async (ev: api.ApiEvent) => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    try {
      const res = await api.events.update(ev.id, { is_locked: !ev.is_locked }) as any
      const updatedEvent = res.event || ev
      
      app.toast((updatedEvent.is_locked ? i18n.events.lock : i18n.events.unlock) + ' ' + i18n.common.success)
      
      // Update local state with the actual data from server
      if (detailEvent?.id === ev.id) {
        setDetailEvent(updatedEvent)
      }
      
      // Update the main list immediately without waiting for full reload
      app.setRawEvents(app.rawEvents.map(e => e.id === ev.id ? updatedEvent : e))
      
    } catch (e: unknown) {
      app.toast(i18n.common.updateFailed + '：' + (e as api.ApiError).body, 'destructive')
    }
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
    try {
      await api.events.restore(id)
      app.toast(i18n.events.restoreSuccess)
      await loadEvents()
      const d = await api.events.recycleBin()
      setBinItems(d.items)
      app.refreshStats()
    } catch (e: any) {
      const msg = e?.body || e?.message || i18n.common.updateFailed
      app.toast(msg, 'destructive')
    }
  }

  const handleClearBin = async () => {
    if (!app.sudo) { app.toast(i18n.common.needSudo, 'destructive'); return }
    if (!confirm(i18n.events.clearBinConfirm)) return
    try {
      await api.events.clearBin()
      app.toast(i18n.events.binClearSuccess)
      setBinItems([])
    } catch (e: any) {
      const msg = e?.body || e?.message || i18n.common.deleteFailed
      app.toast(msg, 'destructive')
    }
  }

  const actions = (
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

      <Popover>
        <PopoverTrigger asChild>
          <Button variant="outline" size="sm" className="h-8 gap-1.5 px-2">
            <SlidersHorizontal className="size-3.5" />
            <span className="hidden sm:inline">{GAP_OPTIONS.find(o => o.value === timeGap)?.label}</span>
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-60 p-4" align="end">
          <div className="space-y-3">
            <div className="flex items-center justify-between text-[11px] text-muted-foreground uppercase font-bold tracking-tight">
              <span>{i18n.events.threadScale}</span>
              <span className="text-primary">{GAP_OPTIONS.find(o => o.value === timeGap)?.label}</span>
            </div>
            <Slider
              value={[GAP_OPTIONS.findIndex(o => o.value === timeGap)]}
              min={0}
              max={GAP_OPTIONS.length - 1}
              step={1}
              onValueChange={([val]) => setTimeGap(GAP_OPTIONS[val].value)}
            />
          </div>
        </PopoverContent>
      </Popover>

      <Button variant="outline" size="sm" className="h-8 gap-1.5 px-2" onClick={openBin}>
        <Trash2 className="size-3.5" />
        <span className="hidden sm:inline">{i18n.events.recycleBin}</span>
      </Button>

      <Button size="sm" onClick={() => setCreateOpen(true)} disabled={!app.sudo} className="h-8">
        <Plus className="mr-1.5 size-3.5" />{i18n.common.create}
      </Button>
    </div>
  )

  const globalActions = (
    <RefreshButton 
      onClick={loadEvents} 
      loading={isRefreshing} 
    />
  )

  return (
    <div className="flex h-svh flex-col overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-500 ease-out fill-mode-both">
      <PageHeader
        title={i18n.page.events.title}
        description={i18n.page.events.description}
        actions={actions}
        globalActions={globalActions}
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
        {/* Main Timeline View - Always full width */}
        <div className="flex flex-1 flex-col overflow-hidden relative">
          {app.rawEvents.length === 0 ? (
            <EmptyState
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
            <div className="flex flex-1 flex-col items-center justify-center p-8 text-center animate-in fade-in duration-500">
              <Search className="size-12 text-muted-foreground/30 mb-4" />
              <h3 className="text-md font-medium text-muted-foreground">{i18n.page.events.noResults}</h3>
              <Button variant="ghost" size="sm" className="mt-2 text-xs" onClick={() => {
                setSearch('');
                setDateRange(undefined);
                setActiveTags(new Set());
              }}>
                {i18n.common.clearHighlight}
              </Button>
            </div>
          ) : (
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
          )}
        </div>

        {/* Responsive Detail Sheet */}
        <Sheet open={!!detailEvent} onOpenChange={(v) => !v && setDetailEvent(null)}>
          <SheetContent 
            side="right" 
            className="w-full sm:max-w-[440px] lg:max-w-[35vw] p-0 flex flex-col gap-0 border-l bg-background shadow-2xl"
          >
            {detailEvent && (
              <div className="flex flex-col h-full overflow-hidden">
                <div className="flex items-center justify-between p-4 border-b shrink-0 bg-background/80 backdrop-blur sticky top-0 z-10">
                  <div className="flex flex-col min-w-0 pr-6">
                    <SheetTitle className="text-sm font-semibold truncate">
                      {i18n.events.detailTitle}
                    </SheetTitle>
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider font-bold truncate">
                      {detailEvent.group || i18n.events.privateChat} Axis
                    </p>
                  </div>
                  <Button 
                    variant="ghost" 
                    size="icon" 
                    className="size-8 shrink-0 -mr-2" 
                    onClick={() => setDetailEvent(null)}
                  >
                    <X className="size-4" />
                  </Button>
                </div>
                
                <ScrollArea className="flex-1 overscroll-contain">
                  <div className="p-4 space-y-4">
                    {app.rawEvents
                      .filter(e => e.group === detailEvent.group)
                      .sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime())
                      .map((ev, idx) => (
                        <div 
                          key={ev.id} 
                          ref={ev.id === detailEvent.id ? focusedCardRef : null}
                          className="animate-in fade-in slide-in-from-right-4 duration-300 fill-mode-both"
                          style={{ animationDelay: `${Math.min(idx * 50, 300)}ms` }}
                        >
                          <EventDetailCard
                            event={ev}
                            isFocused={ev.id === detailEvent.id}
                            onEdit={ev => setEditEvent(ev)}
                            onDelete={handleDelete}
                            onLockToggle={handleLockToggle}
                            onSelect={() => setDetailEvent(ev)}
                            sudoMode={app.sudo}
                          />
                        </div>
                      ))
                    }
                  </div>
                </ScrollArea>
              </div>
            )}
          </SheetContent>
        </Sheet>
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
