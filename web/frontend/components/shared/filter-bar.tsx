'use client'

import React, { useEffect, useMemo, useState } from 'react'
import { LoaderCircle, Sparkles, Tag, X } from 'lucide-react'
import {
  Dialog, DialogContent, DialogDescription, DialogHeader,
  DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { DateRangePicker } from './date-range-picker'
import { DateRange } from 'react-day-picker'
import { getTagColor } from '@/lib/colors'
import { useI18n } from '@/lib/store'
import * as api from '@/lib/api'
import { cn } from '@/lib/utils'

export interface TagItem {
  name: string
  count: number
}

const treeCopy = {
  zh: {
    button: '查看 Tag Tree',
    title: '交互行为 Tag Tree',
    description: '9 个静态类别与当前人格已审核的自定义标签。仅供查看。',
    staticCount: '静态标签',
    customCount: '自定义标签',
    dynamic: '动态',
    empty: '当前范围尚无已审核的自定义标签',
    loadError: 'Tag Tree 加载失败，请稍后重试。',
  },
  ja: {
    button: 'Tag Tree を表示',
    title: 'インタラクション Tag Tree',
    description: '9つの静的カテゴリと、現在のペルソナで承認済みのカスタムタグ。閲覧専用です。',
    staticCount: '静的タグ',
    customCount: 'カスタムタグ',
    dynamic: '動的',
    empty: '現在の範囲には承認済みカスタムタグがありません',
    loadError: 'Tag Tree を読み込めませんでした。後でもう一度お試しください。',
  },
  en: {
    button: 'View Tag Tree',
    title: 'Interaction Tag Tree',
    description: 'Nine static groups and the approved custom tags in the current persona scope. Read only.',
    staticCount: 'Static tags',
    customCount: 'Custom tags',
    dynamic: 'Dynamic',
    empty: 'No approved custom tags exist in the current scope',
    loadError: 'Could not load the Tag Tree. Please try again.',
  },
} as const

function TagTreeDialog({ persona }: { persona?: string | null }) {
  const { lang } = useI18n()
  const text = treeCopy[lang]
  const [open, setOpen] = useState(false)
  const [tree, setTree] = useState<api.InteractionTagTree | null>(null)
  const [loading, setLoading] = useState(false)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!open) return
    let active = true
    setLoading(true)
    setFailed(false)
    api.tags.tree(persona)
      .then(data => {
        if (active) setTree(data)
      })
      .catch(() => {
        if (active) setFailed(true)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [open, persona])

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button
          type="button"
          aria-label={text.button}
          title={text.button}
          className="group grid size-6 shrink-0 place-items-center rounded-md border border-primary/25 bg-primary/15 text-primary shadow-[inset_0_1px_0_color-mix(in_srgb,var(--primary)_18%,transparent)] transition-all hover:border-primary/40 hover:bg-primary/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        >
          <Tag className="size-3 transition-transform group-hover:-rotate-6 group-hover:scale-110" />
        </button>
      </DialogTrigger>
      <DialogContent className="max-h-[82vh] max-w-4xl gap-0 overflow-hidden border-border/70 bg-background p-0 shadow-2xl">
        <DialogHeader className="border-b border-border/60 bg-gradient-to-br from-primary/12 via-primary/5 to-transparent px-6 py-5 pr-12">
          <div className="flex items-start gap-3">
            <div className="grid size-9 shrink-0 place-items-center rounded-lg border border-primary/25 bg-primary/15 text-primary">
              <Tag className="size-4" />
            </div>
            <div className="space-y-1.5">
              <DialogTitle className="font-heading text-xl tracking-tight">{text.title}</DialogTitle>
              <DialogDescription className="max-w-2xl text-xs leading-relaxed">
                {text.description}
              </DialogDescription>
            </div>
          </div>
          {tree && !loading && (
            <div className="flex gap-2 pt-2 text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
              <span className="rounded-full border border-border/60 bg-background/60 px-2 py-1">
                {tree.static_leaf_count} {text.staticCount}
              </span>
              <span className="rounded-full border border-primary/20 bg-primary/10 px-2 py-1 text-primary">
                {tree.custom_leaf_count} {text.customCount}
              </span>
            </div>
          )}
        </DialogHeader>

        <ScrollArea className="h-[min(62vh,650px)]">
          <div className="p-5">
            {loading && (
              <div className="grid min-h-56 place-items-center text-muted-foreground">
                <LoaderCircle className="size-5 animate-spin" />
              </div>
            )}
            {!loading && failed && (
              <div className="grid min-h-56 place-items-center text-sm text-muted-foreground">
                {text.loadError}
              </div>
            )}
            {!loading && !failed && tree && (
              <div className="grid gap-3 md:grid-cols-2">
                {tree.groups.map((group, index) => (
                  <section
                    key={group.id}
                    className={cn(
                      'rounded-xl border border-border/55 bg-card/35 p-4 shadow-sm',
                      group.dynamic && 'border-primary/30 bg-primary/[0.045] md:col-span-2',
                    )}
                  >
                    <div className="mb-3 flex items-start gap-3">
                      <span className={cn(
                        'grid size-6 shrink-0 place-items-center rounded-md bg-muted font-mono text-[10px] text-muted-foreground',
                        group.dynamic && 'bg-primary/15 text-primary',
                      )}>
                        {group.dynamic ? <Sparkles className="size-3" /> : String(index + 1).padStart(2, '0')}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <h3 className="text-sm font-semibold text-foreground">{group.label}</h3>
                          {group.dynamic && (
                            <span className="rounded-full bg-primary/12 px-1.5 py-0.5 text-[9px] font-mono uppercase tracking-wider text-primary">
                              {text.dynamic}
                            </span>
                          )}
                        </div>
                        <p className="mt-0.5 truncate font-mono text-[9px] uppercase tracking-wider text-muted-foreground/65">
                          {group.id} · {group.label_en}
                        </p>
                      </div>
                      <span className="font-mono text-[10px] text-muted-foreground/60">{group.leaves.length}</span>
                    </div>

                    {group.leaves.length > 0 ? (
                      <div className="flex flex-wrap gap-1.5">
                        {group.leaves.map(leaf => {
                          const color = getTagColor(leaf.tag)
                          return (
                            <div
                              key={leaf.id}
                              title={leaf.id}
                              className="rounded-md border px-2 py-1 text-[10px] font-medium"
                              style={{
                                color,
                                background: `color-mix(in srgb, ${color} 9%, transparent)`,
                                borderColor: `color-mix(in srgb, ${color} 24%, transparent)`,
                              }}
                            >
                              #{leaf.tag}
                            </div>
                          )
                        })}
                      </div>
                    ) : (
                      <div className="rounded-lg border border-dashed border-primary/20 bg-background/30 px-3 py-4 text-center text-[10px] text-muted-foreground">
                        {text.empty}
                      </div>
                    )}
                  </section>
                ))}
              </div>
            )}
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  )
}

