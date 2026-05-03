'use client'

import { useEffect, useState, useCallback, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import { Tag, Users, Building2, Activity, Clock, Search } from 'lucide-react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { PageHeader } from '@/components/layout/page-header'
import { useApp } from '@/lib/store'
import * as api from '@/lib/api'
import { i18n } from '@/lib/i18n'

function LibraryContent() {
  const searchParams = useSearchParams()
  const app = useApp()
  const defaultTab = searchParams.get('tab') || 'tags'
  const [tab, setTab] = useState(defaultTab)
  const [search, setSearch] = useState('')

  const [tagList, setTagList] = useState<{ name: string; count: number }[]>([])
  const [personaList, setPersonaList] = useState<api.PersonaNode[]>([])
  const [groupList, setGroupList] = useState<{ id: string; event_count: number; last_active?: string }[]>([])
  const [eventList, setEventList] = useState<api.ApiEvent[]>([])

  const loadData = useCallback(async () => {
    const [tagsData, graphData, eventsData] = await Promise.allSettled([
      api.tags.list(),
      api.graph.get(),
      api.events.list(500),
    ])
    if (tagsData.status === 'fulfilled') setTagList(tagsData.value.tags)
    if (graphData.status === 'fulfilled') {
      setPersonaList(graphData.value.nodes)
      app.setRawGraph(graphData.value)
      // Extract groups from events
    }
    if (eventsData.status === 'fulfilled') {
      setEventList(eventsData.value.items)
      // Aggregate groups
      const groups = new Map<string, { id: string; event_count: number; last_active?: string }>()
      eventsData.value.items.forEach(ev => {
        if (!ev.group) return
        const existing = groups.get(ev.group)
        if (!existing) {
          groups.set(ev.group, { id: ev.group, event_count: 1, last_active: ev.start })
        } else {
          existing.event_count++
          if (!existing.last_active || ev.start > existing.last_active) {
            existing.last_active = ev.start
          }
        }
      })
      setGroupList(Array.from(groups.values()).sort((a, b) => (b.last_active || '') > (a.last_active || '') ? 1 : -1))
    }
  }, [app])

  useEffect(() => {
    loadData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Sync tab from URL
  useEffect(() => {
    const t = searchParams.get('tab')
    if (t) setTab(t)
  }, [searchParams])

  const q = search.toLowerCase()

  const filteredTags = tagList.filter(t => !q || t.name.toLowerCase().includes(q))
  const filteredPersonas = personaList.filter(n =>
    !q || (n.data.label || '').toLowerCase().includes(q) ||
    (n.data.attrs?.description || '').toLowerCase().includes(q),
  )
  const filteredGroups = groupList.filter(g => !q || g.id.toLowerCase().includes(q))
  const filteredEvents = eventList.filter(ev =>
    !q ||
    (ev.content || '').toLowerCase().includes(q) ||
    (ev.topic || '').toLowerCase().includes(q) ||
    (ev.group || '').toLowerCase().includes(q) ||
    (ev.tags || []).some(t => t.toLowerCase().includes(q)),
  )

  const actions = (
    <div className="relative">
      <Search className="text-muted-foreground pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2" />
      <Input
        className="h-7 w-48 pl-7 text-xs"
        placeholder={i18n.common.search + '…'}
        value={search}
        onChange={e => setSearch(e.target.value)}
      />
    </div>
  )

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <PageHeader
        title={i18n.page.library.title}
        description={i18n.page.library.description}
        actions={actions}
      />

      <div className="flex flex-1 flex-col overflow-hidden p-6">
        <Tabs value={tab} onValueChange={setTab} className="flex flex-1 flex-col overflow-hidden">
          <TabsList className="mb-4 shrink-0">
            <TabsTrigger value="tags">
              <Tag className="mr-1.5 size-3.5" />{i18n.library.tabs.tags}
            </TabsTrigger>
            <TabsTrigger value="personas">
              <Users className="mr-1.5 size-3.5" />{i18n.library.tabs.personas}
            </TabsTrigger>
            <TabsTrigger value="groups">
              <Building2 className="mr-1.5 size-3.5" />{i18n.library.tabs.groups}
            </TabsTrigger>
            <TabsTrigger value="events">
              <Activity className="mr-1.5 size-3.5" />{i18n.library.tabs.events}
            </TabsTrigger>
            <TabsTrigger value="time">
              <Clock className="mr-1.5 size-3.5" />{i18n.library.tabs.time}
            </TabsTrigger>
          </TabsList>

          {/* TAGS */}
          <TabsContent value="tags" className="flex-1 overflow-hidden">
            <ScrollArea className="h-full">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
                {filteredTags.length === 0 ? (
                  <p className="text-muted-foreground col-span-full py-8 text-center text-sm">
                    {i18n.library.tags.noTags}
                  </p>
                ) : (
                  filteredTags.map(t => (
                    <Card key={t.name} size="sm">
                      <CardContent className="flex items-center justify-between pt-3">
                        <div>
                          <div className="flex items-center gap-1.5">
                            <Tag className="text-muted-foreground size-3.5" />
                            <span className="text-sm font-medium">{t.name}</span>
                          </div>
                          <p className="text-muted-foreground text-xs">{t.count} 次</p>
                        </div>
                      </CardContent>
                    </Card>
                  ))
                )}
              </div>
            </ScrollArea>
          </TabsContent>

          {/* PERSONAS */}
          <TabsContent value="personas" className="flex-1 overflow-hidden">
            <ScrollArea className="h-full">
              <div className="overflow-hidden rounded-xl ring-1 ring-foreground/10">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>名称</TableHead>
                      <TableHead>{i18n.graph.description}</TableHead>
                      <TableHead>{i18n.graph.affectType}</TableHead>
                      <TableHead>{i18n.graph.confidence}</TableHead>
                      <TableHead>最后活跃</TableHead>
                      <TableHead>{i18n.events.tags}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredPersonas.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} className="text-muted-foreground text-center">
                          {i18n.library.personas.noPersonas}
                        </TableCell>
                      </TableRow>
                    ) : (
                      filteredPersonas.map(n => {
                        const d = n.data
                        const attrs = d.attrs || {}
                        return (
                          <TableRow key={d.id}>
                            <TableCell className="font-medium">
                              {d.label}
                              {d.is_bot && (
                                <Badge variant="secondary" className="ml-1.5 text-xs">Bot</Badge>
                              )}
                            </TableCell>
                            <TableCell className="max-w-48 truncate text-sm">
                              {attrs.description || '—'}
                            </TableCell>
                            <TableCell className="text-sm">{attrs.affect_type || '—'}</TableCell>
                            <TableCell className="text-sm">{(d.confidence * 100).toFixed(0)}%</TableCell>
                            <TableCell className="text-sm">
                              {d.last_active_at ? new Date(d.last_active_at).toLocaleDateString('zh-CN') : '—'}
                            </TableCell>
                            <TableCell>
                              <div className="flex flex-wrap gap-1">
                                {(attrs.content_tags || []).slice(0, 3).map(t => (
                                  <Badge key={t} variant="secondary" className="text-xs">{t}</Badge>
                                ))}
                              </div>
                            </TableCell>
                          </TableRow>
                        )
                      })
                    )}
                  </TableBody>
                </Table>
              </div>
            </ScrollArea>
          </TabsContent>

          {/* GROUPS */}
          <TabsContent value="groups" className="flex-1 overflow-hidden">
            <ScrollArea className="h-full">
              <div className="overflow-hidden rounded-xl ring-1 ring-foreground/10">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{i18n.library.groups.groupId}</TableHead>
                      <TableHead>{i18n.library.groups.events}</TableHead>
                      <TableHead>{i18n.library.groups.lastActive}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredGroups.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={3} className="text-muted-foreground text-center">
                          {i18n.library.groups.noGroups}
                        </TableCell>
                      </TableRow>
                    ) : (
                      filteredGroups.map(g => (
                        <TableRow key={g.id}>
                          <TableCell className="font-mono text-sm">{g.id}</TableCell>
                          <TableCell className="text-sm">{g.event_count}</TableCell>
                          <TableCell className="text-sm">
                            {g.last_active ? new Date(g.last_active).toLocaleDateString('zh-CN') : '—'}
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </ScrollArea>
          </TabsContent>

          {/* EVENTS */}
          <TabsContent value="events" className="flex-1 overflow-hidden">
            <ScrollArea className="h-full">
              <div className="overflow-hidden rounded-xl ring-1 ring-foreground/10">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{i18n.events.topic}</TableHead>
                      <TableHead>{i18n.events.group}</TableHead>
                      <TableHead>{i18n.events.time}</TableHead>
                      <TableHead>{i18n.events.salience}</TableHead>
                      <TableHead>{i18n.events.tags}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredEvents.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={5} className="text-muted-foreground text-center">
                          {i18n.common.noData}
                        </TableCell>
                      </TableRow>
                    ) : (
                      filteredEvents
                        .sort((a, b) => new Date(b.start).getTime() - new Date(a.start).getTime())
                        .map(ev => (
                          <TableRow key={ev.id}>
                            <TableCell className="max-w-60 truncate font-medium">
                              {ev.content || ev.topic || ev.id}
                            </TableCell>
                            <TableCell className="text-sm">{ev.group || i18n.events.privateChat}</TableCell>
                            <TableCell className="text-sm">
                              {new Date(ev.start).toLocaleDateString('zh-CN')}
                            </TableCell>
                            <TableCell className="text-sm">{(ev.salience * 100).toFixed(0)}%</TableCell>
                            <TableCell>
                              <div className="flex flex-wrap gap-1">
                                {(ev.tags || []).slice(0, 3).map(t => (
                                  <Badge key={t} variant="secondary" className="text-xs">{t}</Badge>
                                ))}
                              </div>
                            </TableCell>
                          </TableRow>
                        ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </ScrollArea>
          </TabsContent>

          {/* TIME */}
          <TabsContent value="time" className="flex-1 overflow-hidden">
            <ScrollArea className="h-full">
              <div className="flex flex-col gap-4">
                <p className="text-muted-foreground text-sm">{i18n.library.time.description}</p>
                {/* Group events by month */}
                {(() => {
                  const byMonth = new Map<string, api.ApiEvent[]>()
                  filteredEvents.forEach(ev => {
                    const month = ev.start.slice(0, 7)
                    if (!byMonth.has(month)) byMonth.set(month, [])
                    byMonth.get(month)!.push(ev)
                  })
                  const months = Array.from(byMonth.entries()).sort(([a], [b]) => b.localeCompare(a))
                  return months.map(([month, evs]) => (
                    <div key={month}>
                      <div className="mb-2 flex items-center gap-2">
                        <span className="font-mono text-sm font-semibold">{month}</span>
                        <Badge variant="secondary" className="text-xs">{evs.length} 事件</Badge>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {evs.slice(0, 20).map(ev => (
                          <Badge key={ev.id} variant="outline" className="text-xs">
                            {ev.start.slice(5, 10)} {ev.content?.slice(0, 12) || ev.id.slice(0, 8)}
                          </Badge>
                        ))}
                        {evs.length > 20 && (
                          <Badge variant="outline" className="text-xs">+{evs.length - 20}</Badge>
                        )}
                      </div>
                    </div>
                  ))
                })()}
              </div>
            </ScrollArea>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}

export default function LibraryPage() {
  return (
    <Suspense fallback={<div className="text-muted-foreground flex h-screen items-center justify-center text-sm">加载中…</div>}>
      <LibraryContent />
    </Suspense>
  )
}
