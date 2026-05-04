'use client'

import { useState, useEffect, useRef } from 'react'
import { Pencil, Trash2 } from 'lucide-react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { TagSelector } from '@/components/shared/tag-selector'
import { type PersonaNode, type ImpressionEdge } from '@/lib/api'
import { i18n } from '@/lib/i18n'

// ── Persona Form ─────────────────────────────────────────────────────────

interface PersonaFormData {
  name: string
  description: string
  affect_type: string
  tags: string[]
  bindings: string
}

const AFFECT_TYPES = ['积极', '中性', '消极', '复杂']

function PersonaForm({ data, onChange }: { data: PersonaFormData; onChange: (d: PersonaFormData) => void }) {
  const set = <K extends keyof PersonaFormData>(k: K, v: PersonaFormData[K]) =>
    onChange({ ...data, [k]: v })

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="p-name">{i18n.graph.name} *</Label>
        <Input id="p-name" value={data.name} onChange={e => set('name', e.target.value)} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="p-desc">{i18n.graph.description}</Label>
        <Input id="p-desc" value={data.description} onChange={e => set('description', e.target.value)} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label>{i18n.graph.affectType}</Label>
        <Select value={data.affect_type} onValueChange={v => set('affect_type', v ?? '')}>
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {AFFECT_TYPES.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label>{i18n.graph.contentTags}</Label>
        <TagSelector value={data.tags} onChange={v => set('tags', v)} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="p-bindings">{i18n.graph.bindings}</Label>
        <textarea
          id="p-bindings"
          className="border-input bg-transparent text-foreground focus-visible:border-ring focus-visible:ring-ring/50 min-h-16 w-full rounded-lg border px-2.5 py-2 text-sm outline-none focus-visible:ring-3"
          value={data.bindings}
          onChange={e => set('bindings', e.target.value)}
          placeholder="platform:id&#10;telegram:12345"
        />
      </div>
    </div>
  )
}

function parseBindings(raw: string) {
  return raw.split('\n').map(line => {
    const [platform, physical_id] = line.split(':').map(s => s.trim())
    return platform && physical_id ? { platform, physical_id } : null
  }).filter(Boolean) as { platform: string; physical_id: string }[]
}

// ── Create Persona ────────────────────────────────────────────────────────

