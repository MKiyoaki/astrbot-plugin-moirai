'use client'

import { useState, useEffect, useRef } from 'react'
import { Plus, Undo2, Trash2, Pencil, Check, ChevronsUpDown, X, Lock, Unlock } from 'lucide-react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Slider } from '@/components/ui/slider'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { TagSelector } from '@/components/shared/tag-selector'
import { type ApiEvent } from '@/lib/api'
import { i18n } from '@/lib/i18n'
import { cn } from '@/lib/utils'

export interface EventFormData {
  topic: string
  group_id: string
  start_time: string
  end_time: string
  salience: number
  tags: string[]
  participants: string[]
  inherit_from: string[]
  is_locked: boolean
}

const toLocalIso = (ts: number) =>
  new Date(ts * 1000).toISOString().slice(0, 16)

const fromLocalIso = (s: string) =>
  Math.floor(new Date(s).getTime() / 1000)


function GroupPicker({
  value,
  onChange,
  events,
}: {
  value: string
  onChange: (v: string) => void
  events: ApiEvent[]
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const knownGroups = Array.from(new Set(events.map(ev => ev.group).filter(Boolean) as string[]))
  const filtered = knownGroups.filter(g => g.toLowerCase().includes(search.toLowerCase()))

  const select = (g: string) => {
    onChange(g)
    setOpen(false)
    setSearch('')
  }

  const useCustom = () => {
    if (search.trim()) {
      onChange(search.trim())
      setOpen(false)
      setSearch('')
    }
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        className="border-input bg-transparent text-foreground flex min-h-9 w-full items-center justify-between rounded-lg border px-2.5 py-1.5 text-sm"
        onClick={() => { setOpen(true); setTimeout(() => inputRef.current?.focus(), 50) }}
      >
        <span className={value ? 'font-mono' : 'text-muted-foreground'}>
          {value || i18n.events.groupPlaceholder}
        </span>
        <div className="flex items-center gap-1">
          {value && (
            <button
              type="button"
              onClick={e => { e.stopPropagation(); onChange('') }}
              className="hover:text-destructive"
            >
              <X className="size-3" />
            </button>
          )}
          <ChevronsUpDown className="text-muted-foreground size-3.5 shrink-0" />
        </div>
      </PopoverTrigger>
      <PopoverContent className="w-72 p-2" align="start">
        <Input
          ref={inputRef}
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="输入或搜索群组 ID"
          className="mb-2"
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); useCustom() } }}
        />
        {search.trim() && !knownGroups.includes(search.trim()) && (
          <button
            type="button"
            onClick={useCustom}
            className="hover:bg-accent mb-1 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm"
          >
            <Plus className="size-3.5 shrink-0" />
            <span>使用 &ldquo;{search}&rdquo;</span>
          </button>
        )}
        <div className="max-h-40 overflow-y-auto">
          {filtered.length === 0 && !search.trim() ? (
            <p className="text-muted-foreground px-2 py-1.5 text-sm">暂无已知群组</p>
          ) : filtered.map(g => (
            <button
              key={g}
              type="button"
              onClick={() => select(g)}
              className={cn(
                'hover:bg-accent flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm',
                value === g && 'bg-accent/50',
              )}
            >
              <Check className={cn('size-3.5 shrink-0', value === g ? 'opacity-100' : 'opacity-0')} />
              <span className="font-mono">{g}</span>
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  )
}

// ── Inherit picker ────────────────────────────────────────────────────────

function EventInheritPicker({
  value,
  onChange,
  events,
}: {
  value: string[]
  onChange: (ids: string[]) => void
  events: ApiEvent[]
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const filtered = events.filter(ev => {
    const q = search.toLowerCase()
    return (
      (ev.topic || '').toLowerCase().includes(q) ||
      (ev.content || '').toLowerCase().includes(q) ||
      ev.id.toLowerCase().includes(q)
    )
  })

  const toggle = (id: string) => {
    if (value.includes(id)) {
      onChange(value.filter(x => x !== id))
    } else {
      onChange([...value, id])
    }
  }

  const remove = (id: string) => onChange(value.filter(x => x !== id))

  const labelFor = (id: string) => {
    const ev = events.find(e => e.id === id)
    return ev ? (ev.topic || ev.content || id.slice(0, 12)) : id.slice(0, 12)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        className="border-input bg-transparent text-foreground flex min-h-9 w-full items-center justify-between rounded-lg border px-2.5 py-1.5 text-sm"
        onClick={() => { setOpen(true); setTimeout(() => inputRef.current?.focus(), 50) }}
      >
        <div className="flex flex-wrap gap-1">
          {value.length === 0 && (
            <span className="text-muted-foreground">{i18n.events.inheritPlaceholder}</span>
          )}
          {value.map(id => (
            <Badge key={id} variant="secondary" className="gap-1 pr-1 text-xs">
              {labelFor(id)}
              <button
                type="button"
                onClick={e => { e.stopPropagation(); remove(id) }}
                className="hover:text-destructive ml-0.5"
              >
                <X className="size-2.5" />
              </button>
            </Badge>
          ))}
        </div>
        <ChevronsUpDown className="text-muted-foreground ml-2 size-4 shrink-0" />
      </PopoverTrigger>
      <PopoverContent className="w-80 p-2" align="start">
        <Input
          ref={inputRef}
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder={i18n.events.inheritSearch}
          className="mb-2"
        />
        <div className="max-h-52 overflow-y-auto">
          {filtered.length === 0 ? (
            <p className="text-muted-foreground px-2 py-1.5 text-sm">
              {events.length === 0 ? i18n.events.inheritEmpty : i18n.events.inheritNoMatch}
            </p>
          ) : (
            filtered.map(ev => {
              const selected = value.includes(ev.id)
              return (
                <button
                  key={ev.id}
                  type="button"
                  onClick={() => toggle(ev.id)}
                  className={cn(
                    'hover:bg-accent flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm',
                    selected && 'bg-accent/50',
                  )}
                >
                  <Check className={cn('size-3.5 shrink-0', selected ? 'opacity-100' : 'opacity-0')} />
                  <span className="flex flex-col items-start gap-0.5 text-left">
                    <span className="truncate font-medium">
                      {ev.topic || ev.content || ev.id}
                    </span>
                    <span className="text-muted-foreground text-xs">
                      {ev.id.slice(0, 16)}…
                    </span>
                  </span>
                </button>
              )
            })
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}

// ── Event Form ────────────────────────────────────────────────────────────

function EventForm({
  data,
  onChange,
  tagSuggestions,
  events,
}: {
  data: EventFormData
  onChange: (d: EventFormData) => void
  tagSuggestions: string[]
  events: ApiEvent[]
}) {
  const set = <K extends keyof EventFormData>(k: K, v: EventFormData[K]) =>
    onChange({ ...data, [k]: v })

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="ev-topic">{i18n.events.topic} *</Label>
        <Input
          id="ev-topic"
          value={data.topic}
          onChange={e => set('topic', e.target.value)}
          placeholder="话题内容"
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label>{i18n.events.group}</Label>
        <GroupPicker
          value={data.group_id}
          onChange={v => set('group_id', v)}
          events={events}
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="ev-start">{i18n.events.start}</Label>
          <Input
            id="ev-start"
            type="datetime-local"
            value={data.start_time}
            onChange={e => set('start_time', e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="ev-end">{i18n.events.end}</Label>
          <Input
            id="ev-end"
            type="datetime-local"
            value={data.end_time}
            onChange={e => set('end_time', e.target.value)}
          />
        </div>
      </div>
      <div className="flex flex-col gap-1.5">
        <div className="flex justify-between">
          <Label>{i18n.events.salience}</Label>
          <span className="text-muted-foreground text-xs">{data.salience.toFixed(2)}</span>
        </div>
        <Slider
          value={[data.salience]}
          onValueChange={(v: number | number[]) => set('salience', Array.isArray(v) ? v[0] : v)}
          min={0} max={1} step={0.01}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label>{i18n.events.tags}</Label>
        <TagSelector
          value={data.tags}
          onChange={v => set('tags', v)}
          suggestions={tagSuggestions}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label>{i18n.events.participants}</Label>
        <TagSelector
          value={data.participants}
          onChange={v => set('participants', v)}
          suggestions={[]}
          placeholder="输入 UID，按 Enter 确认"
        />
      </div>
      <div className="flex items-center justify-between py-1">
        <div className="flex flex-col gap-0.5">
          <Label htmlFor="ev-locked" className="flex items-center gap-1.5 cursor-pointer">
            {data.is_locked ? <Lock className="size-3.5" /> : <Unlock className="size-3.5" />}
            锁定记忆
          </Label>
          <p className="text-[11px] text-muted-foreground">锁定后，此记忆不会被自动清理任务删除。</p>
        </div>
        <Switch
          id="ev-locked"
          checked={data.is_locked}
          onCheckedChange={v => set('is_locked', v)}
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label>{i18n.events.inheritFrom}</Label>
        <EventInheritPicker
          value={data.inherit_from}
          onChange={v => set('inherit_from', v)}
          events={events}
        />
      </div>
    </div>
  )
}

// ── Create Event Dialog ────────────────────────────────────────────────────

interface CreateEventDialogProps {
  open: boolean
  onClose: () => void
  onSubmit: (data: EventFormData) => Promise<void>
  tagSuggestions: string[]
  events: ApiEvent[]
}

export function CreateEventDialog({ open, onClose, onSubmit, tagSuggestions, events }: CreateEventDialogProps) {
  const now = new Date()
  const isoNow = now.toISOString().slice(0, 16)
  const isoEnd = new Date(now.getTime() + 1800000).toISOString().slice(0, 16)

  const [data, setData] = useState<EventFormData>({
    topic: '', group_id: '', start_time: isoNow, end_time: isoEnd,
    salience: 0.5, tags: [], participants: [], inherit_from: [], is_locked: false,
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async () => {
    if (!data.topic.trim()) { setError('话题不能为空'); return }
    setLoading(true); setError('')
    try {
      await onSubmit(data)
      onClose()
    } catch (e: unknown) {
      setError((e as { body?: string }).body || '创建失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v: any) => !v && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{i18n.events.createTitle}</DialogTitle>
          <DialogDescription>填写事件信息后点击创建。</DialogDescription>
        </DialogHeader>
        <ScrollArea className="max-h-[60vh]">
          <div className="pr-4">
            <EventForm data={data} onChange={setData} tagSuggestions={tagSuggestions} events={events} />
          </div>
        </ScrollArea>
        {error && <p className="text-destructive text-sm">{error}</p>}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{i18n.common.cancel}</Button>
          <Button onClick={handleSubmit} disabled={loading}>{i18n.common.create}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Edit Event Dialog ──────────────────────────────────────────────────────

interface EditEventDialogProps {
  open: boolean
  event: ApiEvent | null
  onClose: () => void
  onSubmit: (id: string, data: EventFormData) => Promise<void>
  tagSuggestions: string[]
  events: ApiEvent[]
}

export function EditEventDialog({ open, event, onClose, onSubmit, tagSuggestions, events }: EditEventDialogProps) {
  const existingConfidenceRef = useRef<number>(0.8)
  const [data, setData] = useState<EventFormData>({
    topic: '', group_id: '', start_time: '', end_time: '',
    salience: 0.5, tags: [], participants: [], inherit_from: [], is_locked: false,
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (event) {
      existingConfidenceRef.current = event.confidence
      setData({
        topic:       event.topic || event.content || '',
        group_id:    event.group || '',
        start_time:  toLocalIso(event.start_ts || new Date(event.start).getTime() / 1000),
        end_time:    toLocalIso(event.end_ts   || new Date(event.end).getTime()   / 1000),
        salience:    event.salience,
        tags:        event.tags || [],
        participants: event.participants || [],
        inherit_from: event.inherit_from || [],
        is_locked:    event.is_locked || false,
      })
      setError('')
    }
  }, [event])

  const handleSubmit = async () => {
    if (!event) return
    if (!data.topic.trim()) { setError('话题不能为空'); return }
    setLoading(true); setError('')
    try {
      await onSubmit(event.id, data)
      onClose()
    } catch (e: unknown) {
      setError((e as { body?: string }).body || '更新失败')
    } finally {
      setLoading(false)
    }
  }

  // Filter out the currently-edited event from the inherit candidates
  const inheritCandidates = events.filter(ev => ev.id !== event?.id)

  return (
    <Dialog open={open} onOpenChange={(v: any) => !v && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{i18n.events.editTitle}</DialogTitle>
          <DialogDescription>修改事件信息后点击保存。</DialogDescription>
        </DialogHeader>
        <ScrollArea className="max-h-[60vh]">
          <div className="pr-4">
            <EventForm data={data} onChange={setData} tagSuggestions={tagSuggestions} events={inheritCandidates} />
          </div>
        </ScrollArea>
        {error && <p className="text-destructive text-sm">{error}</p>}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{i18n.common.cancel}</Button>
          <Button onClick={handleSubmit} disabled={loading}>{i18n.common.save}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Recycle Bin Dialog ────────────────────────────────────────────────────

interface RecycleBinItem extends ApiEvent { deleted_at?: string }

interface RecycleBinDialogProps {
  open: boolean
  items: RecycleBinItem[]
  loading: boolean
  onClose: () => void
  onRestore: (id: string) => Promise<void>
  onClear: () => Promise<void>
  sudoMode: boolean
}

export function RecycleBinDialog({ open, items, loading, onClose, onRestore, onClear, sudoMode }: RecycleBinDialogProps) {
  return (
    <Dialog open={open} onOpenChange={(v: any) => !v && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{i18n.events.recycleBin}</DialogTitle>
          <DialogDescription>已删除的事件可在此还原。</DialogDescription>
        </DialogHeader>
        <ScrollArea className="max-h-[50vh]">
          {loading ? (
            <p className="text-muted-foreground py-8 text-center text-sm">{i18n.common.loading}</p>
          ) : items.length === 0 ? (
            <p className="text-muted-foreground py-8 text-center text-sm">{i18n.events.recycleBinEmpty}</p>
          ) : (
            <div className="flex flex-col gap-2 pr-2">
              {items.map(ev => (
                <div key={ev.id} className="bg-muted flex items-center justify-between rounded-lg p-3">
                  <div>
                    <div className="text-sm font-medium">{ev.content || ev.topic || ev.id}</div>
                    <div className="text-muted-foreground text-xs">
                      {ev.group || i18n.events.privateChat}
                      {ev.deleted_at && ` · ${i18n.events.deletedAt} ${new Date(ev.deleted_at).toLocaleString()}`}
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={!sudoMode}
                    onClick={() => onRestore(ev.id)}
                  >
                    <Undo2 className="mr-1 size-3.5" />
                    {i18n.events.restore}
                  </Button>
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
        <DialogFooter>
          <Button
            variant="destructive"
            size="sm"
            disabled={!sudoMode || items.length === 0}
            onClick={onClear}
          >
            <Trash2 className="mr-1 size-3.5" />
            {i18n.events.clearBin}
          </Button>
          <Button variant="outline" onClick={onClose}>{i18n.common.close}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Event Detail Sheet ────────────────────────────────────────────────────

interface EventDetailProps {
  event: ApiEvent | null
  onEdit: (ev: ApiEvent) => void
  onDelete: (ev: ApiEvent) => void
  sudoMode: boolean
}

export function EventDetailCard({ event, onEdit, onDelete, sudoMode }: EventDetailProps) {
  if (!event) return null
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
        {[
          [i18n.events.topic,      event.content],
          [i18n.events.id,         event.id.slice(0, 12) + '…'],
          [i18n.events.group,      event.group || i18n.events.privateChat],
          [i18n.events.start,      new Date(event.start).toLocaleString()],
          [i18n.events.end,        new Date(event.end).toLocaleString()],
          [i18n.events.salience,   (event.salience * 100).toFixed(0) + '%'],
          [i18n.events.confidence, (event.confidence * 100).toFixed(0) + '%'],
          [i18n.events.participants, (event.participants || []).map(p => p.slice(0, 10)).join(', ') || '—'],
        ].map(([k, v]) => (
          <div key={k} className="contents">
            <span className="text-muted-foreground">{k}</span>
            <span className="truncate font-medium flex items-center gap-1.5">
              {v}
              {k === i18n.events.topic && event.is_locked && <Lock className="size-3 text-amber-500" />}
            </span>
          </div>
        ))}
      </div>
      {event.tags?.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {event.tags.map(t => <Badge key={t} variant="secondary" className="text-xs">{t}</Badge>)}
        </div>
      )}
      <div className="flex gap-2 pt-2">
        <Button size="sm" variant="outline" disabled={!sudoMode} onClick={() => onEdit(event)}>
          <Pencil className="mr-1 size-3.5" />{i18n.common.edit}
        </Button>
        <Button size="sm" variant="destructive" disabled={!sudoMode} onClick={() => onDelete(event)}>
          <Trash2 className="mr-1 size-3.5" />{i18n.common.delete}
        </Button>
      </div>
    </div>
  )
}
