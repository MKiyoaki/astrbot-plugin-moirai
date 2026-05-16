import { type ReactNode } from 'react'
import { Separator } from '@/components/ui/separator'
import { SidebarTrigger } from '@/components/ui/sidebar'
import { cn } from '@/lib/utils'

interface PageHeaderProps {
  title: string
  description?: string
  actions?: ReactNode
  globalActions?: ReactNode
  className?: string
  /** 'default' = legacy single-row; 'loom' = editorial double-row (preferred for all pages) */
  variant?: 'default' | 'loom'
  /** loom: e.g. "7-DAY WINDOW · 5.06 → 5.12" shown centered in meta strip */
  loomWindow?: string
  /** loom: short section identity shown left in meta strip, e.g. "THE LOOM" */
  loomIssue?: string
  /** loom: legend nodes shown right in meta strip */
  loomLegend?: ReactNode
  /**
   * loom: when true, actions/globalActions are NOT rendered inside PageHeader.
   * Use this when the page renders its own full-width toolbar below.
   * When false/absent, a compact toolbar row is auto-rendered inside PageHeader.
   */
  externalToolbar?: boolean
  /**
   * loom: when true, the compact toolbar row (Row 3) will NOT have a bottom border.
   * Useful when another toolbar (like FilterBar) follows immediately.
   */
  noToolbarBorder?: boolean
}

export function PageHeader({
  title,
  description,
  actions,
  globalActions,
  className,
  variant = 'default',
  loomWindow,
  loomIssue,
  loomLegend,
  externalToolbar = false,
  noToolbarBorder = false,
}: PageHeaderProps) {
  if (variant === 'loom') {
    const hasToolbar = !externalToolbar && (actions || globalActions)

    return (
      <div className={cn('flex flex-col shrink-0', className)}>
        {/* Row 1: meta strip */}
        <div className="flex items-center px-4 pt-3 pb-0 gap-2">
          <div className="flex items-center gap-2 shrink-0 w-32">
            <SidebarTrigger className="-ml-1 shrink-0" />
            {loomIssue && (
              <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted-foreground/50 hidden sm:inline truncate">
                {loomIssue}
              </span>
            )}
          </div>
          <div className="flex-1 flex justify-center">
            {loomWindow && (
              <p className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted-foreground/40 hidden sm:block">
                {loomWindow}
              </p>
            )}
          </div>
          {loomLegend && (
            <div className="hidden md:flex items-center justify-end gap-3 w-32 font-mono text-[9px] uppercase tracking-[0.14em] text-muted-foreground/50">
              {loomLegend}
            </div>
          )}
          {/* When no legend, keep the right spacer so title stays centered */}
          {!loomLegend && <div className="w-32 hidden md:block" />}
        </div>

        {/* Row 2: main title */}
        <div className="flex items-center justify-center pb-3 pt-1">
          <h1 className="text-2xl font-bold tracking-tight leading-none">{title}</h1>
        </div>

        {/* Row 3 (optional): compact toolbar — only when page doesn't manage its own */}
        {hasToolbar && (
          <>
            <div className={cn(
              "flex items-center gap-2 px-4 py-2 bg-muted/5 shrink-0",
              !noToolbarBorder && "border-b"
            )}>
              {actions && <div className="flex items-center gap-2 flex-wrap">{actions}</div>}
              {globalActions && <div className="ml-auto flex items-center gap-2">{globalActions}</div>}
            </div>
          </>
        )}
      </div>
    )
  }

  // ── Legacy default variant ───────────────────────────────────────────────
  return (
    <div className="flex flex-col">
      <header
        className={cn(
          'flex h-16 shrink-0 items-center gap-2 px-6 bg-transparent transition-[width,height] ease-linear group-has-[[data-collapsible=icon]]/sidebar-wrapper:h-12',
          className
        )}
      >
        <div className="flex flex-1 items-center justify-between gap-4">
          <div className="flex min-w-0 flex-1 items-center gap-3">
            <SidebarTrigger className="-ml-1 shrink-0" />
            <div className="flex flex-col gap-0.5 min-w-0">
              <h1 className="text-xl font-bold tracking-tight leading-none truncate">{title}</h1>
              {description && (
                <p className="text-muted-foreground text-[10px] md:text-xs truncate hidden sm:block tracking-wide font-mono">{description}</p>
              )}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {actions && <div className="flex items-center gap-2">{actions}</div>}
            {actions && globalActions && <Separator orientation="vertical" className="mx-1 h-4" />}
            {globalActions && <div className="flex items-center gap-2">{globalActions}</div>}
          </div>
        </div>
      </header>
      <Separator />
    </div>
  )
}
