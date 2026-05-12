'use client'

import { cn } from '@/lib/utils'

interface Tab {
  value: string
  label: string
}

interface TabBarProps {
  tabs: Tab[]
  value: string
  onChange: (v: string) => void
  className?: string
}

export function TabBar({ tabs, value, onChange, className }: TabBarProps) {
  return (
    <div className={cn('flex border-b border-border/50 shrink-0', className)}>
      {tabs.map(tab => (
        <button
          key={tab.value}
          onClick={() => onChange(tab.value)}
          className={cn(
            'px-5 py-2.5 text-[10px] uppercase font-mono tracking-[0.18em] transition-colors relative',
            value === tab.value
              ? 'text-foreground after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-accent-foreground'
              : 'text-muted-foreground hover:text-foreground'
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}
