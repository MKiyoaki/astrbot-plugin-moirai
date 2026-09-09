import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function cleanSummaryText(summary: string): string {
  const entities: Record<string, string> = {
    amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ',
  }
  let value = summary.replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos|nbsp);/gi, (raw, entity: string) => {
    if (!entity.startsWith('#')) return entities[entity.toLowerCase()] ?? raw
    const hex = entity[1].toLowerCase() === 'x'
    const code = parseInt(entity.slice(hex ? 2 : 1), hex ? 16 : 10)
    return code > 0 && code <= 0x10ffff ? String.fromCodePoint(code) : raw
  }).replace(/\\([_*\[\]])/g, '$1').trim()
  for (const marker of ['**', '__', '`']) {
    if (value.startsWith(marker) && value.endsWith(marker)) {
      value = value.slice(marker.length, -marker.length).trim()
    }
  }
  return value
}

export function parseSummaryTopics(summary: string): { what: string; who: string; how: string; eval?: string }[] | null {
  const topics = cleanSummaryText(summary).split(/\s*\|\s*(?=\[What\])|(?=\[What\])/i).map(s => s.trim()).filter(Boolean)
  const result: { what: string; who: string; how: string; eval?: string }[] = []
  for (const topic of topics) {
    const matches = [...topic.matchAll(/\[(What|Who|How|Eval)\]\s*/gi)]
    if (!matches.length || matches[0].index !== 0) return null
    const fields: Record<string, string> = {}
    matches.forEach((match, i) => {
      const end = matches[i + 1]?.index ?? topic.length
      fields[match[1].toLowerCase()] = topic.slice(match.index! + match[0].length, end).trim()
    })
    if (!fields.what) return null
    result.push({ what: fields.what, who: fields.who ?? '', how: fields.how ?? '', ...(fields.eval ? { eval: fields.eval } : {}) })
  }
  return result.length > 0 ? result : null
}
