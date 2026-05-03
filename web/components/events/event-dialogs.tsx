'use client'

import { useState, useEffect } from 'react'
import { Save, Undo2, Trash2, Pencil } from 'lucide-react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import { TagSelector } from '@/components/shared/tag-selector'
import { type ApiEvent } from '@/lib/api'
import { i18n } from '@/lib/i18n'

export interface EventFormData {
  topic: string
  group_id: string
  start_time: string
  end_time: string
  salience: number
  confidence: number
  tags: string[]
  participants: string[]
  inherit_from: string[]
}

const toLocalIso = (ts: number) =>
  new Date(ts * 1000).toISOString().slice(0, 16)

const fromLocalIso = (s: string) =>
  Math.floor(new Date(s).getTime() / 1000)

function EventForm({
  data,
  onChange,
  tagSuggestions,
}: {
  data: EventFormData
  onChange: (d: EventFormData) => void
  tagSuggestions: string[]
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
        <Label htmlFor="ev-group">{i18n.events.group}</Label>
        <Input
          id="ev-group"
          value={data.group_id}
          onChange={e => set('group_id', e.target.value)}
          placeholder="群组 ID（空 = 私聊）"
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
          onValueChange={v => set('salience', Array.isArray(v) ? v[0] : v)}
          min={0} max={1} step={0.01}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <div className="flex justify-between">
          <Label>{i18n.events.confidence}</Label>
          <span className="text-muted-foreground text-xs">{data.confidence.toFixed(2)}</span>
        </div>
        <Slider
          value={[data.confidence]}
          onValueChange={v => set('confidence', Array.isArray(v) ? v[0] : v)}
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
        <Label htmlFor="ev-participants">{i18n.events.participants}（UID，逗号分隔）</Label>
        <Input
          id="ev-participants"
          value={data.participants.join(', ')}
          onChange={e => set('participants', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="ev-inherit">{i18n.events.inheritFrom}（事件 ID，逗号分隔）</Label>
        <Input
          id="ev-inherit"
          value={data.inherit_from.join(', ')}
          onChange={e => set('inherit_from', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
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
}

export function CreateEventDialog({ open, onClose, onSubmit, tagSuggestions }: CreateEventDialogProps) {
  const now = new Date()
  const isoNow = now.toISOString().slice(0, 16)
  const isoEnd = new Date(now.getTime() + 1800000).toISOString().slice(0, 16)

  const [data, setData] = useState<EventFormData>({
    topic: '', group_id: '', start_time: isoNow, end_time: isoEnd,
    salience: 0.5, confidence: 0.8, tags: [], participants: [], inherit_from: [],
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
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{i18n.events.createTitle}</DialogTitle>
          <DialogDescription>填写事件信息后点击创建。</DialogDescription>
        </DialogHeader>
        <ScrollArea className="max-h-[60vh]">
          <div className="pr-4">
            <EventForm data={data} onChange={setData} tagSuggestions={tagSuggestions} />
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
}

export function EditEventDialog({ open, event, onClose, onSubmit, tagSuggestions }: EditEventDialogProps) {
  const [data, setData] = useState<EventFormData>({
    topic: '', group_id: '', start_time: '', end_time: '',
    salience: 0.5, confidence: 0.8, tags: [], participants: [], inherit_from: [],
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (event) {
      setData({
        topic:       event.topic || event.content || '',
        group_id:    event.group || '',
        start_time:  toLocalIso(event.start_ts || new Date(event.start).getTime() / 1000),
        end_time:    toLocalIso(event.end_ts   || new Date(event.end).getTime()   / 1000),
        salience:    event.salience,
        confidence:  event.confidence,
        tags:        event.tags || [],
        participants: event.participants || [],
        inherit_from: event.inherit_from || [],
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

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{i18n.events.editTitle}</DialogTitle>
          <DialogDescription>修改事件信息后点击保存。</DialogDescription>
        </DialogHeader>
        <ScrollArea className="max-h-[60vh]">
          <div className="pr-4">
            <EventForm data={data} onChange={setData} tagSuggestions={tagSuggestions} />
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
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
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
            <span className="truncate font-medium">{v}</span>
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
