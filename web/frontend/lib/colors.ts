/**
 * Unified color utility for the Moirai frontend.
 *
 * All cyclic colors come from --color-palette-N CSS variables defined per theme,
 * so they automatically adapt to the active theme and light/dark mode.
 */

export const CHART_COLORS = [
  'var(--color-chart-1)',
  'var(--color-chart-2)',
  'var(--color-chart-3)',
  'var(--color-chart-4)',
  'var(--color-chart-5)',
  'var(--color-chart-6)',
  'var(--color-chart-7)',
  'var(--color-chart-8)',
  'var(--color-chart-9)',
  'var(--color-chart-10)',
  'var(--color-chart-11)',
  'var(--color-chart-12)',
  'var(--color-chart-13)',
  'var(--color-chart-14)',
  'var(--color-chart-15)',
  'var(--color-chart-16)',
  'var(--color-chart-17)',
  'var(--color-chart-18)',
  'var(--color-chart-19)',
  'var(--color-chart-20)',
]

/** Theme-aware 8-slot palette for tags, thread borders, and graph clusters. */
export const PALETTE_COLORS = [
  'var(--color-palette-1)',
  'var(--color-palette-2)',
  'var(--color-palette-3)',
  'var(--color-palette-4)',
  'var(--color-palette-5)',
  'var(--color-palette-6)',
  'var(--color-palette-7)',
  'var(--color-palette-8)',
]

/** Stable hash for a string. */
export function hashString(str: string): number {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash)
  }
  return Math.abs(hash)
}

/**
 * Returns a stable CSS variable color from the theme palette for a tag name.
 * Consistent across all views that use the same name.
 */
export function getTagColor(name: string): string {
  const hash = hashString(name)
  return PALETTE_COLORS[hash % PALETTE_COLORS.length]
}

/**
 * Returns a stable CSS variable color from the theme palette for an event/thread id.
 * Used for conversation card left-border accents.
 */
export function getThreadColor(id: string): string {
  const hash = hashString(id)
  return PALETTE_COLORS[hash % PALETTE_COLORS.length]
}

/**
 * Returns a CSS variable color from the theme palette by sequential index.
 * Used for graph clusters where numeric stability matters more than string hashing.
 */
export function getPaletteColor(index: number): string {
  return PALETTE_COLORS[Math.abs(index) % PALETTE_COLORS.length]
}

// Chroma floor for cluster colours: grayscale themes (nox) would otherwise
// rotate a zero-chroma colour and draw every community the same grey.
const MIN_CLUSTER_CHROMA = 0.08

function gcd(a: number, b: number): number {
  return b === 0 ? a : gcd(b, a % b)
}

/**
 * Step through the hue slots so size-ranked neighbours land far apart on the
 * wheel. Coprime with `count`, so every slot is still used exactly once.
 */
export function clusterHueStride(count: number): number {
  if (count <= 2) return 1
  let stride = Math.max(1, Math.round(count * 0.38))
  while (gcd(stride, count) !== 1) stride++
  return stride
}

/** Hue offset in degrees from the theme's first palette colour. */
export function clusterHueOffset(index: number, count: number): number {
  const n = Math.max(1, Math.floor(count))
  const i = ((Math.floor(index) % n) + n) % n
  const slot = (i * clusterHueStride(n)) % n
  return Math.round((slot * 360 / n) * 100) / 100
}

/**
 * Colour for graph community `index` out of `count`: the theme's first palette
 * colour rotated around the OKLCH hue wheel. The wheel is split evenly by the
 * community count, so more communities means a smaller hue step and colours
 * never repeat. Community 0 (the largest) keeps the theme colour itself.
 */
export function getClusterColor(index: number, count: number): string {
  const offset = clusterHueOffset(index, count)
  return `oklch(from var(--color-palette-1) l max(c, ${MIN_CLUSTER_CHROMA}) calc(h + ${offset}))`
}
