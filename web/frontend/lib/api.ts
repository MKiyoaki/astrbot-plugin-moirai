export type ApiError = { status: number; body: string }

function _getApiUrl(url: string) {
  if (typeof window === 'undefined') return url;
  // If we are in AstrBot Plugin Pages, the pathname contains this specific prefix
  if (window.location.pathname.includes('/api/pages/astrbot_plugin_moirai/moirai')) {
    return `/api/plug/moirai${url}`;
  }
  return url;
}

async function request<T>(url: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(_getApiUrl(url), {
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

// ── Stats ─────────────────────────────────────────────────────────────────
export interface PerfPhaseInfo {
  avg_ms: number
  last_ms: number
  avg_hits: number
  last_hits: number
}

export interface SessionWindowInfo {
  session_id: string
  group_id: string | null
  message_count: number
  current_rounds: number
  trigger_rounds: number
  trigger_threshold_messages: number
}

export interface PluginStats {
  personas: number
  events: number
  archived_events?: number
  locked_count: number
  impressions: number
  summaries: number
  summary_days?: number
  avg_summary_chars?: number
  groups: number
  version: string
  soul_enabled?: boolean
  active_sessions?: SessionWindowInfo[]
  summary_trigger_rounds?: number
  llm_stats?: {
    total_prompt_tokens: number
    total_completion_tokens: number
    token_usage_by_task: Record<string, { prompt: number; completion: number }>
    active_tasks: number
    total_calls: number
    failed_calls: number
    uptime_seconds: number
  }
  perf?: {
    avg_extraction_time: number
    avg_partition_time: number
    avg_distill_time: number
    avg_retrieval_time: number
    avg_recall_time: number
    avg_response_time: number
    [phase: string]: any
  }
}

export type Stats = PluginStats

export interface SoulState {
  recall_depth: number
  impression_depth: number
  expression_desire: number
  creativity: number
}

export const soul = {
  getStates: () => request<{ states: Record<string, SoulState> }>('/api/soul/states'),
}

export const stats = {
  get: () => request<PluginStats>('/api/stats'),
}

// ── Events ────────────────────────────────────────────────────────────────
export interface ApiEvent {
  id: string
  content: string
  topic: string
  summary: string
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
  bot_persona_name?: string | null
}
export interface EventsResponse { items: ApiEvent[]; total: number }
export const events = {
  list: (limit = 500) => request<EventsResponse>(`/api/events?limit=${limit}`),
  create: (data: Record<string, unknown>) =>
    request('/api/events', { method: 'POST', body: JSON.stringify(data) }),
  update: (id: string, data: Record<string, unknown>) =>
    request(`/api/events/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (id: string) => request(`/api/events/${id}`, { method: 'DELETE' }),
  listArchived: () => request<EventsResponse>('/api/archived_events'),
  archive: (event_id: string) => request(`/api/events/${event_id}/archive`, { method: 'POST' }),
  unarchive: (event_id: string) => request(`/api/events/${event_id}/unarchive`, { method: 'POST' }),
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
    attrs: { description?: string; content_tags?: string[]; big_five?: { O?: number; C?: number; E?: number; A?: number; N?: number }; big_five_evidence?: string | Record<string, string> }
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
export interface GraphData { enabled?: boolean; nodes: PersonaNode[]; edges: ImpressionEdge[]; group_members?: Record<string, string[]> }
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
  regenerate: (groupId: string | null, date: string) =>
    request<{ content: string }>('/api/summary/regenerate', {
      method: 'POST', body: JSON.stringify({ group_id: groupId, date }),
    }),
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
  options?: (string | { value: string; label: string })[]
  default: unknown
  min?: number
  max?: number
  step?: number
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
  providers: () => request<{ providers: { id: string; name: string }[] }>('/api/config/providers'),
}

export const auth = {
  status: () => request<{ authenticated: boolean; sudo: boolean; auth_enabled: boolean; version?: string }>('/api/auth/status'),
  login: (password: string) => request<{ ok: boolean }>('/api/auth/login', { method: 'POST', body: JSON.stringify({ password }) }),
  logout: () => request<{ ok: boolean }>('/api/auth/logout', { method: 'POST', body: '{}' }),
  sudo: (password: string) => request<{ ok: boolean }>('/api/auth/sudo', { method: 'POST', body: JSON.stringify({ password }) }),
  exitSudo: () => request<{ ok: boolean }>('/api/auth/sudo/exit', { method: 'POST', body: '{}' }),
}

// ── Global API Export ──────────────────────────────────────────────────────
export const api = {
  stats,
  events,
  graph,
  summaries,
  recall,
  admin,
  tags,
  config: pluginConfig,
  soul,
  auth,
}