export function CreatePersonaDialog({
  open, onClose, onSubmit, defaultConfidence,
}: {
  open: boolean
  onClose: () => void
  onSubmit: (data: Record<string, unknown>) => Promise<void>
  defaultConfidence: number
}) {
  const [data, setData] = useState<PersonaFormData>({
    name: '', description: '', affect_type: '中性', tags: [], bindings: '',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async () => {
    if (!data.name.trim()) { setError('姓名不能为空'); return }
    setLoading(true); setError('')
    try {
      await onSubmit({
        primary_name: data.name.trim(),
        description: data.description.trim(),
        affect_type: data.affect_type,
        content_tags: data.tags,
        confidence: defaultConfidence,
        bound_identities: parseBindings(data.bindings),
      })
      onClose()
    } catch (e: unknown) {
      setError((e as { body?: string }).body || '创建失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{i18n.graph.createTitle}</DialogTitle>
          <DialogDescription>填写人格信息后点击创建。</DialogDescription>
        </DialogHeader>
        <ScrollArea className="max-h-[60vh]">
          <div className="pr-4"><PersonaForm data={data} onChange={setData} /></div>
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

// ── Edit Persona ──────────────────────────────────────────────────────────

export function EditPersonaDialog({
  open, node, onClose, onSubmit,
}: {
  open: boolean
  node: PersonaNode | null
  onClose: () => void
  onSubmit: (uid: string, data: Record<string, unknown>) => Promise<void>
}) {
  const [data, setData] = useState<PersonaFormData>({
    name: '', description: '', affect_type: '中性', tags: [], bindings: '',
  })
  const existingConfidenceRef = useRef<number>(0.5)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (node) {
      const d = node.data
      existingConfidenceRef.current = d.confidence
      setData({
        name:        d.label || '',
        description: d.attrs?.description || '',
        affect_type: d.attrs?.affect_type || '中性',
        tags:        d.attrs?.content_tags || [],
        bindings:    (d.bound_identities || []).map(b => `${b.platform}:${b.physical_id}`).join('\n'),
      })
      setError('')
    }
  }, [node])

  const handleSubmit = async () => {
    if (!node) return
    if (!data.name.trim()) { setError('姓名不能为空'); return }
    setLoading(true); setError('')
    try {
      await onSubmit(node.data.id, {
        primary_name:   data.name.trim(),
        description:    data.description.trim(),
        affect_type:    data.affect_type,
        content_tags:   data.tags,
        confidence:     existingConfidenceRef.current,
        bound_identities: parseBindings(data.bindings),
      })
      onClose()
    } catch (e: unknown) {
      setError((e as { body?: string }).body || '更新失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{i18n.graph.editTitle}</DialogTitle>
        </DialogHeader>
        <ScrollArea className="max-h-[60vh]">
          <div className="pr-4"><PersonaForm data={data} onChange={setData} /></div>
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

// ── Edit Impression ───────────────────────────────────────────────────────

export function EditImpressionDialog({
  open, edge, onClose, onSubmit,
}: {
  open: boolean
  edge: ImpressionEdge | null
  onClose: () => void
  onSubmit: (observer: string, subject: string, scope: string, data: Record<string, unknown>) => Promise<void>
}) {
  const existingConfidenceRef = useRef<number>(0.8)
  const [relation, setRelation] = useState('')
  const [affect, setAffect] = useState(0)
  const [intensity, setIntensity] = useState(0.5)
  const [evidence, setEvidence] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (edge) {
      existingConfidenceRef.current = edge.data.confidence
      setRelation(edge.data.label || '')
      setAffect(edge.data.affect)
      setIntensity(edge.data.intensity)
      setEvidence((edge.data.evidence_event_ids || []).join(', '))
      setError('')
    }
  }, [edge])

  const handleSubmit = async () => {
    if (!edge) return
    setLoading(true); setError('')
    try {
      await onSubmit(edge.data.source, edge.data.target, edge.data.scope, {
        relation_type: relation.trim(),
        affect, intensity,
        confidence: existingConfidenceRef.current,
        scope: edge.data.scope,
        evidence_event_ids: evidence.split(',').map(s => s.trim()).filter(Boolean),
      })
      onClose()
    } catch (e: unknown) {
      setError((e as { body?: string }).body || '更新失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{i18n.graph.editImpression}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label>{i18n.graph.relationType}</Label>
            <Input value={relation} onChange={e => setRelation(e.target.value)} />
          </div>
          {[
            { label: i18n.graph.affect, val: affect, set: setAffect, min: -1, max: 1 },
            { label: i18n.graph.intensity, val: intensity, set: setIntensity, min: 0, max: 1 },
          ].map(({ label, val, set: setter, min, max }) => (
            <div key={label} className="flex flex-col gap-1.5">
              <div className="flex justify-between">
                <Label>{label}</Label>
                <span className="text-muted-foreground text-xs">
                  {val >= 0 ? '+' : ''}{val.toFixed(2)}
                </span>
              </div>
              <Slider value={[val]} onValueChange={v => setter(Array.isArray(v) ? v[0] : v)} min={min} max={max} step={0.01} />
            </div>
          ))}
          <div className="flex flex-col gap-1.5">
            <Label>{i18n.graph.evidence}</Label>
            <Input value={evidence} onChange={e => setEvidence(e.target.value)} placeholder="event_id_1, event_id_2" />
          </div>
        </div>
        {error && <p className="text-destructive text-sm">{error}</p>}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{i18n.common.cancel}</Button>
          <Button onClick={handleSubmit} disabled={loading}>{i18n.common.save}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Persona Detail Panel ──────────────────────────────────────────────────

export function PersonaDetailCard({
  node, onEdit, onDelete, sudoMode,
}: {
  node: PersonaNode | null
  onEdit: (node: PersonaNode) => void
  onDelete: (uid: string, name: string) => void
  sudoMode: boolean
}) {
  if (!node) return null
  const d = node.data
  const attrs = d.attrs || {}
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
        {[
          [i18n.graph.uid,         d.id.slice(0, 12) + '…'],
          [i18n.graph.confidence,  (d.confidence * 100).toFixed(0) + '%'],
          ...(attrs.description ? [[i18n.graph.description, attrs.description]] : []),
          ...(attrs.affect_type  ? [[i18n.graph.affectType, attrs.affect_type]]  : []),
        ].map(([k, v]) => (
          <div key={k} className="contents">
            <span className="text-muted-foreground">{k}</span>
            <span className="truncate font-medium">{v}</span>
          </div>
        ))}
      </div>
      {(attrs.content_tags?.length ?? 0) > 0 && (
        <div className="flex flex-wrap gap-1">
          {(attrs.content_tags ?? []).map(t => <Badge key={t} variant="secondary" className="text-xs">{t}</Badge>)}
        </div>
      )}
      {d.bound_identities?.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {d.bound_identities.map(b => (
            <Badge key={`${b.platform}:${b.physical_id}`} variant="outline" className="text-xs">
              {b.platform}:{b.physical_id}
            </Badge>
          ))}
        </div>
      )}
      <div className="flex gap-2 pt-2">
        <Button size="sm" variant="outline" disabled={!sudoMode} onClick={() => onEdit(node)}>
          <Pencil className="mr-1 size-3.5" />{i18n.common.edit}
        </Button>
        <Button size="sm" variant="destructive" disabled={!sudoMode} onClick={() => onDelete(d.id, d.label)}>
          <Trash2 className="mr-1 size-3.5" />{i18n.common.delete}
        </Button>
      </div>
    </div>
  )
}

// ── Impression Detail Panel ───────────────────────────────────────────────

export function ImpressionDetailCard({
  edge, onEdit, onJumpToEvent, sudoMode,
}: {
  edge: ImpressionEdge | null
  onEdit: (edge: ImpressionEdge) => void
  onJumpToEvent: (eventId: string) => void
  sudoMode: boolean
}) {
  if (!edge) return null
  const d = edge.data
  const affColor = d.affect > 0 ? 'text-green-500' : d.affect < 0 ? 'text-red-500' : 'text-muted-foreground'
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
        {[
          [i18n.graph.relationType, d.label],
          [i18n.graph.intensity,    (d.intensity * 100).toFixed(0) + '%'],
          [i18n.graph.confidence,   (d.confidence * 100).toFixed(0) + '%'],
          [i18n.graph.scope,        d.scope],
        ].map(([k, v]) => (
          <div key={k} className="contents">
            <span className="text-muted-foreground">{k}</span>
            <span className="font-medium">{v}</span>
          </div>
        ))}
        <span className="text-muted-foreground">{i18n.graph.affect}</span>
        <span className={`font-mono font-medium ${affColor}`}>
          {d.affect >= 0 ? '+' : ''}{d.affect.toFixed(2)}
        </span>
      </div>
      {d.evidence_event_ids?.length > 0 && (
        <div className="flex flex-col gap-1">
          <p className="text-muted-foreground text-xs">{i18n.graph.evidenceEvents}</p>
          {d.evidence_event_ids.map(eid => (
            <button
              key={eid}
              onClick={() => onJumpToEvent(eid)}
              className="hover:bg-accent rounded px-2 py-1 text-left text-xs transition-colors"
            >
              {eid.slice(0, 16)}…
            </button>
          ))}
        </div>
      )}
      <div className="flex gap-2 pt-2">
        <Button size="sm" variant="outline" disabled={!sudoMode} onClick={() => onEdit(edge)}>
          <Pencil className="mr-1 size-3.5" />{i18n.common.edit}
        </Button>
      </div>
    </div>
  )
}
