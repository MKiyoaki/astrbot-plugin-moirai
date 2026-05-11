'use client'

import { useState, useRef, useEffect } from 'react'
import { X, ChevronDown, ChevronUp } from 'lucide-react'
import { useApp } from '@/lib/store'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { getTagColor } from '@/lib/colors'

const COLLAPSED_H = 36

export interface TagItem {
  name: string
  count: number
}

interface TagFilterProps {
  tags: TagItem[]
  value: Set<string>
  onChange: (next: Set<string>) => void
}

export function TagFilter({ tags, value, onChange }: TagFilterProps) {
  const { i18n } = useApp()
  const [expanded, setExpanded] = useState(false)
  const chipsRef = useRef<HTMLDivElement>(null)
  const [overflows, setOverflows] = useState(false)

  useEffect(() => {
    const el = chipsRef.current
    if (!el) return
    const measure = () => setOverflows(el.scrollHeight > COLLAPSED_H + 6)
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    measure()
    return () => ro.disconnect()
  }, [tags])

  if (!tags.length) return null

  const toggle = (name: string) => {
    const next = new Set(value)
    if (next.has(name)) next.delete(name); else next.add(name)
    onChange(next)
  }

  return (
    <div className="px-4 pb-2 pt-2">
      <div className="mb-1.5 flex items-center gap-2">
        <span className="text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">
          {i18n.events.tagFilter}
        </span>
        {value.size > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => onChange(new Set())}
            className="h-5 rounded-full px-2 text-[9.5px] text-muted-foreground gap-1"
          >
            <X className="size-2.5" />
            {i18n.events.tagClear}
          </Button>
        )}
      </div>
      <div
        ref={chipsRef}
        className="flex flex-wrap items-start gap-1.5 overflow-hidden"
        style={{ height: expanded ? undefined : `${COLLAPSED_H}px` }}
      >
        {tags.map((tag) => {
          const active = value.has(tag.name)
          const color = getTagColor(tag.name)
          return (
            <button
              key={tag.name}
              onClick={() => toggle(tag.name)}
              className={cn(
                "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] transition-all",
                active 
                  ? "bg-secondary border-muted-foreground/20 shadow-sm" 
                  : "bg-transparent border-transparent hover:bg-muted/50"
              )}
            >
              <span className="size-1.5 shrink-0 rounded-full" style={{ background: color }} />
              {tag.name}
              <span className="ml-0.5 text-[9px] text-muted-foreground opacity-70">
                {tag.count}
              </span>
              {active && <X className="ml-0.5 size-2.5 text-muted-foreground" />}
            </button>
          )
        })}
      </div>
      {overflows && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setExpanded(e => !e)}
          className="mt-1 h-6 rounded border px-2 py-0.5 text-[10px] text-muted-foreground hover:text-foreground"
        >
          {expanded ? (
            <>
              <ChevronUp className="mr-1 size-3" />
              {i18n.events.tagCollapse}
            </>
          ) : (
            <>
              <ChevronDown className="mr-1 size-3" />
              {i18n.events.tagMore}
            </>
          )}
        </Button>
      )}
    </div>
  )
}
