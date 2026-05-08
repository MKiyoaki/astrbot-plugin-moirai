export type ApiError = { status: number; body: string }

async function request<T>(url: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(url, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
  })
  if (!res.ok) {
    const raw = await res.text()
    let detail = raw
    try { const j = JSON.parse(raw); detail = j.error || raw } catch {}
    throw { status: res.status, body: detail } satisfies ApiError
  }
  return res.json() as Promise<T>
}

// ── Auth ──────────────────────────────────────────────────────────────────
export interface AuthStatus {
  auth_enabled: boolean
  authenticated: boolean
  sudo: boolean
  password_set: boolean
  sudo_remaining_seconds?: number
}
export const auth = {
  status: () => request<AuthStatus>('/api/auth/status'),
  login: (password: string) =>
    request('/api/auth/login', { method: 'POST', body: JSON.stringify({ password }) }),
  setup: (password: string) =>
    request('/api/auth/setup', { method: 'POST', body: JSON.stringify({ password }) }),
  logout: () => request('/api/auth/logout', { method: 'POST' }),
  sudo: (password: string) =>
    request<{ sudo_remaining_seconds: number }>('/api/auth/sudo', {
      method: 'POST', body: JSON.stringify({ password }),
    }),
  exitSudo: () => request('/api/auth/sudo/exit', { method: 'POST' }),
  changePassword: (old_password: string, new_password: string) =>
    request('/api/auth/password', {
      method: 'POST', body: JSON.stringify({ old_password, new_password }),
    }),
}

// ── Stats ─────────────────────────────────────────────────────────────────
export interface Stats {
  personas: number
  events: number
  locked_count: number
  impressions: number
  groups: number
  version: string
}
export const stats = {
  get: () => request<Stats>('/api/stats'),
}

// ── Events ────────────────────────────────────────────────────────────────
export interface ApiEvent {
  id: string
  content: string
  topic: string
  start: string
  end: string
  start_ts: number
  end_ts: number
  group: string | null
  salience: number
  confidence: number
  tags: string[]
  inherit_from: string[]
  participants: string[]
  is_locked: boolean
  status: 'active' | 'archived'
}
export interface EventsResponse { items: ApiEvent[]; total: number }
export const events = {
  list: (limit = 500) => request<EventsResponse>(`/api/events?limit=${limit}`),
  create: (data: Record<string, unknown>) =>
    request('/api/events', { method: 'POST', body: JSON.stringify(data) }),
  update: (id: string, data: Record<string, unknown>) =>
    request(`/api/events/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (id: string) => request(`/api/events/${id}`, { method: 'DELETE' }),
  recycleBin: () => request<{ items: (ApiEvent & { deleted_at?: string })[] }>('/api/recycle_bin'),
  restore: (event_id: string) =>
    request('/api/recycle_bin/restore', { method: 'POST', body: JSON.stringify({ event_id }) }),
  clearBin: () => request('/api/recycle_bin', { method: 'DELETE' }),
}

// ── Graph ─────────────────────────────────────────────────────────────────
export interface PersonaNode {
  data: {
    id: string
    label: string
    confidence: number
    attrs: { description?: string; affect_type?: string; content_tags?: string[] }
    bound_identities: { platform: string; physical_id: string }[]
    created_at: string
    last_active_at: string
    is_bot?: boolean
    msg_count?: number
  }
}
export interface ImpressionEdge {
  data: {
    id: string
    source: string
    target: string
    label: string
    affect: number
    intensity: number
    power: number
    r_squared: number
    confidence: number
    scope: string
    evidence_event_ids: string[]
    last_reinforced_at: string
    msg_count?: number
  }
}
export interface GraphData { enabled?: boolean; nodes: PersonaNode[]; edges: ImpressionEdge[] }
export const graph = {
  get: () => request<GraphData>('/api/graph'),
  createPersona: (data: Record<string, unknown>) =>
    request('/api/personas', { method: 'POST', body: JSON.stringify(data) }),
  updatePersona: (uid: string, data: Record<string, unknown>) =>
    request(`/api/personas/${uid}`, { method: 'PUT', body: JSON.stringify(data) }),
  deletePersona: (uid: string) => request(`/api/personas/${uid}`, { method: 'DELETE' }),
  updateImpression: (observer: string, subject: string, scope: string, data: Record<string, unknown>) =>
    request(`/api/impressions/${observer}/${subject}/${scope}`, { method: 'PUT', body: JSON.stringify(data) }),
}

// ── Summaries ─────────────────────────────────────────────────────────────
export interface SummaryMeta { group_id: string | null; date: string; label: string }
export const summaries = {
  list: () => request<SummaryMeta[]>('/api/summaries'),
  get: (groupId: string | null, date: string) => {
    const qs = groupId ? `group_id=${encodeURIComponent(groupId)}&date=${encodeURIComponent(date)}` : `date=${encodeURIComponent(date)}`
    return request<{ content: string }>(`/api/summary?${qs}`)
  },
  save: (groupId: string | null, date: string, content: string) =>
    request('/api/summary', { method: 'PUT', body: JSON.stringify({ group_id: groupId, date, content }) }),
}

// ── Recall ────────────────────────────────────────────────────────────────
export interface RecallResult { items: ApiEvent[]; count: number; algorithm: string }
export const recall = {
  query: (q: string, limit = 5, sessionId?: string) => {
    const params = new URLSearchParams({ q, limit: String(limit) })
    if (sessionId) params.set('session_id', sessionId)
    return request<RecallResult>(`/api/recall?${params}`)
  },
}

// ── Admin ─────────────────────────────────────────────────────────────────
export const admin = {
  runTask: (name: string) =>
    request<{ ok: boolean }>('/api/admin/run_task', { method: 'POST', body: JSON.stringify({ name }) }),
  injectDemo: () => request<{ seeded: { personas: number; events: number; impressions: number } }>('/api/admin/demo', { method: 'POST' }),
  panels: () => request<{ panels: { plugin_id: string; title: string }[] }>('/api/panels'),
}

// ── Tags ─────────────────────────────────────────────────────────────────
export const tags = {
  list: () => request<{ tags: { name: string; count: number }[] }>('/api/tags').catch(() => ({ tags: [] })),
}

// ── Plugin Config ─────────────────────────────────────────────────────────
export interface ConfSchemaField {
  description: string
  hint?: string
  type: 'bool' | 'int' | 'float' | 'string' | 'text' | 'object' | 'list' | 'select'
  options?: string[]
  default: unknown
}
export interface PluginConfigResponse {
  schema: Record<string, ConfSchemaField>
  values: Record<string, unknown>
}
export const pluginConfig = {
  get: () => request<PluginConfigResponse>('/api/config'),
  update: (values: Record<string, unknown>) =>
    request<{ ok: boolean; saved: string[] }>('/api/config', {
      method: 'PUT', body: JSON.stringify(values),
    }),
}
