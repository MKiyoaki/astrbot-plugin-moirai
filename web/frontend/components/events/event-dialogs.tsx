'use client'

import { useState, useEffect, useRef } from 'react'
import { Plus, Undo2, Trash2, Pencil, Check, ChevronsUpDown, X, Lock, Unlock, Archive } from 'lucide-react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { Slider } from '@/components/ui/slider'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Spinner } from '@/components/ui/spinner'
import { FieldGroup, Field, FieldLabel, FieldContent, FieldDescription } from '@/components/ui/field'
import { TagSelector } from '@/components/shared/tag-selector'
import { type ApiEvent } from '@/lib/api'
import { useApp } from '@/lib/store'
import { cn, parseSummaryTopics } from '@/lib/utils'
import { getTagColor } from '@/lib/colors'

export interface EventFormData {
  topic: string
  summary: string
  group_id: string
  start_time: string
  end_time: string
  salience: number
  tags: string[]
  participants: string[]
  inherit_from: string[]
  is_locked: boolean
  status: 'active' | 'archived'
}

const toLocalIso = (ts: number) => {
  if (!Number.isFinite(ts) || ts <= 0) {
    return new Date().toISOString().slice(0, 16)
  }
  return new Date(ts * 1000).toISOString().slice(0, 16)
}

// ── Helpers ───────────────────────────────────────────────────────────────

function GroupPicker({
  value,
  onChange,
  events,
}: {
  value: string
  onChange: (v: string) => void
  events: ApiEvent[]
}) {
  const { i18n } = useApp()
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

  const handleUseCustom = () => {
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
            <span
              role="button"
              tabIndex={0}
              className="inline-flex h-6 w-6 items-center justify-center rounded hover:text-destructive cursor-pointer"
              onClick={e => { e.stopPropagation(); onChange('') }}
              onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.stopPropagation(); onChange('') } }}
            >
              <X className="size-3" />
            </span>
          )}
          <ChevronsUpDown className="text-muted-foreground shrink-0" data-icon="inline-end" />
        </div>
      </PopoverTrigger>
      <PopoverContent className="w-72 p-2" align="start">
        <Input
          ref={inputRef}
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="输入或搜索群组 ID"
          className="mb-2"
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); handleUseCustom() } }}
        />
        {search.trim() && !knownGroups.includes(search.trim()) && (
          <Button
            variant="ghost"
            className="mb-1 w-full justify-start gap-2 h-9 px-2"
            onClick={handleUseCustom}
          >
            <Plus className="shrink-0 size-4" />
            <span>使用 &ldquo;{search}&rdquo;</span>
          </Button>
        )}
        <div className="max-h-40 overflow-y-auto">
          {filtered.length === 0 && !search.trim() ? (
            <p className="text-muted-foreground px-2 py-1.5 text-sm">暂无已知群组</p>
          ) : filtered.map(g => (
            <Button
              key={g}
              variant="ghost"
              className={cn(
                'w-full justify-start gap-2 h-9 px-2 font-normal',
                value === g && 'bg-accent/50',
              )}
              onClick={() => select(g)}
            >
              <Check className={cn('shrink-0 size-4', value === g ? 'opacity-100' : 'opacity-0')} />
              <span className="font-mono">{g}</span>
            </Button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  )
}

function EventInheritPicker({
  value,
  onChange,
  events,
}: {
  value: string[]
  onChange: (ids: string[]) => void
  events: ApiEvent[]
}) {
  const { i18n } = useApp()
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
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={e => { e.stopPropagation(); remove(id) }}
                className="hover:text-destructive h-4 w-4"
              >
                <X className="size-2.5" />
              </Button>
            </Badge>
          ))}
        </div>
        <ChevronsUpDown className="text-muted-foreground ml-2 shrink-0" data-icon="inline-end" />
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
                <Button
                  key={ev.id}
                  variant="ghost"
                  onClick={() => toggle(ev.id)}
                  className={cn(
                    'w-full justify-start gap-2 h-auto py-2 px-2 font-normal',
                    selected && 'bg-accent/50',
                  )}
                >
                  <Check className={cn('shrink-0 size-4', selected ? 'opacity-100' : 'opacity-0')} />
                  <span className="flex flex-col items-start gap-0.5 text-left">
                    <span className="truncate font-medium">
                      {ev.topic || ev.content || ev.id}
                    </span>
                    <span className="text-muted-foreground text-xs">
                      {ev.id.slice(0, 16)}…
                    </span>
                  </span>
                </Button>
              )
            })
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}