interface FilterBarProps {
  tags: TagItem[]
  activeTags: Set<string>
  onTagsChange: (tags: Set<string>) => void
  dateRange: DateRange | undefined
  onDateRangeChange: (range: DateRange | undefined) => void
  persona?: string | null
  className?: string
}

export function FilterBar({
  tags,
  activeTags,
  onTagsChange,
  dateRange,
  onDateRangeChange,
  persona,
  className = "",
}: FilterBarProps) {
  const [tagPopoverOpen, setTagPopoverOpen] = useState(false)

  // Top 8 tags inline; rest in popover
  const topTags = useMemo(() => tags.slice(0, 8), [tags])
  const moreTags = useMemo(() => tags.slice(8), [tags])

  const toggleTag = (tag: string) => {
    const next = new Set(activeTags)
    if (next.has(tag)) next.delete(tag); else next.add(tag)
    onTagsChange(next)
  }

  return (
    <div className={`flex items-center gap-1.5 px-4 py-1.5 flex-wrap border-b bg-muted/5 shrink-0 ${className}`}>
      <TagTreeDialog persona={persona} />
      {tags.length > 0 && topTags.map(({ name }) => {
        const active = activeTags.has(name)
        const color = getTagColor(name)
        return (
          <button key={name} onClick={() => toggleTag(name)}
            className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-mono font-medium transition-all"
            style={{
              background: active ? `color-mix(in srgb, ${color} 20%, transparent)` : 'transparent',
              color: active ? color : 'var(--muted-foreground)',
              border: `1px solid ${active ? `color-mix(in srgb, ${color} 40%, transparent)` : 'transparent'}`,
            }}>
            #{name}{active && <X className="size-2.5 ml-0.5" />}
          </button>
        )
      })}
      {tags.length > 0 && moreTags.length > 0 && (
        <Popover open={tagPopoverOpen} onOpenChange={setTagPopoverOpen}>
          <PopoverTrigger asChild>
            <button className="inline-flex items-center rounded px-2 py-0.5 text-[10px] font-mono text-muted-foreground/60 hover:text-muted-foreground border border-transparent hover:border-border transition-all">
              +{moreTags.length}
            </button>
          </PopoverTrigger>
          <PopoverContent className="w-64 p-3" align="start">
            <div className="flex flex-wrap gap-1.5">
              {moreTags.map(({ name }) => {
                const active = activeTags.has(name); const color = getTagColor(name)
                return (
                  <button key={name} onClick={() => toggleTag(name)}
                    className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-mono font-medium transition-all"
                    style={{
                      background: active ? `color-mix(in srgb, ${color} 20%, transparent)` : `color-mix(in srgb, ${color} 8%, transparent)`,
                      color: active ? color : 'var(--muted-foreground)',
                      border: `1px solid ${active ? `color-mix(in srgb, ${color} 40%, transparent)` : 'transparent'}`,
                    }}>
                    #{name}{active && <X className="size-2.5 ml-0.5" />}
                  </button>
                )
              })}
            </div>
          </PopoverContent>
        </Popover>
      )}
      {/* Date range picker — right-aligned, compact height matching row */}
      <DateRangePicker
        value={dateRange}
        onChange={onDateRangeChange}
        className="ml-auto shrink-0"
        buttonClassName="h-6 text-[10px] min-w-[160px] px-2"
      />
    </div>
  )
}
