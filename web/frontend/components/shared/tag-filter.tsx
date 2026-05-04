'use client'

import { useState, useRef, useEffect } from 'react'
import { X } from 'lucide-react'
import { i18n } from '@/lib/i18n'

const THREAD_COLORS = ['#7dd3fc', '#86efac', '#fca5a5', '#c4b5fd', '#fdba74', '#67e8f9', '#fde68a']
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
    <div className="border-b px-4 pb-2 pt-2">
      <div className="mb-1.5 flex items-center gap-2">
        <span className="text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">
          {i18n.events.tagFilter}
        </span>
        {value.size > 0 && (
          <button
            onClick={() => onChange(new Set())}
            className="flex items-center gap-0.5 rounded-full border px-2 py-0.5 text-[9.5px] text-muted-foreground transition-colors hover:text-foreground"
          >
            <X className="size-2.5" />
            {i18n.events.tagClear}
          </button>
        )}
      </div>
      <div
        ref={chipsRef}
        className="flex flex-wrap items-start gap-1.5 overflow-hidden"
        style={{ height: expanded ? undefined : `${COLLAPSED_H}px` }}
      >
        {tags.map((tag, i) => {
          const active = value.has(tag.name)
          const color = THREAD_COLORS[i % THREAD_COLORS.length]
          return (
            <button
              key={tag.name}
              onClick={() => toggle(tag.name)}
              className="inline-flex shrink-0 items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] transition-all"
              style={active ? { borderColor: `${color}55`, background: `${color}18`, color } : {}}
            >
              <span className="text-[10px] text-muted-foreground">#</span>
              {tag.name}
              <span className="rounded bg-muted px-1 text-[9px] text-muted-foreground">
                {tag.count}
              </span>
            </button>
          )
        })}
      </div>
      {overflows && (
        <button
          onClick={() => setExpanded(e => !e)}
          className="mt-1 rounded border px-2 py-0.5 text-[10px] text-muted-foreground hover:text-foreground"
        >
          {expanded ? i18n.events.tagCollapse : i18n.events.tagMore}
        </button>
      )}
    </div>
  )
}
