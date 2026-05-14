'use client'

import { useEffect, useState, useCallback } from 'react'
import { Pencil, Save, X, Search, RotateCcw, ScrollText } from 'lucide-react'
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
import { EmptyState } from '@/components/shared/empty-state'
import { useApp } from '@/lib/store'
import * as api from '@/lib/api'
import { cn } from '@/lib/utils'

interface SummaryState {
  groupId: string | null
  date: string
  content: string
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
  const { i18n } = app
  const [summaries, setSummaries] = useState<api.SummaryMeta[]>([])
  const [current, setCurrent] = useState<SummaryState>({ groupId: null, date: '', content: '' })
  const [sections, setSections] = useState<Sections>({ topic: '', events: '', mood: '' })
  const [editing, setEditing] = useState(false)
  const [editTopic, setEditTopic] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)

  const loadList = useCallback(async () => {
    try {
      const list = await api.summaries.list()
      setSummaries(list)
      if (list.length && !current.date) {
        loadSummary(list[0].group_id, list[0].date)
      }
    } catch {
      app.toast(i18n.common.error, 'destructive')
    }
  }, [app, current.date, i18n.common.error]) // eslint-disable-line

  useEffect(() => {
    loadList()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const loadSummary = async (groupId: string | null, date: string) => {
    setLoading(true)
    try {
      const { content } = await api.summaries.get(groupId, date)
      setCurrent({ groupId, date, content })
      setSections(parseSections(content))
    } catch {
      app.toast(i18n.summary.loadError, 'destructive')
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    const newSections = { ...sections, topic: editTopic }
    const newContent = assembleSections(newSections)
    try {
      await api.summaries.save(current.groupId, current.date, newContent)
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
    setRegenerating(true)
    try {
      const { content } = await api.summaries.regenerate(current.groupId, current.date)
      setCurrent(prev => ({ ...prev, content }))
      setSections(parseSections(content))
      setEditing(false)
      app.toast(i18n.summary.regenerateSuccess)
    } catch (e: unknown) {
      app.toast(`${i18n.summary.regenerateError}: ${(e as api.ApiError).body}`, 'destructive')
    } finally {
      setRegenerating(false)
    }
  }

  const filtered = summaries.filter(s =>
    !search ||
    (s.label || '').toLowerCase().includes(search.toLowerCase()) ||
    s.date.includes(search),
  )

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

      {current.date && !editing && (
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
      )}

      {!editing ? (
        <Button
          variant="outline"
          size="sm"
          className="h-8 gap-1.5 px-2"
          disabled={!current.date || !app.sudo}
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
    <div className="flex w-full flex-1 h-full flex-col min-w-0 overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-500 ease-out fill-mode-both">
      <PageHeader
        title={i18n.page.summary.title}
        description={i18n.page.summary.description}
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

      <div className="flex flex-1 overflow-hidden min-w-0">
        <div className="bg-card border-foreground/10 flex w-56 shrink-0 flex-col border-r">
          <ScrollArea className="flex-1">
            <div className="p-2">
              {filtered.length === 0 ? (
                <p className="text-muted-foreground px-2 py-4 text-center text-xs whitespace-pre-line">
                  {i18n.summary.noneHint}
                </p>
              ) : (
                filtered.map(s => (
                  <button
                    key={`${s.group_id ?? ''}-${s.date}`}
                    className={cn(
                      'w-full rounded-lg px-3 py-2 text-left text-sm transition-all duration-200',
                      current.date === s.date && current.groupId === s.group_id
                        ? 'bg-accent text-accent-foreground shadow-sm'
                        : 'hover:bg-muted text-muted-foreground hover:text-foreground',
                    )}
                    onClick={() => { setEditing(false); loadSummary(s.group_id, s.date) }}
                  >
                    <div className="truncate font-medium">{s.label}</div>
                    <div className="text-muted-foreground text-xs">{s.date}</div>
                  </button>
                ))
              )}
            </div>
          </ScrollArea>
        </div>

        <div className="flex flex-1 flex-col overflow-hidden min-w-0">
          {!current.date ? (
            <EmptyState
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
                key={`${current.groupId}-${current.date}`}
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
                    <p className="text-sm font-mono leading-relaxed break-all whitespace-pre-wrap">
                      {sections.events || <span className="text-muted-foreground italic">{i18n.summary.noEvents}</span>}
                    </p>
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
