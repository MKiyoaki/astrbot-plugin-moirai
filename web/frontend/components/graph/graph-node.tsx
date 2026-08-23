import { memo } from "react"
import { cn } from "@/lib/utils"

interface GraphNodeProps {
  x: number
  y: number
  r: number
  label: string
  fill: string
  strokeColor: string
  isSelected?: boolean
  isHovered?: boolean
  isFocused?: boolean
  isDimmed?: boolean
  isBot?: boolean
  botLabel?: string
  fontSize: number
  showLabel: boolean
  onClick?: (e: React.MouseEvent) => void
  onMouseEnter?: () => void
  onMouseLeave?: () => void
}

function GraphNodeImpl({
  x, y, r, label, fill, strokeColor, isSelected, isHovered, isFocused, isDimmed, isBot, botLabel,
  fontSize, showLabel, onClick, onMouseEnter, onMouseLeave
}: GraphNodeProps) {
  void isFocused
  return (
    <g
      transform={`translate(${x},${y})`}
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      className={cn(
        "cursor-pointer transition-opacity duration-400",
        isDimmed && "opacity-15"
      )}
    >
      {/* Pulse Ring */}
      {(isHovered || isSelected) && (
        <circle
          r={r}
          fill="none"
          stroke={strokeColor}
          strokeWidth={2}
          className="animate-graph-pulse"
        />
      )}

      <circle
        r={r}
        fill={fill}
        fillOpacity={isBot ? 0.15 : 1}
        stroke={isSelected ? strokeColor : (isBot ? strokeColor : 'var(--border)')}
        strokeWidth={isSelected ? 2.5 : (isBot ? 1.5 : 1)}
        className={cn(
          "transition-all duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)]",
          isHovered && "scale-110"
        )}
      />
      {showLabel && (
        <text
          y={r + fontSize + 2}
          fontSize={fontSize}
          fill="var(--foreground)"
          stroke="var(--background)"
          strokeWidth={fontSize * 0.4}
          paintOrder="stroke"
          textAnchor="middle"
          dominantBaseline="middle"
          className="select-none pointer-events-none animate-in fade-in duration-200"
        >
          {label}
        </text>
      )}
      {isBot && showLabel && (
        <text
          y={r + fontSize * 2 + 4}
          fontSize={fontSize * 0.8}
          fill={strokeColor}
          textAnchor="middle"
          dominantBaseline="middle"
          fontWeight="bold"
          className="select-none pointer-events-none animate-in fade-in duration-200"
        >
          {botLabel ?? 'BOT'}
        </text>
      )}
    </g>
  )
}

export const GraphNode = memo(GraphNodeImpl)
