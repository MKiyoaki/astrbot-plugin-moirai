import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function parseSummaryTopics(summary: string): { what: string; who: string; how: string; eval?: string }[] | null {
  const topics = summary.split('|').map(s => s.trim()).filter(Boolean)
  const result: { what: string; who: string; how: string; eval?: string }[] = []
  for (const t of topics) {
    const what = t.match(/\[What\]\s*([^\[]+)/)?.[1]?.trim()
    const who  = t.match(/\[Who\]\s*([^\[]+)/)?.[1]?.trim()
    const how  = t.match(/\[How\]\s*([^\[]+)/)?.[1]?.trim()
    const eval_ = t.match(/\[Eval\]\s*([^\[]+)/)?.[1]?.trim()
    if (what && who && how) result.push({ what, who, how, ...(eval_ ? { eval: eval_ } : {}) })
  }
  return result.length > 0 ? result : null
}
