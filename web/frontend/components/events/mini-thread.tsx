'use client'

import type { ApiEvent } from '@/lib/api'

interface MiniThreadProps {
  events: ApiEvent[]
  accent: string
  className?: string
}

function knotY(index: number, total: number) {
  if (total <= 1) return 24
  const t = index / (total - 1)
  return 24 + Math.sin(t * Math.PI * 2 - Math.PI / 8) * 9
}

export function MiniThread({ events, accent, className }: MiniThreadProps) {
  const knots = events.slice(-12)
  const width = 240
  const height = 48
  const path = `M 6 24 Q ${width * 0.25} 9 ${width * 0.5} 24 T ${width - 6} 24`

  return (
    <svg
      className={className}
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`${knots.length} event knots`}
    >
      <path d={path} fill="none" stroke={accent} strokeWidth="1.6" strokeLinecap="round" opacity="0.42" />
      <path
        d={path}
        fill="none"
        stroke={accent}
        strokeWidth="1"
        strokeLinecap="round"
        strokeDasharray="16 9"
        opacity="0.72"
        className="silk-flow"
      />
      {knots.map((ev, index) => {
        const x = knots.length <= 1 ? width / 2 : 14 + (index / (knots.length - 1)) * (width - 28)
        const y = knotY(index, knots.length)
        const r = Math.max(2.6, Math.min(6.2, 2.8 + (ev.salience ?? 0) * 3.4))
        const archived = ev.status === 'archived'
        const locked = ev.is_locked
        const high = (ev.salience ?? 0) > 0.8

        if (archived) {
          return (
            <path
              key={ev.id}
              d={`M ${x} ${y - r} L ${x + r} ${y} L ${x} ${y + r} L ${x - r} ${y} Z`}
              fill="var(--background)"
              stroke={accent}
              strokeWidth="1.2"
              strokeDasharray="3 2"
              opacity="0.72"
            />
          )
        }

        return (
          <g key={ev.id}>
            {high && <circle cx={x} cy={y} r={r + 3.5} fill="none" stroke={accent} strokeWidth="0.8" opacity="0.26" />}
            <circle
              cx={x}
              cy={y}
              r={r}
              fill={locked ? accent : 'var(--background)'}
              stroke={accent}
              strokeWidth={locked ? 1.8 : 1.3}
            />
            {locked && <circle cx={x} cy={y} r={Math.max(1.2, r * 0.35)} fill="var(--background)" opacity="0.9" />}
          </g>
        )
      })}
    </svg>
  )
}
