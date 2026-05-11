/**
 * Unified color utility for the Moirai frontend.
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

/**
 * Generates a stable hash for a string.
 */
export function hashString(str: string): number {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash)
  }
  return Math.abs(hash)
}

/**
 * Returns a stable color from the CHART_COLORS palette for a given string (e.g. a tag name).
 * This ensures consistency across different views.
 */
export function getTagColor(name: string): string {
  const hash = hashString(name)
  return CHART_COLORS[hash % CHART_COLORS.length]
}
