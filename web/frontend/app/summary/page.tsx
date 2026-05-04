'use client'

import { useEffect, useState, useCallback } from 'react'
import { Pencil, RefreshCw, Save, X, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { PageHeader } from '@/components/layout/page-header'
import { useApp } from '@/lib/store'
import * as api from '@/lib/api'
import { i18n } from '@/lib/i18n'
import { cn } from '@/lib/utils'

interface SummaryState {
  groupId: string | null
  date: string
  content: string
}

export default function SummaryPage() {
  const app = useApp()
  const [summaries, setSummaries] = useState<api.SummaryMeta[]>([])
  const [current, setCurrent] = useState<SummaryState>({ groupId: null, date: '', content: '' })
  const [editing, setEditing] = useState(false)
  const [editContent, setEditContent] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(false)
  const [renderedHtml, setRenderedHtml] = useState('')

  const loadList = useCallback(async () => {
    try {
      const list = await api.summaries.list()
      setSummaries(list)
      if (list.length && !current.date) {
        loadSummary(list[0].group_id, list[0].date)
      }
    } catch {
      app.toast('加载失败', 'destructive')
    }
  }, [app, current.date]) // eslint-disable-line

  useEffect(() => {
    loadList()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const loadSummary = async (groupId: string | null, date: string) => {
    setLoading(true)
    try {
      const { content } = await api.summaries.get(groupId, date)
      setCurrent({ groupId, date, content })
      renderMarkdown(content)
    } catch {
      app.toast('摘要加载失败', 'destructive')
    } finally {
      setLoading(false)
    }
  }

  const renderMarkdown = async (content: string) => {
    try {
      const { marked } = await import('marked')
      setRenderedHtml(marked.parse(content) as string)
    } catch {
      setRenderedHtml(`<pre>${content}</pre>`)
    }
  }

  const handleSave = async () => {
    try {
      await api.summaries.save(current.groupId, current.date, editContent)
      setCurrent(prev => ({ ...prev, content: editContent }))
      setEditing(false)
      renderMarkdown(editContent)
      app.toast(i18n.summary.saveSuccess)
    } catch (e: unknown) {
      app.toast(i18n.summary.saveError + '：' + (e as api.ApiError).body, 'destructive')
    }
  }

  const filtered = summaries.filter(s =>
    !search ||
    (s.label || '').toLowerCase().includes(search.toLowerCase()) ||
    s.date.includes(search),
  )

  const actions = (
    <div className="flex items-center gap-2">
      <div className="relative">
        <Search className="text-muted-foreground pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2" />
        <Input
          className="h-7 w-40 pl-7 text-xs"
          placeholder={i18n.summary.search}
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>
      {!editing ? (
        <Button
          variant="outline"
          size="sm"
          disabled={!current.date || !app.sudo}
          onClick={() => { setEditing(true); setEditContent(current.content) }}
        >
          <Pencil className="mr-1 size-3.5" />{i18n.summary.edit}
        </Button>
      ) : (
        <>
          <Button variant="outline" size="sm" onClick={() => setEditing(false)}>
            <X className="mr-1 size-3.5" />{i18n.summary.cancel}
          </Button>
          <Button size="sm" onClick={handleSave}>
            <Save className="mr-1 size-3.5" />{i18n.summary.save}
          </Button>
        </>
      )}
      <Button variant="ghost" size="icon" onClick={loadList} title={i18n.common.refresh}>
        <RefreshCw />
      </Button>
    </div>
  )

  return (
    // Replaced h-full with w-full flex-1 h-full min-w-0 to constrain width bounds
    <div className="flex w-full flex-1 h-full flex-col min-w-0 overflow-hidden">
      <PageHeader
        title={i18n.page.summary.title}
        description={i18n.page.summary.description}
        actions={actions}
      />

      <div className="flex flex-1 overflow-hidden min-w-0">
        <div className="bg-card border-foreground/10 flex w-56 shrink-0 flex-col border-r">
          <ScrollArea className="flex-1">
            <div className="p-2">
              {filtered.length === 0 ? (
                <p className="text-muted-foreground px-2 py-4 text-center text-xs">
                  {i18n.summary.noneHint}
                </p>
              ) : (
                filtered.map(s => (
                  <button
                    key={`${s.group_id ?? ''}-${s.date}`}
                    className={cn(
                      'w-full rounded-lg px-3 py-2 text-left text-sm transition-colors',
                      current.date === s.date && current.groupId === s.group_id
                        ? 'bg-accent text-accent-foreground'
                        : 'hover:bg-muted',
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

        {/* Added min-w-0 to prevent long markdown lines from expanding the flex item */}
        <div className="flex flex-1 flex-col overflow-hidden min-w-0">
          {!current.date ? (
            <div className="text-muted-foreground flex flex-1 items-center justify-center text-sm">
              {i18n.summary.placeholder}
            </div>
          ) : loading ? (
            <div className="text-muted-foreground flex flex-1 items-center justify-center text-sm">
              {i18n.common.loading}
            </div>
          ) : editing ? (
            <div className="flex flex-1 flex-col gap-0 overflow-hidden p-4 min-w-0">
              <Textarea
                className="min-h-0 flex-1 resize-none font-mono text-sm"
                value={editContent}
                onChange={e => setEditContent(e.target.value)}
                placeholder="Markdown 内容…"
              />
            </div>
          ) : (
            <ScrollArea className="flex-1">
              <div
                className="prose dark:prose-invert max-w-none p-6 break-words w-full"
                dangerouslySetInnerHTML={{ __html: renderedHtml || `<p class="text-muted-foreground text-sm">${i18n.summary.placeholder}</p>` }}
              />
            </ScrollArea>
          )}
        </div>
      </div>
    </div>
  )
}