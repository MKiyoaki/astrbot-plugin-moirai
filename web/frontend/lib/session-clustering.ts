import type { ApiEvent } from '@/lib/api'

export interface EventSession {
  events: ApiEvent[]
  startTs: number
  endTs: number
}

export function dayStart(ts: number): number {
  const d = new Date(ts)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

export function buildSessions(events: ApiEvent[], timeGap: number): EventSession[] {
  const sorted = [...events]
    .filter(ev => ev?.start)
    .sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime())

  const sessions: EventSession[] = []
  for (const ev of sorted) {
    const ts = new Date(ev.start).getTime()
    const last = sessions[sessions.length - 1]
    if (last && ts - last.endTs <= timeGap) {
      last.events.push(ev)
      last.endTs = ts
    } else {
      sessions.push({ events: [ev], startTs: ts, endTs: ts })
    }
  }
  return sessions
}
