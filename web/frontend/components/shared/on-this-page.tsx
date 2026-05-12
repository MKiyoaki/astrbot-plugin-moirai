import { cn } from "@/lib/utils"

interface OnThisPageProps {
  items: { id: string; label: string }[]
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
            <button
              key={item.id}
              onClick={() => onItemClick(item.id)}
              className={cn(
                "text-left text-sm py-1 transition-colors duration-200",
                isActive
                  ? "font-medium text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {item.label}
            </button>
          )
        })}
      </nav>
    </div>
  )
}
