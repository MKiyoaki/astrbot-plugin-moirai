'use client'

/**
 * Shared ambient silk-thread SVG background used on the login page and landing hero card.
 * Thread-view animations (thread-draw, loom-axis-flow) are intentionally separate — they
 * belong to the timeline narrative, not the ambient brand decoration.
 */

interface SilkThreadBgProps {
  /** Speed up the flow animation (e.g. while password input is focused). */
  fast?: boolean
  /** Preset path/viewport layout for each surface. */
  variant: 'login' | 'hero'
}


export function SilkThreadBg({ fast = false, variant }: SilkThreadBgProps) {
  if (variant === 'login') {
    return (
      <svg
        className="absolute inset-0 w-full h-full pointer-events-none"
        aria-hidden
        preserveAspectRatio="none"
        viewBox="0 0 400 700"
      >

        {/* Background threads — muted, subtly curved */}
        <path d="M-10,148 Q80,142 180,155 Q280,168 410,151" fill="none" stroke="currentColor" strokeWidth="0.4" opacity="0.18" />
        <path d="M-10,220 Q60,228 160,215 Q260,202 410,224" fill="none" stroke="currentColor" strokeWidth="0.3" opacity="0.14" />
        <path d="M-10,310 Q100,298 200,318 Q300,328 410,308" fill="none" stroke="currentColor" strokeWidth="0.45" opacity="0.16" />
        <path d="M-10,420 Q90,432 190,418 Q290,405 410,428" fill="none" stroke="currentColor" strokeWidth="0.3" opacity="0.12" />
        <path d="M-10,510 Q120,502 210,516 Q310,525 410,506" fill="none" stroke="currentColor" strokeWidth="0.4" opacity="0.15" />
        <path d="M-10,580 Q70,575 170,588 Q270,598 410,574" fill="none" stroke="currentColor" strokeWidth="0.3" opacity="0.10" />

        {/* Accent silk thread — animated flow */}
        <path
          className={fast ? 'silk-accent silk-fast' : 'silk-accent'}
          d="M-10,265 Q60,252 140,270 Q220,288 310,260 Q360,247 410,268"
          fill="none"
          stroke="var(--color-primary, oklch(0.53 0.130 295))"
          strokeWidth="0.7"
          strokeLinecap="round"
        />

        {/* Knot-like nodes where threads cross */}
        <circle cx="112" cy="155" r="1.8" fill="currentColor" opacity="0.20" />
        <circle cx="248" cy="310" r="1.4" fill="currentColor" opacity="0.16" />
        <circle cx="310" cy="261" r="2" fill="var(--color-primary, oklch(0.53 0.130 295))" opacity="0.30" />
        <circle cx="168" cy="510" r="1.3" fill="currentColor" opacity="0.14" />
      </svg>
    )
  }

  // hero variant
  return (
    <svg
      className="absolute inset-0 w-full h-full pointer-events-none"
      aria-hidden
      preserveAspectRatio="none"
      viewBox="0 0 700 280"
    >

      {/* Background threads — lower half only */}
      <path d="M-10,180 Q120,172 260,185 Q400,198 560,178 Q640,172 710,184" fill="none" stroke="currentColor" strokeWidth="0.45" opacity="0.12" />
      <path d="M-10,230 Q100,240 240,228 Q380,216 520,236 Q630,244 710,228" fill="none" stroke="currentColor" strokeWidth="0.35" opacity="0.10" />
      <path d="M-10,258 Q130,250 280,263 Q420,276 570,253 Q650,246 710,260" fill="none" stroke="currentColor" strokeWidth="0.30" opacity="0.08" />

      {/* Accent silk threads — sit below text, in lower third */}
      <path
        className="silk-accent"
        d="M-10,210 Q80,198 200,214 Q330,228 460,202 Q560,188 640,216 Q680,228 710,218"
        fill="none"
        stroke="var(--color-primary, oklch(0.53 0.130 295))"
        strokeWidth="0.70"
        strokeLinecap="round"
        opacity="0.7"
      />
      <path
        className="silk-accent-2"
        d="M-10,248 Q90,258 210,244 Q350,228 480,256 Q580,270 710,248"
        fill="none"
        stroke="var(--color-primary, oklch(0.53 0.130 295))"
        strokeWidth="0.50"
        strokeLinecap="round"
        opacity="0.55"
      />

      {/* Knot nodes */}
      <circle cx="200" cy="214" r="1.6" fill="var(--color-primary, oklch(0.53 0.130 295))" opacity="0.22" />
      <circle cx="460" cy="202" r="1.3" fill="var(--color-primary, oklch(0.53 0.130 295))" opacity="0.18" />
      <circle cx="390" cy="263" r="1.2" fill="currentColor" opacity="0.12" />
      <circle cx="560" cy="236" r="1.4" fill="currentColor" opacity="0.10" />
    </svg>
  )
}