// ── Structured Summary Editor ─────────────────────────────────────────────

type StructuredTopic = { what: string; who: string; how: string; eval: string }

function buildSummaryString(topics: StructuredTopic[]): string {
  return topics
    .map(tp => {
      const base = `[What] ${tp.what} [Who] ${tp.who} [How] ${tp.how}`
      return tp.eval.trim() ? `${base} [Eval] ${tp.eval}` : base
    })
    .join(' | ')
}

function StructuredSummaryEditor({
  value,
  onChange,
}: {
  value: string
  onChange: (v: string) => void
}) {
  const { i18n } = useApp()
  const parsed = parseSummaryTopics(value)

  const [topics, setTopics] = useState<StructuredTopic[]>(() =>
    parsed
      ? parsed.map(tp => ({ what: tp.what, who: tp.who, how: tp.how, eval: tp.eval ?? '' }))
      : []
  )

  const update = (idx: number, field: keyof StructuredTopic, v: string) => {
    const next = topics.map((tp, i) => i === idx ? { ...tp, [field]: v } : tp)
    setTopics(next)
    onChange(buildSummaryString(next))
  }

  const addTopic = () => {
    const next = [...topics, { what: '', who: '', how: '', eval: '' }]
    setTopics(next)
    onChange(buildSummaryString(next))
  }

  const removeTopic = (idx: number) => {
    const next = topics.filter((_, i) => i !== idx)
    setTopics(next)
    onChange(buildSummaryString(next))
  }

  if (!parsed) {
    return (
      <Textarea
        id="ev-summary"
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder="输入事件的详细总结描述..."
        className="min-h-20"
      />
    )
  }

  const fieldDefs: { key: keyof StructuredTopic; label: string; placeholder: string }[] = [
    { key: 'what', label: i18n.events.summaryWhat, placeholder: i18n.events.summaryWhat },
    { key: 'who',  label: i18n.events.summaryWho,  placeholder: i18n.events.summaryWho },
    { key: 'how',  label: i18n.events.summaryHow,  placeholder: i18n.events.summaryHow },
    { key: 'eval', label: i18n.events.summaryEval, placeholder: i18n.events.summaryEvalNone },
  ]

  return (
    <div className="flex flex-col gap-3">
      {topics.map((tp, idx) => (
        <div key={idx} className="rounded-lg border border-border p-3 flex flex-col gap-2 relative">
          {topics.length > 1 && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="absolute top-1 right-1 h-6 w-6 text-muted-foreground hover:text-destructive"
              onClick={() => removeTopic(idx)}
            >
              <X className="size-3.5" />
            </Button>
          )}
          {topics.length > 1 && (
            <p className="text-[10px] font-bold text-muted-foreground tracking-widest">
              #{idx + 1}
            </p>
          )}
          {fieldDefs.map(({ key, label, placeholder }) => (
            <div key={key} className="flex items-start gap-2">
              <span className="text-[10px] uppercase font-bold text-primary/60 tracking-tight w-16 shrink-0 pt-2">
                {label}
              </span>
              <Input
                value={tp[key]}
                onChange={e => update(idx, key, e.target.value)}
                placeholder={placeholder}
                className="h-8 text-sm"
              />
            </div>
          ))}
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="self-start"
        onClick={addTopic}
      >
        <Plus className="size-3.5 mr-1" />
        {i18n.events.summaryWhat.includes('何') ? 'トピック追加' : i18n.events.summaryWhat.includes('发') ? '添加话题' : 'Add Topic'}
      </Button>
    </div>
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
  const { i18n } = useApp()
  const set = <K extends keyof EventFormData>(k: K, v: EventFormData[K]) =>
    onChange({ ...data, [k]: v })

  return (
    <FieldGroup>
      <Field>
        <FieldLabel htmlFor="ev-topic">{i18n.events.topic} *</FieldLabel>
        <FieldContent>
          <Input
            id="ev-topic"
            value={data.topic}
            onChange={e => set('topic', e.target.value)}
            placeholder="话题内容"
          />
        </FieldContent>
      </Field>

      <Field>
        <FieldLabel>{i18n.events.summary || '详细摘要'}</FieldLabel>
        <FieldContent>
          <StructuredSummaryEditor
            value={data.summary}
            onChange={v => set('summary', v)}
          />
        </FieldContent>
      </Field>

      <Field>
        <FieldLabel>{i18n.events.group}</FieldLabel>
        <FieldContent>
          <GroupPicker
            value={data.group_id}
            onChange={v => set('group_id', v)}
            events={events}
          />
        </FieldContent>
      </Field>

      <div className="grid grid-cols-2 gap-3">
        <Field>
          <FieldLabel htmlFor="ev-start">{i18n.events.start}</FieldLabel>
          <FieldContent>
            <Input
              id="ev-start"
              type="datetime-local"
              value={data.start_time}
              onChange={e => set('start_time', e.target.value)}
            />
          </FieldContent>
        </Field>

        <Field>
          <FieldLabel htmlFor="ev-end">{i18n.events.end}</FieldLabel>
          <FieldContent>
            <Input
              id="ev-end"
              type="datetime-local"
              value={data.end_time}
              onChange={e => set('end_time', e.target.value)}
            />
          </FieldContent>
        </Field>
      </div>

      <Field>
        <div className="flex justify-between">
          <FieldLabel>{i18n.events.salience}</FieldLabel>
          <span className="text-muted-foreground text-xs">{data.salience.toFixed(2)}</span>
        </div>
        <FieldContent>
          <Slider
            value={[data.salience]}
            onValueChange={(v: number | number[]) => set('salience', Array.isArray(v) ? v[0] : v)}
            min={0} max={1} step={0.01}
          />
        </FieldContent>
      </Field>

      <Field>
        <FieldLabel>{i18n.events.tags}</FieldLabel>
        <FieldContent>
          <TagSelector
            value={data.tags}
            onChange={v => set('tags', v)}
            suggestions={tagSuggestions}
          />
        </FieldContent>
      </Field>

      <Field>
        <FieldLabel>{i18n.events.participants}</FieldLabel>
        <FieldContent>
          <TagSelector
            value={data.participants}
            onChange={v => set('participants', v)}
            suggestions={[]}
            placeholder="输入 UID，按 Enter 确认"
          />
        </FieldContent>
      </Field>

      <Field orientation="horizontal" className="justify-between py-1">
        <FieldContent>
          <FieldLabel htmlFor="ev-locked" className="flex items-center gap-1.5 cursor-pointer">
            {data.is_locked ? <Lock data-icon="inline-start" /> : <Unlock data-icon="inline-start" />}
            {i18n.events.lockedMemory}
          </FieldLabel>
          <FieldDescription>{i18n.events.lockedMemoryDesc}</FieldDescription>
        </FieldContent>
        <Switch
          id="ev-locked"
          checked={data.is_locked}
          onCheckedChange={v => set('is_locked', v)}
        />
      </Field>

      <Field>
        <FieldLabel>{i18n.events.inheritFrom}</FieldLabel>
        <FieldContent>
          <EventInheritPicker
            value={data.inherit_from}
            onChange={v => set('inherit_from', v)}
            events={events}
          />
        </FieldContent>
      </Field>
    </FieldGroup>
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
  const { i18n } = useApp()
  const now = new Date()
  const isoNow = now.toISOString().slice(0, 16)
  const isoEnd = new Date(now.getTime() + 1800000).toISOString().slice(0, 16)

  const [data, setData] = useState<EventFormData>({
    topic: '', summary: '', group_id: '', start_time: isoNow, end_time: isoEnd,
    salience: 0.5, tags: [], participants: [], inherit_from: [], is_locked: false,
    status: 'active',
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
    <Dialog open={open} onOpenChange={(v: boolean) => !v && onClose()}>
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
          <Button onClick={handleSubmit} disabled={loading}>
            {loading && <Spinner data-icon="inline-start" />}
            {i18n.common.create}
          </Button>
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
  const { i18n } = useApp()
  const [data, setData] = useState<EventFormData>({
    topic: '', summary: '', group_id: '', start_time: '', end_time: '',
    salience: 0.5, tags: [], participants: [], inherit_from: [], is_locked: false,
    status: 'active',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (event) {
      setData({
        topic:       event.topic || event.content || '',
        summary:     event.summary || '',
        group_id:    event.group || '',
        start_time:  toLocalIso(event.start_ts || new Date(event.start).getTime() / 1000),
        end_time:    toLocalIso(event.end_ts   || new Date(event.end).getTime()   / 1000),
        salience:    event.salience,
        tags:        event.tags || [],
        participants: event.participants || [],
        inherit_from: event.inherit_from || [],
        is_locked: event.is_locked || false,
        status: event.status || 'active',
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

  const inheritCandidates = events.filter(ev => ev.id !== event?.id)

  return (
    <Dialog open={open} onOpenChange={(v: boolean) => !v && onClose()}>
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
          <Button onClick={handleSubmit} disabled={loading}>
            {loading && <Spinner data-icon="inline-start" />}
            {i18n.common.save}
          </Button>
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
  const { i18n } = useApp()
  return (
    <Dialog open={open} onOpenChange={(v: boolean) => !v && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{i18n.events.recycleBin}</DialogTitle>
          <DialogDescription>{i18n.events.recycleBinDescription}</DialogDescription>
        </DialogHeader>
        <ScrollArea className="max-h-[50vh]">
          {loading ? (
            <div className="flex justify-center py-8">
              <Spinner />
            </div>
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
                    <Undo2 data-icon="inline-start" />
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
            <Trash2 data-icon="inline-start" />
            {i18n.events.clearBin}
          </Button>
          <Button variant="outline" onClick={onClose}>{i18n.common.close}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Archive Events Dialog ─────────────────────────────────────────────────

interface ArchiveEventsDialogProps {
  open: boolean
  items: ApiEvent[]
  loading: boolean
  onClose: () => void
  onUnarchive: (id: string) => Promise<void>
  sudoMode: boolean
}
export function ArchiveEventsDialog({ open, items, loading, onClose, onUnarchive, sudoMode }: ArchiveEventsDialogProps) {
  const { i18n } = useApp()
  return (
    <Dialog open={open} onOpenChange={(v: boolean) => !v && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{i18n.events.archivedBin}</DialogTitle>
          <DialogDescription>{i18n.events.archivedBinDescription}</DialogDescription>
        </DialogHeader>
        <ScrollArea className="max-h-[65vh]">
          {loading ? (
            <div className="flex justify-center py-8">
              <Spinner />
            </div>
          ) : items.length === 0 ? (
            <p className="text-muted-foreground py-8 text-center text-sm">{i18n.events.archivedBinEmpty}</p>
          ) : (
            <div className="flex flex-col gap-2 pr-2">
              {items.map(ev => (
                <div key={ev.id} className="bg-muted flex items-center justify-between rounded-lg p-3">
                  <div className="min-w-0 flex-1 pr-4">
                    <div className="text-sm font-medium truncate">{ev.content || ev.topic || ev.id}</div>
                    <div className="text-muted-foreground text-xs mt-0.5 flex items-center gap-2">
                      <span>{ev.group || i18n.events.privateChat}</span>
                      <span>·</span>
                      <span>{new Date(ev.start).toLocaleDateString()}</span>
                      <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4">
                        {(ev.salience * 100).toFixed(0)}%
                      </Badge>
                      {(ev.tags ?? []).slice(0, 2).map(t => (
                        <Badge key={t} variant="outline" className="text-[10px] px-1.5 py-0 h-4">#{t}</Badge>
                      ))}
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={!sudoMode}
                    onClick={() => onUnarchive(ev.id)}
                  >
                    <Undo2 data-icon="inline-start" />
                    {i18n.events.unarchive}
                  </Button>
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{i18n.common.close}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Event Detail Sheet ────────────────────────────────────────────────────

interface EventDetailProps {
  event: ApiEvent | null
  isFocused?: boolean
  onEdit: (ev: ApiEvent) => void
  onDelete: (ev: ApiEvent) => void
  onLockToggle: (ev: ApiEvent) => void
  onArchive?: (ev: ApiEvent) => void
  onSelect?: () => void
  sudoMode: boolean
}

export function EventDetailCard({ event, isFocused, onEdit, onDelete, onLockToggle, onArchive, onSelect, sudoMode }: EventDetailProps) {
  const { i18n } = useApp()
  const [pendingArchive, setPendingArchive] = useState(false)
  const archiveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  if (!event) return null
  const isArchived = event.status === 'archived'

  return (
    <div 
      onClick={() => !isFocused && onSelect?.()}
      className={cn(
        "relative flex flex-col gap-3 rounded-xl border bg-card p-5 transition-all duration-300 min-w-0 max-w-full overflow-hidden",
        isFocused ? "ring-2 ring-primary shadow-lg scale-[1.01] z-10" : "opacity-70 hover:opacity-100 cursor-pointer hover:border-primary/30",
        isArchived && "opacity-60 grayscale-[0.5]"
      )}
    >
      {/* Accent Bar */}
      <div 
        className={cn(
          "absolute left-0 top-3 bottom-3 w-1.5 rounded-r-full transition-colors",
          isFocused ? "bg-primary" : "bg-muted"
        )} 
      />

      <div className="flex items-start justify-between gap-2 pl-2 min-w-0">
        <div className="flex-1 min-w-0">
          <h4 className="font-bold text-base truncate flex items-center gap-2">
            {event.content || event.topic || event.id}
            {event.is_locked && <Lock className="size-4 text-primary shrink-0" />}
          </h4>
          <p className="text-[11px] font-mono text-muted-foreground mt-0.5">
            {new Date(event.start).toLocaleString()}
          </p>
        </div>
        {isFocused && (
          <Badge variant={event.salience > 0.7 ? "default" : "secondary"} className="shrink-0">
            Salience: {(event.salience * 100).toFixed(0)}%
          </Badge>
        )}
      </div>

      <div className="grid grid-cols-3 gap-3 text-xs pl-2 bg-muted/30 p-3 rounded-lg">
        {[
          [i18n.events.id,         event.id.slice(0, 8) + '…'],
          [i18n.events.end,        new Date(event.end).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })],
          [i18n.events.confidence, (event.confidence * 100).toFixed(0) + '%'],
          [i18n.events.participants, (event.participants || []).length > 0 ? (event.participants || []).length : '—'],
          [i18n.events.personaLabel, event.bot_persona_name ?? i18n.events.personaDefault],
        ].map(([k, v]) => (
          <div key={k} className="flex flex-col gap-0.5">
            <span className="text-muted-foreground text-[10px] uppercase font-bold tracking-tight">{k}</span>
            <span className="truncate font-medium">{v}</span>
          </div>
        ))}
      </div>

      {event.summary && (() => {
        const topics = parseSummaryTopics(event.summary)
        return (
          <div className="relative overflow-hidden rounded-lg border-l-4 border-primary/40 bg-primary/5 p-4 ml-2">
            <div className="absolute top-0 right-0 p-2 opacity-10">
              <Check className="size-12" />
            </div>
            <p className="text-[11px] uppercase font-bold text-primary/70 tracking-widest mb-2">{i18n.events.summary || 'Summary'}</p>
            {topics ? (
              <div className="flex flex-col gap-2">
                {topics.map((tp, i) => (
                  <div key={i} className="flex flex-col gap-0.5">
                    {i > 0 && <div className="border-t border-primary/10 mb-1" />}
                    {([
                      [i18n.events.summaryWhat, tp.what],
                      [i18n.events.summaryWho,  tp.who],
                      [i18n.events.summaryHow,  tp.how],
                      [i18n.events.summaryEval, tp.eval ?? i18n.events.summaryEvalNone],
                    ] as [string, string][]).map(([label, val]) => (
                      <div key={label} className="flex gap-2 text-sm leading-snug">
                        <span className="text-[10px] uppercase font-bold text-primary/60 tracking-tight w-14 shrink-0 pt-0.5">{label}</span>
                        <span className="text-foreground/90 font-medium">{val}</span>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-foreground/90 leading-relaxed font-medium">
                {event.summary}
              </div>
            )}
          </div>
        )
      })()}

      {event.tags?.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pl-2">
          {event.tags.map(t => {
            const tagColor = getTagColor(t)
            return (
              <Badge 
                key={t} 
                variant="secondary" 
                className="text-[10px] py-0 px-2 h-5 font-medium"
                style={{ 
                  background: `color-mix(in srgb, ${tagColor} 12%, transparent)`, 
                  color: tagColor,
                  borderColor: `color-mix(in srgb, ${tagColor} 30%, transparent)`
                }}
              >
                #{t}
              </Badge>
            )
          })}
        </div>
      )}

      <div className="flex items-center gap-2 pt-2 pl-2 border-t mt-1">
        {isFocused ? (
          <>
            <Button size="sm" variant="default" className="h-9 px-4 shadow-sm" disabled={!sudoMode} onClick={() => onEdit(event)}>
              <Pencil className="mr-2 size-3.5" />{i18n.common.edit}
            </Button>
            <Button
              size="sm"
              variant="outline"
              className={cn("h-9 px-4", event.is_locked && "text-primary border-primary/30 bg-primary/5")}
              disabled={!sudoMode}
              onClick={() => onLockToggle(event)}
            >
              {event.is_locked ? <Lock className="mr-2 size-3.5" /> : <Unlock className="mr-2 size-3.5" />}
              {event.is_locked ? i18n.events.unlock : i18n.events.lock}
            </Button>
            {onArchive && (
              <Button
                size="sm"
                variant={pendingArchive ? "default" : "outline"}
                className={cn("h-9 px-4 transition-colors", pendingArchive && "bg-amber-500 hover:bg-amber-600 border-amber-500 text-white")}
                disabled={!sudoMode || event.is_locked || event.status === 'archived'}
                onClick={() => {
                  if (!pendingArchive) {
                    setPendingArchive(true)
                    archiveTimerRef.current = setTimeout(() => setPendingArchive(false), 3000)
                  } else {
                    if (archiveTimerRef.current) clearTimeout(archiveTimerRef.current)
                    setPendingArchive(false)
                    onArchive(event)
                  }
                }}
              >
                <Archive className="mr-2 size-3.5" />
                {pendingArchive ? i18n.common.confirm : i18n.events.archive}
              </Button>
            )}
            <div className="flex-1" />
            <Button
              size="sm"
              variant="ghost"
              className="h-9 px-3 text-destructive hover:bg-destructive/10 hover:text-destructive"
              disabled={!sudoMode || event.is_locked}
              onClick={(e) => { e.stopPropagation(); onDelete(event) }}
              title={event.is_locked ? (i18n.events.lockedDeleteHint || 'Locked events cannot be deleted') : ''}
            >
              <Trash2 className="size-3.5" />
            </Button>
          </>
        ) : (
          <>
            <Button 
              size="sm" 
              variant="ghost" 
              className={cn("h-8 text-[11px]", event.is_locked && "text-primary")}
              disabled={!sudoMode} 
              onClick={(e) => { e.stopPropagation(); onLockToggle(event) }}
            >
              {event.is_locked ? <Lock className="mr-1.5 size-3" /> : <Unlock className="mr-1.5 size-3" />}
              {event.is_locked ? i18n.events.unlock : i18n.events.lock}
            </Button>
            <div className="flex-1" />
            <span className="text-[10px] text-muted-foreground italic">Select to edit</span>
          </>
        )}
      </div>
    </div>
  )
}
