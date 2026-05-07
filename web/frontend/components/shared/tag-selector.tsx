'use client'

import { useState } from 'react'
import { Check, ChevronsUpDown, Plus, X, Tag } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
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

  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            className="border-input bg-transparent text-foreground flex min-h-9 w-full items-center justify-between rounded-lg border px-2.5 py-1.5 text-sm"
          >
            <div className="flex flex-wrap gap-1">
              {value.length === 0 && (
                <span className="text-muted-foreground">{placeholder}</span>
              )}
              {value.map(tag => (
                <Badge key={tag} variant="secondary" className="gap-1 pr-1 text-xs">
                  <Tag className="size-2.5" />
                  {tag}
                  <span
                    role="button"
                    tabIndex={0}
                    onClick={e => {
                      e.stopPropagation()
                      removeTag(tag)
                    }}
                    onKeyDown={e => {
                      if (e.key === 'Enter') {
                        e.stopPropagation()
                        removeTag(tag)
                      }
                    }}
                    className="hover:text-destructive ml-0.5 cursor-pointer outline-none"
                  >
                    <X className="size-2.5" />
                  </span>
                </Badge>
              ))}
            </div>
            <ChevronsUpDown className="text-muted-foreground ml-2 size-4 shrink-0" />
          </button>
        </PopoverTrigger>
        <PopoverContent className="w-72 p-0" align="start">
          <Command>
            <CommandInput
              placeholder="搜索或新建标签…"
              value={input}
              onValueChange={setInput}
            />
            <CommandList>
              <CommandEmpty>
                {input.trim() ? (
                  <button
                    type="button"
                    onClick={() => addTag(input)}
                    className="hover:bg-accent flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm"
                  >
                    <Plus className="size-3.5" />
                    <span>创建 &ldquo;{input}&rdquo;</span>
                  </button>
                ) : (
                  '暂无标签'
                )}
              </CommandEmpty>
              <CommandGroup heading="建议标签">
                {suggestions
                  .filter(s => !value.includes(s))
                  .map(s => (
                    <CommandItem
                      key={s}
                      value={s}
                      onSelect={() => {
                        addTag(s)
                      }}
                    >
                      <Check
                        className={cn(
                          'mr-2 size-3.5',
                          value.includes(s) ? 'opacity-100' : 'opacity-0'
                        )}
                      />
                      <Tag className="mr-2 size-3" />
                      {s}
                    </CommandItem>
                  ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  )
}

