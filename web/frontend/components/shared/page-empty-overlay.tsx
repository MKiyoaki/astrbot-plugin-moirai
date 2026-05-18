import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

interface PageEmptyOverlayProps {
  icon: LucideIcon
  title: string
  description?: string
  action?: ReactNode
}

export function PageEmptyOverlay({
  icon: Icon,
  title,
  description,
  action,
}: PageEmptyOverlayProps) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center p-8 text-center bg-background/60 backdrop-blur-sm animate-in fade-in duration-500">
      <div className="mb-4 flex size-16 shrink-0 items-center justify-center rounded-full bg-muted">
        <Icon className="size-8 text-muted-foreground/60" />
      </div>
      <h3 className="mb-1.5 text-base font-medium">{title}</h3>
      {description && (
        <p className="max-w-xs text-sm leading-relaxed text-muted-foreground">
          {description}
        </p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}
