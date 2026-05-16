'use client'

import React, { useMemo, useState } from 'react'
import { Tag, X } from 'lucide-react'
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover'
import { DateRangePicker } from './date-range-picker'
import { DateRange } from 'react-day-picker'
import { getTagColor } from '@/lib/colors'

export interface TagItem {
  name: string
  count: number
}

interface FilterBarProps {
  tags: TagItem[]
  activeTags: Set<string>
  onTagsChange: (tags: Set<string>) => void
  dateRange: DateRange | undefined
  onDateRangeChange: (range: DateRange | undefined) => void
  className?: string
}

export function FilterBar({
  tags,
  activeTags,
  onTagsChange,
  dateRange,
  onDateRangeChange,
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
      {tags.length > 0 && <Tag className="size-3 text-muted-foreground/50 shrink-0" />}
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
