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
  fontSize: number
  labelOpacity: number
  showLabel: boolean
  onClick?: (e: React.MouseEvent) => void
  onMouseEnter?: () => void
  onMouseLeave?: () => void
}

export function GraphNode({
  x, y, r, label, fill, strokeColor, isSelected, isHovered, isFocused, isDimmed, isBot,
  fontSize, labelOpacity, showLabel, onClick, onMouseEnter, onMouseLeave
}: GraphNodeProps) {
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
        stroke={isSelected ? strokeColor : (isBot ? strokeColor : 'var(--border)')}
        strokeWidth={isSelected ? 2.5 : (isBot ? 1.5 : 1)}
        className={cn(
          "transition-all duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)]",
          isHovered && "scale-110"
        )}
      />
      {showLabel && (
        <text
          y={r + 12}
          fontSize={fontSize}
          fill="var(--foreground)"
          textAnchor="middle"
          dominantBaseline="middle"
          className="select-none pointer-events-none transition-opacity duration-300"
          style={{ opacity: isFocused ? 1 : labelOpacity }}
        >
          {label}
        </text>
      )}
      {isBot && (
        <text
          y={r + 22}
          fontSize={8}
          fill={strokeColor}
          textAnchor="middle"
          dominantBaseline="middle"
          fontWeight="bold"
          className="select-none pointer-events-none transition-opacity duration-300"
          style={{ opacity: isFocused ? 1 : labelOpacity }}
        >
          BOT
        </text>
      )}
    </g>
  )
}
