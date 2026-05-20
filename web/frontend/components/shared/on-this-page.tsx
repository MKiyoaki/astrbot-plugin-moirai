import { cn } from "@/lib/utils"

interface TocItem {
  id: string
  label: string
  children?: { id: string; label: string }[]
}

interface OnThisPageProps {
  items: TocItem[]
  activeId: string
  onItemClick: (id: string) => void
  title: string
}

export function OnThisPage({ items, activeId, onItemClick, title }: OnThisPageProps) {
  if (items.length === 0) return null

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs font-semibold text-foreground">{title}</p>
      <nav className="flex flex-col space-y-1">
        {items.map(item => {
          const isActive = activeId === item.id
          return (
            <div key={item.id} className="flex flex-col">
              <button
                onClick={() => onItemClick(item.id)}
                className={cn(
                  "text-left text-sm py-1 transition-colors duration-200",
                  isActive
                    ? "font-semibold text-foreground"
                    : "font-medium text-muted-foreground hover:text-foreground"
                )}
              >
                {item.label}
              </button>
              {item.children && item.children.length > 0 && (
                <div className="flex flex-col border-l border-border/60 ml-1 pl-3">
                  {item.children.map(child => {
                    const childActive = activeId === child.id
                    return (
                      <button
                        key={child.id}
                        onClick={() => onItemClick(child.id)}
                        className={cn(
                          "text-left text-xs py-0.5 transition-colors duration-200",
                          childActive
                            ? "font-medium text-foreground"
                            : "text-muted-foreground/80 hover:text-foreground"
                        )}
                      >
                        {child.label}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </nav>
    </div>
  )
}
