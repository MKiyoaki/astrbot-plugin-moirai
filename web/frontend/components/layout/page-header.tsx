import { type ReactNode } from 'react'
import { Separator } from '@/components/ui/separator'
import { SidebarTrigger } from '@/components/ui/sidebar'
import { cn } from '@/lib/utils'

interface PageHeaderProps {
  title: string
  description?: string
  actions?: ReactNode
  className?: string
}

export function PageHeader({ title, description, actions, className }: PageHeaderProps) {
  return (
    <div className="flex flex-col">
      <header
        className={cn(
          // Adopted Shadcn standard header transition classes for smoother UI sync
          'flex h-16 shrink-0 items-center gap-2 px-6 bg-transparent transition-[width,height] ease-linear group-has-[[data-collapsible=icon]]/sidebar-wrapper:h-12',
          className
        )}
      >
        <div className="flex flex-1 items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <SidebarTrigger className="-ml-1" />
            <div className="flex flex-col gap-0.5 min-w-0">
              <h1 className="text-xl font-semibold tracking-tight leading-none truncate whitespace-nowrap">{title}</h1>
              {description && (
                <p className="text-muted-foreground text-xs truncate whitespace-nowrap">{description}</p>
              )}
            </div>
          </div>
          {actions && (
            <div className="flex shrink-0 items-center gap-2">
              {actions}
            </div>
          )}
        </div>
      </header>
      <Separator />
    </div>
  )
}