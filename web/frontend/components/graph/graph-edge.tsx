import { cn } from "@/lib/utils"

interface GraphEdgeProps {
  x1: number
  y1: number
  x2: number
  y2: number
  color: string
  width: number
  isBidirectional?: boolean
  isHovered?: boolean
  isSelected?: boolean
  isFocused?: boolean
  isDimmed?: boolean
  arrowId?: string
  perpX?: number
  perpY?: number
  offset?: number
  onClick?: (e: React.MouseEvent) => void
  onMouseEnter?: () => void
  onMouseLeave?: () => void
}

export function GraphEdge({
  x1, y1, x2, y2, color, width, isBidirectional, isHovered, isSelected, isFocused, isDimmed,
  arrowId, perpX, perpY, offset, onClick, onMouseEnter, onMouseLeave
}: GraphEdgeProps) {
  const strokeW = (isHovered || isSelected) ? width + 2.5 : (isFocused ? width + 1.2 : width)
  const edgeColor = (isHovered || isSelected) ? 'var(--accent-foreground)' : color

  return (
    <g
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      className={cn(
        "cursor-pointer transition-opacity duration-400",
        isDimmed && "opacity-10"
      )}
    >
      {/* Glow effect for selection or hover */}
      {(isHovered || isSelected) && (
        <line
          x1={x1} y1={y1} x2={x2} y2={y2}
          className="stroke-accent opacity-30"
          strokeWidth={strokeW + 6}
          strokeLinecap="round"
        />
      )}

      {isBidirectional && perpX !== undefined && perpY !== undefined && offset !== undefined ? (
        <>
          <line
            x1={x1 + perpX * offset} y1={y1 + perpY * offset}
            x2={x2 + perpX * offset} y2={y2 + perpY * offset}
            stroke={edgeColor} strokeWidth={strokeW}
            className={isFocused ? "animate-graph-flow" : ""}
            strokeDasharray={isFocused ? "5,5" : "none"}
          />
          <line
            x1={x2 - perpX * offset} y1={y2 - perpY * offset}
            x2={x1 - perpX * offset} y2={y1 - perpY * offset}
            stroke={edgeColor} strokeWidth={strokeW}
            className={isFocused ? "animate-graph-flow" : ""}
            strokeDasharray={isFocused ? "5,5" : "none"}
          />
        </>
      ) : (
        <line
          x1={x1} y1={y1} x2={x2} y2={y2}
          stroke={edgeColor} strokeWidth={strokeW}
          className={isFocused ? "animate-graph-flow" : ""}
          strokeDasharray={isFocused ? "5,5" : "none"}
          markerEnd={arrowId ? `url(#${arrowId})` : undefined}
        />
      )}
      {/* Transparent wide hit area */}
      <line
        x1={x1} y1={y1} x2={x2} y2={y2}
        stroke="transparent" strokeWidth={16}
      />
    </g>
  )
}
