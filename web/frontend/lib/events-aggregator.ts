import type { ApiEvent } from '@/lib/api'

export const EVENT_GROUP_PRIVATE = '__pvt__'

export interface SpindleCard {
  groupId: string
  name: string
  glyph: string
  issue: string
  events: ApiEvent[]
  total: number
  locked: number
  archived: number
  highSalience: number
  lastActiveAt: string | null
  topTags: string[]
  accent: string
}

export const GROUP_GLYPHS = ['Α', 'Β', 'Γ', 'Δ', 'Ε', 'Ζ', 'Η', 'Θ', 'Ι', 'Κ', 'Λ', 'Μ']
export const GROUP_ISSUES = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII']
export const GROUP_PALETTE = [
  'oklch(0.58 0.14 295)',
  'oklch(0.58 0.13 200)',
  'oklch(0.62 0.14 30)',
  'oklch(0.56 0.13 145)',
  'oklch(0.60 0.13 250)',
  'oklch(0.60 0.13 340)',
]

export function eventGroupId(ev: Pick<ApiEvent, 'group'>): string {
  return ev.group || EVENT_GROUP_PRIVATE
}

export function eventGroupLabel(groupId: string, privateLabel = 'Private / DM'): string {
  return groupId === EVENT_GROUP_PRIVATE ? privateLabel : groupId
}

export function stringHash(input: string): number {
  let hash = 2166136261
  for (let i = 0; i < input.length; i++) {
    hash ^= input.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

export function groupAccent(groupId: string): string {
  return GROUP_PALETTE[stringHash(groupId) % GROUP_PALETTE.length]
}

export function groupDecor(groupId: string, fallbackIndex: number) {
  const index = groupId === EVENT_GROUP_PRIVATE ? 3 : fallbackIndex
  return {
    glyph: GROUP_GLYPHS[index % GROUP_GLYPHS.length],
    issue: GROUP_ISSUES[index % GROUP_ISSUES.length],
  }
}

export function buildSpindleCards(events: ApiEvent[], privateLabel = 'Private / DM'): SpindleCard[] {
  const grouped = new Map<string, ApiEvent[]>()
  for (const ev of events) {
    const key = eventGroupId(ev)
    const list = grouped.get(key) ?? []
    list.push(ev)
    grouped.set(key, list)
  }

  return Array.from(grouped.entries())
    .map(([groupId, groupEvents]) => {
      const sorted = [...groupEvents].sort((a, b) => {
        return new Date(a.start).getTime() - new Date(b.start).getTime()
      })
      const activeEvents = sorted.filter(ev => ev.status !== 'archived')
      const last = sorted.reduce<ApiEvent | null>((acc, ev) => {
        if (!ev.start) return acc
        if (!acc) return ev
        return new Date(ev.start).getTime() > new Date(acc.start).getTime() ? ev : acc
      }, null)

      const tagCounts = new Map<string, number>()
      for (const ev of activeEvents) {
        for (const tag of ev.tags ?? []) {
          tagCounts.set(tag, (tagCounts.get(tag) ?? 0) + 1)
        }
      }

      return {
        groupId,
        name: eventGroupLabel(groupId, privateLabel),
        glyph: '',
        issue: '',
        events: sorted,
        total: sorted.length,
        locked: sorted.filter(ev => ev.is_locked).length,
        archived: sorted.filter(ev => ev.status === 'archived').length,
        highSalience: activeEvents.filter(ev => (ev.salience ?? 0) > 0.8).length,
        lastActiveAt: last?.start ?? null,
        topTags: Array.from(tagCounts.entries())
          .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
          .slice(0, 5)
          .map(([tag]) => tag),
        accent: groupAccent(groupId),
      }
    })
    .sort((a, b) => {
      const at = a.lastActiveAt ? new Date(a.lastActiveAt).getTime() : 0
      const bt = b.lastActiveAt ? new Date(b.lastActiveAt).getTime() : 0
      return bt - at || a.name.localeCompare(b.name)
    })
    .map((card, index) => ({
      ...card,
      ...groupDecor(card.groupId, index),
    }))
}
