'use client'

import React from 'react'
import { TagFilter, TagItem } from './tag-filter'
import { DateRangePicker } from './date-range-picker'
import { DateRange } from 'react-day-picker'
import { Separator } from '@/components/ui/separator'

interface FilterBarProps {
  tags: TagItem[]
  activeTags: Set<string>
  onTagsChange: (tags: Set<string>) => void
  dateRange: DateRange | undefined
  onDateRangeChange: (range: DateRange | undefined) => void
  className?: string
  extraActions?: React.ReactNode
}

export function FilterBar({
  tags,
  activeTags,
  onTagsChange,
  dateRange,
  onDateRangeChange,
  className = "",
  extraActions,
}: FilterBarProps) {
  return (
    <div className={`flex items-start border-b ${className}`}>
      <div className="flex-1 min-w-0">
        <TagFilter tags={tags} value={activeTags} onChange={onTagsChange} />
      </div>
      <div className="flex shrink-0 self-stretch py-2">
        <Separator orientation="vertical" className="h-auto mx-2" />
      </div>
      <div className="flex flex-col p-3 gap-2 bg-muted/5 shrink-0">
        <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground px-1">
          时间范围
        </span>
        <div className="flex items-center gap-2">
          <DateRangePicker 
            value={dateRange} 
            onChange={onDateRangeChange} 
            className="w-full"
          />
          {extraActions}
        </div>
      </div>
    </div>
  )
}
