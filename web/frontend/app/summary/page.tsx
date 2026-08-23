'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { Pencil, Save, X, Search, RotateCcw, ScrollText, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { PageHeader } from '@/components/layout/page-header'
import { RefreshButton } from '@/components/shared/refresh-button'
import { PageEmptyOverlay } from '@/components/shared/page-empty-overlay'
import { useApp } from '@/lib/store'
import { setStored } from '@/lib/safe-storage'
import * as api from '@/lib/api'
import { cn } from '@/lib/utils'

interface SummaryState {
  key: api.SummaryKey | null
  content: string
}

const EMPTY_STATE: SummaryState = { key: null, content: '' }

function metaKey(meta: api.SummaryMeta): api.SummaryKey {
  return {
    group_id: meta.group_id,
    peer_uid: meta.peer_uid,
    persona_dir: meta.persona_dir,
    date: meta.date,
  }
}

function keyId(key: api.SummaryKey): string {
  return `${key.group_id ?? ''}|${key.peer_uid ?? ''}|${key.persona_dir}|${key.date}`
}

interface Sections {
  topic: string
  events: string
  mood: string
}

const MARKER_TOPIC = '[主要话题]'
const MARKER_EVENTS = '[事件列表]'
const MARKER_MOOD = '[情感动态]'

function parseSections(content: string): Sections {
  const topicRegex = new RegExp(`\\${MARKER_TOPIC}\\n([\\s\\S]*?)(?=\\n\\${MARKER_EVENTS}|\\n\\${MARKER_MOOD}|$)`)
  const eventsRegex = new RegExp(`\\${MARKER_EVENTS}\\n([\\s\\S]*?)(?=\\n\\${MARKER_MOOD}|$)`)
  const moodRegex = new RegExp(`\\${MARKER_MOOD}\\n([\\s\\S]*?)$`)
  
  const topicMatch = content.match(topicRegex)
  const eventsMatch = content.match(eventsRegex)
  const moodMatch = content.match(moodRegex)
  
  return {
    topic: topicMatch?.[1]?.trim() ?? content,
    events: eventsMatch?.[1]?.trim() ?? '',
    mood: moodMatch?.[1]?.trim() ?? '',
  }
}

function assembleSections(sections: Sections): string {
  const parts: string[] = []
  if (sections.topic) parts.push(`${MARKER_TOPIC}\n${sections.topic}`)
  if (sections.events) parts.push(`${MARKER_EVENTS}\n${sections.events}`)
  if (sections.mood) parts.push(`${MARKER_MOOD}\n${sections.mood}`)
  return parts.join('\n\n') + '\n'
}

