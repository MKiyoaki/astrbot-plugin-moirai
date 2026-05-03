'use client'

import { useState, useEffect, useRef } from 'react'
import { Check, ChevronsUpDown, Plus, X, Tag } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'

interface TagSelectorProps {
  value: string[]
  onChange: (tags: string[]) => void
  suggestions?: string[]
  placeholder?: string
  className?: string
}

export function TagSelector({
  value,
  onChange,
  suggestions = [],
  placeholder = '选择或输入标签…',
  className,
}: TagSelectorProps) {
  const [open, setOpen] = useState(false)
  const [input, setInput] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const filtered = suggestions.filter(
    s => s.toLowerCase().includes(input.toLowerCase()) && !value.includes(s),
  )

  const addTag = (tag: string) => {
    const trimmed = tag.trim()
    if (trimmed && !value.includes(trimmed)) {
      onChange([...value, trimmed])
    }
    setInput('')
  }

  const removeTag = (tag: string) => {
    onChange(value.filter(t => t !== tag))
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if ((e.key === 'Enter' || e.key === ',') && input.trim()) {
      e.preventDefault()
      addTag(input)
    } else if (e.key === 'Backspace' && !input && value.length) {
      removeTag(value[value.length - 1])
    }
  }

  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger
          className="border-input bg-transparent text-foreground flex min-h-9 w-full items-center justify-between rounded-lg border px-2.5 py-1.5 text-sm"
          onClick={() => { setOpen(true); setTimeout(() => inputRef.current?.focus(), 50) }}
        >
          <div className="flex flex-wrap gap-1">
            {value.length === 0 && (
              <span className="text-muted-foreground">{placeholder}</span>
            )}
            {value.map(tag => (
              <Badge key={tag} variant="secondary" className="gap-1 pr-1 text-xs">
                <Tag className="size-2.5" />
                {tag}
                <button
                  type="button"
                  onClick={e => { e.stopPropagation(); removeTag(tag) }}
                  className="hover:text-destructive ml-0.5"
                >
                  <X className="size-2.5" />
                </button>
              </Badge>
            ))}
          </div>
          <ChevronsUpDown className="text-muted-foreground ml-2 size-4 shrink-0" />
        </PopoverTrigger>
        <PopoverContent className="w-72 p-2" align="start">
          <Input
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入标签名，Enter 添加…"
            className="mb-2"
          />
          <div className="max-h-48 overflow-y-auto">
            {input.trim() && !suggestions.includes(input.trim()) && (
              <button
                type="button"
                onClick={() => addTag(input)}
                className="hover:bg-accent flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm"
              >
                <Plus className="size-3.5" />
                <span>创建 &ldquo;{input}&rdquo;</span>
              </button>
            )}
            {filtered.map(s => (
              <button
                key={s}
                type="button"
                onClick={() => { addTag(s); setInput('') }}
                className="hover:bg-accent flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm"
              >
                <Check className={cn('size-3.5', value.includes(s) ? 'opacity-100' : 'opacity-0')} />
                <Tag className="size-3" />
                {s}
              </button>
            ))}
            {filtered.length === 0 && !input.trim() && (
              <p className="text-muted-foreground px-2 py-1.5 text-sm">
                {suggestions.length ? '无更多标签' : '暂无已知标签，输入后按 Enter 创建'}
              </p>
            )}
          </div>
        </PopoverContent>
      </Popover>
    </div>
  )
}
