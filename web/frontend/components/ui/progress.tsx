"use client"

import * as React from "react"

import { cn } from "@/lib/utils"

type ProgressProps = React.HTMLAttributes<HTMLDivElement> & {
  value?: number | null
  max?: number
}

const Progress = React.forwardRef<
  HTMLDivElement,
  ProgressProps
>(({ className, value = 0, max = 100, ...props }, ref) => {
  const safeMax = max > 0 ? max : 100
  const boundedValue = Math.max(0, Math.min(Number(value ?? 0), safeMax))
  const percent = (boundedValue / safeMax) * 100

  return (
  <div
    ref={ref}
    role="progressbar"
    aria-valuemin={0}
    aria-valuemax={safeMax}
    aria-valuenow={boundedValue}
    className={cn(
      "relative h-4 w-full overflow-hidden rounded-full bg-secondary",
      className
    )}
    {...props}
  >
    <div
      className="h-full w-full flex-1 bg-primary transition-all"
      style={{ transform: `translateX(-${100 - percent}%)` }}
    />
  </div>
)})
Progress.displayName = "Progress"

export { Progress }