export default function SummaryPage() {
  const app = useApp()
  const router = useRouter()
  const { i18n, currentPersonaName, scopeMode } = app
  const personaFilter = scopeMode === 'single'
    ? (currentPersonaName ?? api.LEGACY_PERSONA_TOKEN)
    : null
  const [summaries, setSummaries] = useState<api.SummaryMeta[]>([])
  const [current, setCurrent] = useState<SummaryState>(EMPTY_STATE)
  const [sections, setSections] = useState<Sections>({ topic: '', events: '', mood: '' })
  const [linkedEvents, setLinkedEvents] = useState<api.SummaryLinkedEvent[]>([])
  const [editing, setEditing] = useState(false)
  const [editTopic, setEditTopic] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)

  const loadSummary = useCallback(async (key: api.SummaryKey) => {
    setLoading(true)
    try {
      const { content, linked_events } = await api.summaries.get(key)
      setCurrent({ key, content })
      setSections(parseSections(content))
      setLinkedEvents(linked_events ?? [])
    } catch {
      app.toast(i18n.summary.loadError, 'destructive')
    } finally {
      setLoading(false)
    }
  }, [app, i18n.summary.loadError])

  const currentKeyRef = useRef<api.SummaryKey | null>(null)
  currentKeyRef.current = current.key

  const loadList = useCallback(async () => {
    try {
      const list = await api.summaries.list(personaFilter)
      setSummaries(list)
      // Keep the open summary if it survived the filter change, else open the newest.
      const open = currentKeyRef.current
      const stillThere = open && list.some(s => keyId(metaKey(s)) === keyId(open))
      if (!stillThere) {
        if (list.length) {
          loadSummary(metaKey(list[0]))
        } else {
          setCurrent(EMPTY_STATE)
          setSections({ topic: '', events: '', mood: '' })
          setLinkedEvents([])
        }
      }
    } catch {
      app.toast(i18n.common.error, 'destructive')
    }
  }, [app, i18n.common.error, personaFilter, loadSummary])

  useEffect(() => {
    loadList()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [personaFilter])

  const handleSave = async () => {
    const newSections = { ...sections, topic: editTopic }
    const newContent = assembleSections(newSections)
    try {
      if (!current.key) return
      await api.summaries.save(current.key, newContent)
      setCurrent(prev => ({ ...prev, content: newContent }))
      setSections(newSections)
      setEditing(false)
      app.toast(i18n.summary.saveSuccess)
    } catch (e: unknown) {
      app.toast(`${i18n.summary.saveError}: ${(e as api.ApiError).body}`, 'destructive')
    }
  }

  const handleRegenerate = async () => {
    setConfirmOpen(false)
    if (!current.key) return
    const key = current.key
    setRegenerating(true)
    try {
      const { content, linked_events } = await app.runTask(
        i18n.tasks.regenerateSummary,
        () => api.summaries.regenerate(key),
      )
      setCurrent(prev => ({ ...prev, content }))
      setSections(parseSections(content))
      setLinkedEvents(linked_events ?? [])
      setEditing(false)
    } catch {
      /* running / failure state surfaced by the TaskDock */
    } finally {
      setRegenerating(false)
    }
  }

  const handleDelete = async () => {
    setDeleteConfirmOpen(false)
    if (!current.key) return
    const id = keyId(current.key)
    try {
      await api.summaries.delete(current.key)
      app.toast(i18n.summary.deleteSuccess)
      const newList = summaries.filter(s => keyId(metaKey(s)) !== id)
      setSummaries(newList)
      if (newList.length) {
        loadSummary(metaKey(newList[0]))
      } else {
        setCurrent(EMPTY_STATE)
        setSections({ topic: '', events: '', mood: '' })
        setLinkedEvents([])
      }
      setEditing(false)
    } catch (e: unknown) {
      app.toast(`${i18n.summary.deleteFailed}: ${(e as api.ApiError).body}`, 'destructive')
    }
  }

  const filtered = summaries.filter(s =>
    !search ||
    (s.label || '').toLowerCase().includes(search.toLowerCase()) ||
    s.date.includes(search),
  )

  const KIND_ORDER: api.SummaryKind[] = ['group', 'private', 'legacy_private']
  const kindLabel: Record<api.SummaryKind, string> = {
    group: i18n.summary.kindGroup,
    private: i18n.summary.kindPrivate,
    legacy_private: i18n.summary.kindLegacy,
  }
  const grouped = KIND_ORDER
    .map(kind => ({ kind, items: filtered.filter(s => s.kind === kind) }))
    .filter(g => g.items.length > 0)
  const currentId = current.key ? keyId(current.key) : null

  const focusEvent = (eventId: string | null) => {
    if (!eventId) return
    setStored('em_focus_event', eventId, 'session')
    router.push('/events')
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

      {current.key && !editing && (
        <>
          <Button
            variant="outline"
            size="sm"
            className="h-8 gap-1.5 px-2"
            disabled={!app.sudo || regenerating}
            onClick={() => setConfirmOpen(true)}
            title={!app.sudo ? i18n.common.needSudo : undefined}
          >
            <RotateCcw className="size-3.5" />
            <span className="hidden sm:inline">
              {regenerating ? i18n.common.loading : i18n.summary.regenerate}
            </span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-8 px-2 text-destructive hover:bg-destructive/10 hover:text-destructive"
            disabled={!app.sudo}
            onClick={() => setDeleteConfirmOpen(true)}
            title={!app.sudo ? i18n.common.needSudo : undefined}
          >
            <Trash2 className="size-3.5" />
          </Button>
        </>
      )}

      {!editing ? (
        <Button
          variant="outline"
          size="sm"
          className="h-8 gap-1.5 px-2"
          disabled={!current.key || !app.sudo}
          onClick={() => { setEditing(true); setEditTopic(sections.topic) }}
        >
          <Pencil className="size-3.5" />
          <span className="hidden sm:inline">{i18n.summary.edit}</span>
        </Button>
      ) : (
        <>
          <Button variant="outline" size="sm" className="h-8 gap-1.5 px-2" onClick={() => setEditing(false)}>
            <X className="size-3.5" />
            <span className="hidden sm:inline">{i18n.summary.cancel}</span>
          </Button>
          <Button size="sm" className="h-8 gap-1.5 px-2" onClick={handleSave}>
            <Save className="size-3.5" />
            <span className="hidden sm:inline">{i18n.summary.save}</span>
          </Button>
        </>
      )}
    </div>
  )

  const globalActions = (
    <RefreshButton 
      onClick={loadList} 
      loading={loading} 
    />
  )

  return (
    <div className="flex h-svh flex-col overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-500 ease-out fill-mode-both">
      <PageHeader
        variant="loom"
        loomIssue="ΠΕΡΙΛΗΨΗ"
          loomWindow={i18n.page.summary.loomWindow}
        title={i18n.page.summary.title}
        actions={actions}
        globalActions={globalActions}
      />

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{i18n.summary.regenerateConfirmTitle}</AlertDialogTitle>
            <AlertDialogDescription>{i18n.summary.regenerateConfirmDesc}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{i18n.common.cancel}</AlertDialogCancel>
            <AlertDialogAction onClick={handleRegenerate}>{i18n.common.confirm}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{i18n.common.delete}</AlertDialogTitle>
            <AlertDialogDescription>{i18n.summary.deleteConfirm}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{i18n.common.cancel}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={handleDelete}
            >
              {i18n.common.delete}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <div className="flex flex-1 overflow-hidden min-w-0">
        <div className="bg-card border-foreground/10 flex w-56 shrink-0 flex-col border-r">
          <ScrollArea className="flex-1">
            <div className="p-2">
              {filtered.length === 0 ? (
                <p className="text-muted-foreground px-2 py-4 text-center text-xs whitespace-pre-line">
                  {i18n.summary.noneHint}
                </p>
              ) : (
                grouped.map(group => (
                  <div key={group.kind} className="mb-1">
                    <div className="text-muted-foreground px-3 pb-1 pt-2 text-[10px] font-medium tracking-wide uppercase">
                      {kindLabel[group.kind]}
                    </div>
                    {group.items.map(s => {
                      const id = keyId(metaKey(s))
                      return (
                        <button
                          key={id}
                          className={cn(
                            'w-full rounded-lg px-3 py-2 text-left text-sm transition-all duration-200',
                            currentId === id
                              ? 'bg-accent text-accent-foreground shadow-sm'
                              : 'hover:bg-muted text-muted-foreground hover:text-foreground',
                          )}
                          onClick={() => { setEditing(false); loadSummary(metaKey(s)) }}
                        >
                          <div className="truncate font-medium">{s.label}</div>
                          <div className="text-muted-foreground flex items-center gap-1.5 text-xs">
                            <span>{s.date}</span>
                            {scopeMode === 'all' && (
                              <span className="truncate opacity-70">
                                · {s.bot_persona_name ?? i18n.personaSelector.defaultPersona}
                              </span>
                            )}
                          </div>
                        </button>
                      )
                    })}
                  </div>
                ))
              )}
            </div>
          </ScrollArea>
        </div>

        <div className="flex flex-1 flex-col overflow-hidden min-w-0">
          {!current.key ? (
            <PageEmptyOverlay
              icon={ScrollText}
              title={summaries.length === 0 ? i18n.summary.noneHint.split('\n')[0] : i18n.summary.placeholder}
              description={summaries.length === 0 ? i18n.summary.noneHint.split('\n').slice(1).join(' ') : undefined}
            />
          ) : loading ? (
            <div className="text-muted-foreground flex flex-1 items-center justify-center text-sm animate-pulse">
              {i18n.common.loading}
            </div>
          ) : (
            <ScrollArea className="flex-1">
              <div 
                key={current.key ? keyId(current.key) : 'none'}
                className="flex flex-col gap-4 p-6 animate-in fade-in slide-in-from-right-4 duration-300 ease-out"
              >

                {/* [主要话题] — editable */}
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold">[{i18n.summary.sectionTopic}]</span>
                  </div>
                  {editing ? (
                    <Textarea
                      className="min-h-[120px] resize-none font-mono text-sm"
                      value={editTopic}
                      onChange={e => setEditTopic(e.target.value)}
                      placeholder={i18n.summary.topicPlaceholder}
                    />
                  ) : (
                    <div className="text-sm leading-relaxed whitespace-pre-wrap rounded-md border bg-muted/30 px-3 py-2">
                      {sections.topic || <span className="text-muted-foreground italic">{i18n.summary.noTopic}</span>}
                    </div>
                  )}
                </div>

                {/* [事件列表] — read-only */}
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold">[{i18n.summary.sectionEvents}]</span>
                    <Badge variant="secondary" className="text-xs px-1.5 py-0">{i18n.summary.readOnly}</Badge>
                  </div>
                  <div className="rounded-md border bg-muted/30 px-3 py-2">
                    {linkedEvents.length > 0 ? (
                      <div className="flex flex-col gap-1.5">
                        {linkedEvents.map((item, index) => (
                          <button
                            key={`${item.ref}-${index}`}
                            type="button"
                            disabled={!item.event_id}
                            onClick={() => focusEvent(item.event_id)}
                            className={cn(
                              'group flex w-full min-w-0 items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors',
                              item.event_id
                                ? 'hover:bg-background hover:text-foreground'
                                : 'cursor-default opacity-60',
                            )}
                            title={item.event_id ? item.event_id : undefined}
                          >
                            <Badge variant={item.resolved ? 'secondary' : 'outline'} className="shrink-0 font-mono text-[10px]">
                              {item.ref}
                            </Badge>
                            <span className="min-w-0 flex-1 truncate font-medium">
                              {item.topic || item.title || i18n.summary.noEvents}
                            </span>
                            {item.event_id && (
                              <span className="text-muted-foreground shrink-0 text-[10px] opacity-0 transition-opacity group-hover:opacity-100">
                                Event
                              </span>
                            )}
                          </button>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm font-mono leading-relaxed break-all whitespace-pre-wrap">
                        {sections.events || <span className="text-muted-foreground italic">{i18n.summary.noEvents}</span>}
                      </p>
                    )}
                  </div>
                </div>

                {/* [情感动态] — read-only */}
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold">[{i18n.summary.sectionMood}]</span>
                    <Badge variant="secondary" className="text-xs px-1.5 py-0">{i18n.summary.readOnly}</Badge>
                  </div>
                  <div className="rounded-md border bg-muted/30 px-3 py-2">
                    <p className="text-sm leading-relaxed whitespace-pre-wrap">
                      {sections.mood || <span className="text-muted-foreground italic">{i18n.summary.noMood}</span>}
                    </p>
                  </div>
                </div>

              </div>
            </ScrollArea>
          )}
        </div>
      </div>
    </div>
  )
}
