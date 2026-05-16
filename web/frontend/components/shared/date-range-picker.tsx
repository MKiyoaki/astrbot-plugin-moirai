'use client'

import * as React from 'react'
import { format, isSameYear } from 'date-fns'
import { Calendar as CalendarIcon, X } from 'lucide-react'
import { DateRange } from 'react-day-picker'

import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Calendar } from '@/components/ui/calendar'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { useApp } from '@/lib/store'

interface DateRangePickerProps {
  value: DateRange | undefined
  onChange: (range: DateRange | undefined) => void
  className?: string
  buttonClassName?: string
}

export function DateRangePicker({
  value,
  onChange,
  className,
  buttonClassName,
}: DateRangePickerProps) {
  const { rawEvents, i18n } = useApp()
  const t = i18n.common.datePicker || { selectDate: 'Select Date', selectRange: 'Select Range' }

  const eventDates = React.useMemo(() => {
    const dates = new Set<string>()
    rawEvents.forEach(ev => {
      try {
        const d = new Date(ev.start)
        dates.add(format(d, 'yyyy-MM-dd'))
      } catch {}
    })
    return Array.from(dates).map(d => new Date(d))
  }, [rawEvents])

  const formatDateRange = (range: DateRange) => {
    const from = range.from
    const to = range.to
    if (!from) return t.selectRange
    
    const yearFormat = 'yy/MM/dd'
    const shortFormat = 'MM/dd'
    
    if (!to) return format(from, yearFormat)
    
    if (isSameYear(from, to)) {
      return `${format(from, yearFormat)} - ${format(to, shortFormat)}`
    }
    return `${format(from, yearFormat)} - ${format(to, yearFormat)}`
  }

  return (
    <div className={cn('grid gap-2', className)}>
      <Popover>
        <PopoverTrigger asChild>
          <Button
            id="date"
            variant={'outline'}
            className={cn(
              'h-9 justify-start text-left font-normal text-xs px-2.5 min-w-[200px] w-auto transition-all',
              !value && 'text-muted-foreground',
              buttonClassName
            )}
          >
            <CalendarIcon className="mr-2 h-3.5 w-3.5 opacity-60" />
            <span className="truncate mr-1">
              {value ? formatDateRange(value) : t.selectDate}
            </span>
            {value && (
              <div 
                className="ml-auto rounded-full p-0.5 hover:bg-muted transition-colors cursor-pointer"
                onClick={(e) => {
                  e.stopPropagation()
                  onChange(undefined)
                }}
              >
                <X className="h-3 w-3 opacity-60 hover:opacity-100" />
              </div>
            )}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0 shadow-2xl" align="end">
          <Calendar
            initialFocus
            mode="range"
            defaultMonth={value?.from}
            selected={value}
            onSelect={onChange}
            numberOfMonths={2}
            modifiers={{
              hasEvent: eventDates
            }}
            modifiersClassNames={{
              hasEvent: "bg-muted/40 font-bold text-foreground relative after:absolute after:bottom-1 after:left-1/2 after:-translate-x-1/2 after:size-0.5 after:rounded-full after:bg-primary/50"
            }}
          />
        </PopoverContent>
      </Popover>
    </div>
  )
}
