'use client'

import { useState, useEffect, useRef } from 'react'
import { Pencil, Trash2 } from 'lucide-react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Slider } from '@/components/ui/slider'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/spinner'
import { FieldGroup, Field, FieldLabel, FieldContent, FieldDescription } from '@/components/ui/field'
import { TagSelector } from '@/components/shared/tag-selector'
import { type PersonaNode, type ImpressionEdge } from '@/lib/api'
import { useApp } from '@/lib/store'
import { getLocalizedOrientation } from '@/lib/i18n'

// ── Persona Form ─────────────────────────────────────────────────────────

interface PersonaFormData {
  name: string
  description: string
  tags: string[]
  bindings: string
}

function PersonaForm({ data, onChange }: { data: PersonaFormData; onChange: (d: PersonaFormData) => void }) {
  const { i18n } = useApp()
  const set = <K extends keyof PersonaFormData>(k: K, v: PersonaFormData[K]) =>
    onChange({ ...data, [k]: v })

  return (
    <FieldGroup>
      <Field>
        <FieldLabel htmlFor="p-name">{i18n.graph.name} *</FieldLabel>
        <FieldContent>
          <Input id="p-name" value={data.name} onChange={e => set('name', e.target.value)} />
        </FieldContent>
      </Field>

      <Field>
        <FieldLabel htmlFor="p-desc">{i18n.graph.description}</FieldLabel>
        <FieldContent>
          <Input id="p-desc" value={data.description} onChange={e => set('description', e.target.value)} />
        </FieldContent>
      </Field>

      <Field>
        <FieldLabel>{i18n.graph.contentTags}</FieldLabel>
        <FieldContent>
          <TagSelector value={data.tags} onChange={v => set('tags', v)} />
        </FieldContent>
      </Field>

      <Field>
        <FieldLabel htmlFor="p-bindings">{i18n.graph.bindings}</FieldLabel>
        <FieldContent>
          <textarea
            id="p-bindings"
            className="border-input bg-transparent text-foreground focus-visible:border-ring focus-visible:ring-ring/50 min-h-16 w-full rounded-lg border px-2.5 py-2 text-sm outline-none focus-visible:ring-3"
            value={data.bindings}
            onChange={e => set('bindings', e.target.value)}
            placeholder="platform:id&#10;telegram:12345"
          />
        </FieldContent>
      </Field>
    </FieldGroup>
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
  const { i18n } = useApp()
  const [data, setData] = useState<PersonaFormData>({
    name: '', description: '', tags: [], bindings: '',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async () => {
    if (!data.name.trim()) { setError(i18n.graph.nameRequired); return }
    setLoading(true); setError('')
    try {
      await onSubmit({
        primary_name: data.name.trim(),
        description: data.description.trim(),
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
          <DialogDescription>{i18n.graph.createPersonaDesc}</DialogDescription>
        </DialogHeader>
        <ScrollArea className="max-h-[60vh]">
          <div className="pr-4"><PersonaForm data={data} onChange={setData} /></div>
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

// ── Edit Persona ──────────────────────────────────────────────────────────

export function EditPersonaDialog({
  open, node, onClose, onSubmit,
}: {
  open: boolean
  node: PersonaNode | null
  onClose: () => void
  onSubmit: (uid: string, data: Record<string, unknown>) => Promise<void>
}) {
  const { i18n } = useApp()
  const [data, setData] = useState<PersonaFormData>({
    name: '', description: '', tags: [], bindings: '',
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
        tags:        d.attrs?.content_tags || [],
        bindings:    (d.bound_identities || []).map(b => `${b.platform}:${b.physical_id}`).join('\n'),
      })
      setError('')
    }
  }, [node])

  const handleSubmit = async () => {
    if (!node) return
    if (!data.name.trim()) { setError(i18n.graph.nameRequired); return }
    setLoading(true); setError('')
    try {
      await onSubmit(node.data.id, {
        primary_name:   data.name.trim(),
        description:    data.description.trim(),
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
          <DialogDescription>{i18n.graph.editPersonaDesc}</DialogDescription>
        </DialogHeader>
        <ScrollArea className="max-h-[60vh]">
          <div className="pr-4">
            <PersonaForm data={data} onChange={setData} />
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

// ── Edit Impression ───────────────────────────────────────────────────────

export function EditImpressionDialog({
  open, edge, onClose, onSubmit,
}: {
  open: boolean
  edge: ImpressionEdge | null
  onClose: () => void
  onSubmit: (observer: string, subject: string, scope: string, data: Record<string, unknown>) => Promise<void>
}) {
  const { i18n } = useApp()
  const existingConfidenceRef = useRef<number>(0.8)
  const [orientation, setOrientation] = useState('')
  const [benevolence, setBenevolence] = useState(0)
  const [power, setPower] = useState(0)
  const [intensity, setIntensity] = useState(0.5)
  const [rSquared, setRSquared] = useState(0.7)
  const [evidence, setEvidence] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (edge) {
      existingConfidenceRef.current = edge.data.confidence
      setOrientation(edge.data.label || '')
      setBenevolence(edge.data.affect)
      setPower(edge.data.power)
      setIntensity(edge.data.intensity)
      setRSquared(edge.data.r_squared)
      setEvidence((edge.data.evidence_event_ids || []).join(', '))
      setError('')
    }
  }, [edge])

  const handleSubmit = async () => {
    if (!edge) return
    setLoading(true); setError('')
    try {
      await onSubmit(edge.data.source, edge.data.target, edge.data.scope, {
        relation_type: orientation.trim(),
        affect: benevolence,
        power: power,
        intensity: intensity,
        r_squared: rSquared,
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
          <DialogDescription>{i18n.graph.editImpressionDesc}</DialogDescription>
        </DialogHeader>
        <FieldGroup>
          <Field>
            <FieldLabel>{i18n.graph.relationType}</FieldLabel>
            <FieldContent>
              <Input value={orientation} onChange={e => setOrientation(e.target.value)} />
            </FieldContent>
          </Field>
          
          {[
            { label: i18n.graph.affect, val: benevolence, set: setBenevolence, min: -1, max: 1 },
            { label: i18n.graph.power, val: power, set: setPower, min: -1, max: 1 },
            { label: i18n.graph.intensity, val: intensity, set: setIntensity, min: 0, max: 1 },
            { label: `${i18n.graph.fitConfidence} (R²)`, val: rSquared, set: setRSquared, min: 0, max: 1 },
          ].map(({ label, val, set: setter, min, max }) => (
            <Field key={label}>
              <div className="flex justify-between">
                <FieldLabel>{label}</FieldLabel>
                <span className="text-muted-foreground text-xs">
                  {val >= 0 ? '+' : ''}{val.toFixed(2)}
                </span>
              </div>
              <FieldContent>
                <Slider value={[val]} onValueChange={v => setter(Array.isArray(v) ? v[0] : v)} min={min} max={max} step={0.01} />
              </FieldContent>
            </Field>
          ))}

          <Field>
            <FieldLabel>{i18n.graph.evidence}</FieldLabel>
            <FieldContent>
              <Input value={evidence} onChange={e => setEvidence(e.target.value)} placeholder="event_id_1, event_id_2" />
            </FieldContent>
          </Field>
        </FieldGroup>
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

// ── Persona Detail Panel ──────────────────────────────────────────────────

export function PersonaDetailCard({
  node, onEdit, onDelete, sudoMode,
}: {
  node: PersonaNode | null
  onEdit: (node: PersonaNode) => void
  onDelete: (uid: string, name: string) => void
  sudoMode: boolean
}) {
  const { i18n } = useApp()
  if (!node) return null
  const d = node.data
  const attrs = d.attrs || {}
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
        {[
          [i18n.graph.uid,         d.id.slice(0, 12) + '…'],
          [i18n.graph.confidence,  (d.confidence * 100).toFixed(0) + '%'],
        ].map(([k, v]) => (
          <div key={k} className="contents">
            <span className="text-muted-foreground">{k}</span>
            <span className="truncate font-medium">{v}</span>
          </div>
        ))}
      </div>
      {(attrs.description || attrs.big_five) && (() => {
        return (
          <div className="rounded-lg border bg-muted/40 px-3 py-2 flex flex-col gap-2">
            <p className="text-xs font-medium">{i18n.graph.personalityBlock}</p>
            {attrs.description && <p className="text-xs text-foreground/80">{attrs.description}</p>}
            {attrs.big_five && (() => {
              const evRaw = attrs.big_five_evidence
              return (
                <div className="flex flex-col gap-1.5">
                  {(['O','C','E','A','N'] as const).map(dim => {
                    const val = attrs.big_five?.[dim]
                    if (val === undefined) return null
                    const score = Math.round((val + 1) / 2 * 100)
                    const color = score >= 65 ? 'text-green-500' : score <= 35 ? 'text-red-500' : 'text-muted-foreground'
                    const evText = evRaw && typeof evRaw === 'object' ? evRaw[dim] : undefined
                    return (
                      <div key={dim} className="flex flex-col gap-0.5">
                        <div className="flex items-center justify-between text-xs gap-2">
                          <span className="text-muted-foreground shrink-0">{i18n.graph.bigFive[dim as keyof typeof i18n.graph.bigFive]}</span>
                          <span className={`font-mono font-medium ${color}`}>{score}%</span>
                        </div>
                        {evText && <p className="text-[10px] italic text-muted-foreground leading-snug">{evText}</p>}
                      </div>
                    )
                  })}
                  {evRaw && typeof evRaw === 'string' && (
                    <p className="text-[10px] italic text-muted-foreground leading-snug">{evRaw}</p>
                  )}
                </div>
              )
            })()}
          </div>
        )
      })()}
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
          <Pencil data-icon="inline-start" />{i18n.common.edit}
        </Button>
        <Button size="sm" variant="destructive" disabled={!sudoMode} onClick={() => onDelete(d.id, d.label)}>
          <Trash2 data-icon="inline-start" />{i18n.common.delete}
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
  const { i18n } = useApp()
  if (!edge) return null
  const d = edge.data
  const affColor = d.affect > 0 ? 'text-green-500' : d.affect < 0 ? 'text-red-500' : 'text-muted-foreground'
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
        {[
          [i18n.graph.relationType, getLocalizedOrientation(d.label, i18n)],
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
            <Button
              key={eid}
              variant="ghost"
              size="sm"
              onClick={() => onJumpToEvent(eid)}
              className="w-full justify-start h-8 px-2 font-mono text-[10px]"
            >
              {eid.slice(0, 16)}…
            </Button>
          ))}
        </div>
      )}
      <div className="flex gap-2 pt-2">
        <Button size="sm" variant="outline" disabled={!sudoMode} onClick={() => onEdit(edge)}>
          <Pencil data-icon="inline-start" />{i18n.common.edit}
        </Button>
      </div>
    </div>
  )
}
