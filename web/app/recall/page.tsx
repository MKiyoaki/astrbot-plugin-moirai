'use client'

import { useState } from 'react'
import { Search as SearchIcon } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { PageHeader } from '@/components/layout/page-header'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useApp } from '@/lib/store'
import * as api from '@/lib/api'
import { i18n } from '@/lib/i18n'

interface RecallItem extends api.ApiEvent {}

export default function RecallPage() {
  const app = useApp()
  const [query, setQuery] = useState('')
  const [limit, setLimit] = useState(5)
  const [sessionId, setSessionId] = useState('')
  const [results, setResults] = useState<RecallItem[]>([])
  const [meta, setMeta] = useState<{ count: number; algorithm: string } | null>(null)
  const [searching, setSearching] = useState(false)
  const [searched, setSearched] = useState(false)

  const handleRecall = async () => {
    if (!query.trim()) { app.toast('请输入查询内容', 'destructive'); return }
    setSearching(true)
    try {
      const data = await api.recall.query(query.trim(), limit, sessionId.trim() || undefined)
      setResults(data.items || [])
      setMeta({ count: data.count, algorithm: data.algorithm })
      setSearched(true)
    } catch (e: unknown) {
      app.toast(i18n.recall.error + '：' + (e as api.ApiError).body, 'destructive')
    } finally {
      setSearching(false)
    }
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <PageHeader
        title={i18n.page.recall.title}
        description={i18n.page.recall.description}
      />

      <div className="flex flex-1 flex-col gap-4 overflow-hidden p-6">
        {/* Search card */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{i18n.recall.title}</CardTitle>
            <CardDescription>{i18n.recall.hint}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {/* Query input — large textarea */}
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="recall-input">查询内容</Label>
              <Textarea
                id="recall-input"
                className="min-h-24 resize-y text-sm"
                placeholder={i18n.recall.placeholder}
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    handleRecall()
                  }
                }}
              />
            </div>

            {/* Controls row */}
            <div className="flex flex-wrap items-end gap-3">
              {/* Result count */}
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="recall-limit">{i18n.recall.resultCount}</Label>
                <Input
                  id="recall-limit"
                  type="number"
                  min={1}
                  max={50}
                  value={limit}
                  onChange={e => {
                    const v = parseInt(e.target.value, 10)
                    if (v > 0) setLimit(v)
                  }}
                  className="w-24"
                />
              </div>

              {/* Optional session ID */}
              <div className="flex min-w-48 flex-col gap-1.5">
                <Label htmlFor="recall-session">{i18n.recall.sessionId}</Label>
                <Input
                  id="recall-session"
                  value={sessionId}
                  onChange={e => setSessionId(e.target.value)}
                  placeholder="（可选）"
                  className="font-mono text-xs"
                />
              </div>

              <Button
                className="min-w-24"
                onClick={handleRecall}
                disabled={searching}
              >
                <SearchIcon className="mr-1.5 size-4" />
                {searching ? '查询中…' : i18n.recall.recall}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Results */}
        {searched && (
          <div className="flex min-h-0 flex-1 flex-col gap-2">
            {meta && (
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground text-sm">
                  找到 <strong>{meta.count}</strong> 条
                </span>
                <Badge variant="outline" className="font-mono text-xs">{meta.algorithm || 'fts5'}</Badge>
              </div>
            )}
            <ScrollArea className="flex-1">
              {results.length === 0 ? (
                <p className="text-muted-foreground py-8 text-center text-sm">{i18n.recall.noResults}</p>
              ) : (
                <div className="flex flex-col gap-2 pr-2">
                  {results.map(ev => (
                    <div
                      key={ev.id}
                      className="bg-card ring-foreground/10 rounded-xl p-3 ring-1 transition-shadow hover:ring-2"
                    >
                      <div className="mb-1 font-medium text-sm">{ev.content || ev.topic || ev.id}</div>
                      <div className="text-muted-foreground flex flex-wrap items-center gap-2 text-xs">
                        <span>{new Date(ev.start).toLocaleDateString('zh-CN')}</span>
                        <span>{ev.group || i18n.events.privateChat}</span>
                        <span>{i18n.recall.importance} {(ev.salience * 100).toFixed(0)}%</span>
                        {(ev.tags || []).slice(0, 3).map(t => (
                          <Badge key={t} variant="secondary" className="text-xs">{t}</Badge>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </ScrollArea>
          </div>
        )}

        {!searched && (
          <div className="text-muted-foreground flex flex-1 items-center justify-center text-sm">
            {i18n.recall.hint}
          </div>
        )}
      </div>
    </div>
  )
}
