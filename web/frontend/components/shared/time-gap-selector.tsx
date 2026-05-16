'use client'

import React from 'react'
import { SlidersHorizontal } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'
import {
  Popover, PopoverTrigger, PopoverContent,
} from '@/components/ui/popover'
import { useApp } from '@/lib/store'

export const GAP_OPTIONS = [
  { label: '30m', value: 1800000 },
  { label: '1h',  value: 3600000 },
  { label: '2h',  value: 7200000 },
  { label: '4h',  value: 14400000 },
  { label: '8h',  value: 28800000 },
  { label: '24h', value: 86400000 },
  { label: '7d',  value: 604800000 },
]

interface TimeGapSelectorProps {
  value: number
  onChange: (value: number) => void
  className?: string
}

export function TimeGapSelector({ value, onChange, className }: TimeGapSelectorProps) {
  const { i18n } = useApp()
  const currentOption = GAP_OPTIONS.find(o => o.value === value) || GAP_OPTIONS[2]

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className={`h-7 gap-1.5 px-2 ${className}`}>
          <SlidersHorizontal className="size-3.5" />
          <span className="text-xs">{currentOption.label}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-52 p-4" align="start">
        <div className="space-y-3">
          <div className="flex items-center justify-between text-[10px] text-muted-foreground uppercase font-bold tracking-tight">
            <span>{i18n.events.threadScale}</span>
            <span className="text-primary">{currentOption.label}</span>
          </div>
          <Slider
            value={[GAP_OPTIONS.findIndex(o => o.value === value)]}
            min={0}
            max={GAP_OPTIONS.length - 1}
            step={1}
            onValueChange={([val]) => onChange(GAP_OPTIONS[val].value)}
          />
        </div>
      </PopoverContent>
    </Popover>
  )
}
