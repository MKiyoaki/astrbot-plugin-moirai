# Project: AstrBot Memory Plugin (Working Name: TBD)

## What This Project Is

A long-term memory plugin for [AstrBot](https://docs.astrbot.app), a multi-platform LLM chatbot framework (QQ, Telegram, WeChat, Discord, etc.). The plugin provides cross-platform unified memory management for chatbots deployed in private and group chat scenarios.
This is a fresh implementation, not a fork of any existing AstrBot memory plugin. We have studied LivingMemory, Memorix, and Scriptor in depth and synthesized lessons from each, but the architecture below is our own.

## Design Philosophy

The core thesis is that chatbot memory should be organized along three orthogonal axes simultaneously, not collapsed into one:

1. Episodic axis: what happened, when, with whom (Event Flow)
2. Social axis: who thinks what about whom (Relation Graph)
3. Narrative axis: what does it all mean over time (Summarised Memory)

Existing solutions tend to pick one axis and force the other two through it. We keep all three as first-class citizens, unified by a shared time coordinate and a shared event_id index.

## Non-Goals

Not a general-purpose RAG framework. Optimized for chat memory, will not generalize well to document QA.

Not a replacement for AstrBot's built-in Auto Context Compression. The plugin handles long-term memory only; short-term context compression is delegated to the host framework.

Not aiming for SOTA benchmark scores. Target is consumer deployment (single user / small group), prioritizing token efficiency and explainability over raw retrieval accuracy.

## Architecture Overview
```
Raw Messages (from AstrBot event stream)
       │
       ▼
[Event Boundary Detector]    ← simple heuristics, no LLM
       │
       ▼ (on event close)
[LLM Event Extractor]        ← single LLM call per event
       │
       ▼
       ┌─────────────────────────────────────────────┐
       │  Domain Model Layer (pure Python dataclasses) │
       │  Persona | Event | Impression                │
       └─────────────────────────────────────────────┘
       │
       ▼
[Repository Layer]           ← abstract interface
       │
       ├─► SQLite + FTS5 + sqlite-vec (single file: structured + keyword + vector)
       └─► Markdown Projector (read-only user-facing files)

Periodic Tasks (cron-style, not on hot path):
  • Impression aggregation    — weekly
  • Persona profile synthesis — weekly
  • Summarised Memory render  — daily/weekly
  • Importance decay          — daily
```

## Core Domain Model

Three first-class entities:

```python
python@dataclass
class Persona:
    ...

@dataclass
class Event:
    ...

@dataclass
class Impression:
    ...
```

Bot itself is a Persona node. Impressions are directional (observer → subject), so `Impression(A->B) != Impression(B->A)`.


## Developing Principle

This project has frontend WebUI module in `web/`, and backend engine in  `core/`. 

- When developing frontend, you should only check the files within `web/`, when developing backend, you should only check `core/`. You MUST ask for permission if you need to check over, including when you are developing cross-frontend-backend functionalities.
- When developing `core/`, if you need to know the AstrBot API, check: https://docs.astrbot.app/dev/star/plugin-new.html. You MUST NOT scan the disk of the user to find the AstrBot Implementation. 
- When coding, always considering the functionalities and seek for possible abstraction, including the implementation of registry pattern, managers, data types, hooks. 
- When coding, always check the existing APIs of existing modules at first. 
- When developing frontend and WebUI, you must retrieve https://ui.shadcn.com/docs/components to understand the API of components. 

## WebUI Module

The WebUI is intentionally outside `core/` because it is a **presentation/admin layer** with a different lifecycle than the data engine: it can be disabled, replaced, or extended by other plugins without touching the memory pipeline.

**Frontend stack**: Next.js 16 (App Router) + shadcn/ui (base-nova style, using `@radix/react` headless primitives — NOT Radix UI). All pages are Client Components. Theme managed by `next-themes`. API calls are proxied from `/api/*` to the Python backend via `next.config.mjs` rewrites.

### Layout

```
web/frontend/
├── app/                 # Next.js App Router pages
│   ├── layout.tsx       # Root layout: ThemeProvider + AppProvider + AppShell
│   ├── page.tsx         # Dashboard (stat cards + nav cards)
│   ├── events/page.tsx  # Event timeline + CRUD
│   ├── graph/page.tsx   # Cytoscape relation graph + CRUD
│   ├── summary/page.tsx # Summarized memory viewer/editor
│   ├── recall/page.tsx  # Semantic memory recall
│   ├── library/page.tsx # Tags/Personas/Groups/Events/Time tabs
│   └── settings/page.tsx# Theme, auth, sudo guard, tasks, demo
├── components/
│   ├── layout/          # app-shell.tsx, app-sidebar.tsx, page-header.tsx
│   ├── shared/          # login-screen.tsx, toaster.tsx, tag-selector.tsx
│   ├── events/          # event-timeline.tsx, event-dialogs.tsx
│   ├── graph/           # cytoscape-graph.tsx (dynamic import), persona-dialogs.tsx
│   └── ui/              # shadcn/ui components (button, card, dialog, etc.)
├── lib/
│   ├── i18n.ts          # All zh-CN UI strings (extend here for i18n)
│   ├── api.ts           # Typed API client; throws ApiError on failure
│   └── store.tsx        # React Context: auth, sudo, stats, toasts, rawGraph/Events
└── next.config.mjs      # API proxy: /api/* → http://localhost:${BACKEND_PORT}/api/*
```

`web/server.py` imports `core.domain.models` and `core.repository.base` (absolute imports) — `web/` depends on `core/`, never the reverse.

The legacy frontend lives in `web-legacy/` (vanilla HTML/CSS/JS SPA) and is kept for reference only — do not add features to it.

### Two-tier Authentication

- **Login** — password (bcrypt, stored at `data_dir/.webui_password`) → opaque session cookie (default 24 h). Borrowed from Scriptor.
- **Sudo** — same password re-entered to elevate session for ~30 min. Required for write operations: change password, run scheduled task on demand, future config edits. Scopes are enforced server-side via `_wrap("sudo", ...)`.
- **Disable** — `webui_auth_enabled: false` in plugin config skips both checks (only safe for purely-local deployments).

`bcrypt` is a soft import: missing `bcrypt` package degrades to sha256 with a warning (dev only — production should `pip install bcrypt`).

### Plugin Composition via PanelRegistry

This plugin acts as a **WebUI host** for the memory ecosystem. Other AstrBot plugins (B, C, …) that depend on this one can mount their own panels and routes without running their own HTTP server:

```python
# In plugin B that lists this plugin as a dependency
em = self.context.get_registered_star("astrbot_plugin_enhanced_memory")
if em and em.webui_registry:
    em.webui_registry.register(
        PanelManifest(
            plugin_id="astrbot_plugin_xxx",
            panel_id="my_panel",
            title="我的面板",
            icon="🔮",
            api_prefix="/api/ext/xxx",
            permission="auth",       # public | auth | sudo
        ),
        routes=[
            PanelRoute("GET", "/api/ext/xxx/data", my_handler, permission="auth"),
        ],
    )
```

Front-end fetches `/api/panels` and dynamically mounts third-party panels alongside the three built-in ones. Permission enforcement happens in `WebuiServer._wrap`, so registered routes inherit the same auth model.

### Visual Design (Memorix-inspired, shadcn/ui implementation)

- **Density slider** on Event Flow: client-side filter that keeps top-N events by salience (Memorix's saliency-density pattern).
- **LOD on zoom**: Cytoscape node labels are hidden below `zoom < 0.6` to keep large graphs legible.
- **Cytoscape theming**: oklch CSS variables are resolved through canvas at render time so Cytoscape (canvas-based) picks up shadcn theme colors correctly.
- **Graph layout**: Connected nodes use concentric layout; isolated nodes are manually positioned to the right of the connected cluster bounding box.
- **Dark/light theme toggle** via `next-themes` (`useTheme()` + `setTheme()`). Cytoscape re-initializes on theme class change.
- **Sidebar grouping**: nav items grouped under `可视化` / `工具` / `管理` using shadcn `<SidebarGroup>` + `<SidebarGroupLabel>`.
- **Toast**: center-bottom fixed via custom `Toaster` component reading from AppContext toasts array.
- **Frontend build environment**: Node.js lives in the `node` conda env (`/Users/kiyoaki/miniconda3/envs/node/bin/node`). Prepend it to PATH before running npm: `export PATH="/Users/kiyoaki/miniconda3/envs/node/bin:$PATH"`. Build command: `cd web/frontend && npm run build` (output to `web/frontend/output/`).
- **Tag Selector**: Popover-based combobox; Enter/comma to add new tags, backspace to remove.
- **Sudo guard settings**: Configurable via Settings page; `sudoGuardEnabled` + `sudoGuardMinutes` stored in localStorage. 0 minutes = always-sudo mode (shows Unlock badge instead of toggle).
- **Event timeline**: shadcn `Card` grouped-by-thread vertical layout (replaces legacy SVG canvas). Uses colored `border-left` for thread accent; adapts to light/dark theme via Tailwind utility classes only — no inline background color.
- **Persona confidence is read-only**: never expose a confidence slider in create/edit persona dialogs. Confidence is ML-derived. New persona initial value comes from `app.defaultPersonaConfidence` (settings-configurable, default 0.5, stored in localStorage as `em_default_persona_confidence`). Edit persona must preserve the existing `node.data.confidence` and pass it back to the API unchanged.
- **Searchable combobox pattern**: follow `TagSelector` / `EventInheritPicker` — Popover + Input + filtered scrollable list. No `Command` component is installed; do not add it.

**When editing the front-end:**

1. **Never introduce emojis** for UI chrome. Use Lucide React components (`import { Icon } from 'lucide-react'`). Emojis are acceptable only inside user-generated content.
2. **Use `render` prop** (not `asChild`) for polymorphic `SidebarMenuButton` and other base-ui components: `<SidebarMenuButton render={<Link href="..." />}>`.
3. **`size` prop only on `<Card>`**, not on `<CardHeader>` or `<CardContent>` — those inherit sizing via CSS group selectors (`group-data-[size=sm]/card:*`).
4. **Slider `onValueChange`** receives `number | readonly number[]`; always use `v => Array.isArray(v) ? v[0] : v` pattern.
5. **Select `onValueChange`** receives `string | null`; use `v ?? ''` or `v ?? defaultValue`.
6. **PopoverTrigger** does not support `asChild`; render content directly inside `<PopoverTrigger>`.
7. All UI strings must go through `lib/i18n.ts`. Do not hard-code Chinese text in components.

### Configurable Items (in `_conf_schema.json`)

| Key | Default | Note |
|-----|---------|------|
| `webui_enabled` | `true` | Master switch |
| `webui_port` | `2653` | Bind port |
| `webui_auth_enabled` | `true` | Toggle auth middleware |
| `webui_session_hours` | `24` | Login session TTL |
| `webui_sudo_minutes` | `30` | Sudo elevation TTL |

Password is **never** stored in `_conf_schema.json` (sensitive); it's set via the WebUI's first-run flow and persisted to `data_dir/.webui_password`.

## Backend Design
### Event Boundary Detection (v1 — Intentionally Simple)

Do not over-engineer this. v1 uses three signals only:

```
Trigger new event when ANY of:
  1. time_gap_since_last_message > 30 minutes
  2. message_count_in_window >= 20 AND topic_drift > 0.6
  3. (hard cap) message_count >= 50 OR window_duration >= 60 minutes
```

`topic_drift` = cosine distance between embeddings of (first message of current window) and (latest message). Single embedding model call per signal check, locally cached.
v1 explicitly does not handle:

parallel conversations in the same group (treated as one event)
nested events (parent-child structure)
reply-chain disentanglement
hysteresis / debouncing

These are all future work. The simple version is sufficient to validate the ontology.

### Storage Layout
```
data/plugins/<plugin_name>/data
├── db/
│   └── core.db          # SQLite WAL: events, personas, impressions, fts5, vec0 (sqlite-vec)
├── personas/
│   └── <uid>/
│       ├── PROFILE.md   # objective info (read-only projection)
│       └── IMPRESSIONS.md  # bot's view of this person (read/write by user)
├── groups/
│   └── <gid>/
│       ├── CHARTER.md   # group character description
│       └── summaries/
│           └── <YYYY-MM-DD>.md
└── global/
    ├── SOP.md           # cross-group bot rules
    └── BOT_PERSONA.md   # bot's own persona definition
```

**Markdown files are read-only projections by default**, regenerated periodically from the database. Exception: `IMPRESSIONS.md` and user-facing profile files can be edited by users; a file watcher detects changes and merges them back to the database with high prior weight (user edits override LLM inferences).

### Identity Unification (Cross-Platform)

Following [Scriptor](https://github.com/ysf7762-dev/astrbot_plugin_scriptor)'s pattern:
```python
pythondef get_or_create_uid(physical_id: str, platform: str, sender_name: str) -> str:
    # Maps (platform, physical_id) → stable internal uid
    # Same person on QQ + Telegram can be merged into one uid via admin command
```
All Domain Model entities reference uid, never `(platform, physical_id)` directly. Platform adapters are responsible for the translation at the boundary.

### Retrieval Pipeline
On every LLM call (before generation):
```
1. Query classification (rule-based, no model):
   - is_relation_query? → query impressions table directly, format & inject
   - is_profile_query? → read PERSONA.md for the relevant uid
   - is_event_query / general → continue to RAG

2. Hybrid RAG:
   a. BM25 top-20 (FTS5) + vector top-20 (sqlite-vec vec0)
   b. RRF fusion → top-10
   c. Neighbor expansion: for each retrieved event, optionally include
      one inherit-parent and one inherit-child if they pass a relevance gate
   d. Greedy fill into token budget (default 800 tokens, hard cap)
      Sort by: salience × recency_decay × relevance_score

3. Inject as system prompt segment with clear demarcation.
```

### LLM Usage Budget
**Hot path (per user message)**: zero LLM calls outside the host model's reply generation. Retrieval is fully local.

**Background (event close)**: one LLM call per event for structured extraction. Output is a constrained JSON schema with enum-typed fields where possible to minimize tokens.

**Periodic (daily)**:

- Persona synthesis: ~1 call per active persona per day
- Impression aggregation: ~1 call per active observer-subject pair per day
- Summarised Memory: ~1 call per active group per day

Estimated total: ~20-50% more tokens than LivingMemory baseline at the same activity level. Acceptable cost for the richer ontology.

### Model Dependencies

**Required**: an LLM provider (uses AstrBot's configured provider, no separate model needed for plugin operation).

**Recommended**: a local embedding model (bge-small-zh-v1.5, ~100MB, CPU inference). Without it, semantic search degrades to keyword-only.

**Optional (off by default)**: a small local LLM (0.5B-1.5B) for write-time filtering and event boundary refinement. Useful for high-volume deployments, unnecessary for typical consumer use.

**Explicitly not used**: rerankers (overkill for short event summaries), PageRank (too heavy for consumer deployment), full GraphRAG community detection (no global queries to justify it).

## Plugin Decoupling
The social relation system is implemented as a separate logical module subscribing to the same event stream. It writes to its own `impressions` table and exposes a query API. The memory module can use these results as ranking hints but does not depend on the relation module being enabled.

This means: `relation_inference.enabled = false` should still leave the memory system fully functional; it just won't inject persona impressions into prompts.

**Code Organization Principles**

- Domain Model is pure Python — no I/O, no external dependencies. Should be unit-testable in isolation.
- Repository interfaces are abstract — production uses Chroma DB vector + Tantivy BM25, tests use in-memory implementation.
- Markdown rendering is one-way by default — DB is source of truth, files are projections. Reverse sync (file → DB) is an explicit subsystem with clear merge semantics. 
- No async on the hot path that isn't strictly necessary — group chat throughput rarely demands it; readability wins.
- Explicit configuration over inferred behavior — every threshold (event boundary, decay rate, retrieval top-k, token budget) must be configurable, with sensible defaults.
- Add changes into CHANGELOG.md for every modification. 

### Coding Conventions

- Python 3.10+ (use `match` statements where they improve clarity, not for the sake of it)
- Always refer the official documentation of [Astrbot plugins](https://docs.astrbot.app/dev/star/plugin-new.html) to use the interfaces correctly
- Type hints required for all public functions; strict mypy on the Domain Model layer
- Dataclasses (with `slots=True` for hot-path objects) over Pydantic (Pydantic only at API boundary if needed)
- `aioChroma` for async DB; never `Chroma3` directly
- HTTP clients use `httpx`, never `requests`
- Format with `ruff` before commit
- Use `pathlib.Path` to manage with path related functions, not `os.path`
- All persistent data lives under AstrBot's `data/` directory, not the plugin directory itself

### hat to Build First (Suggested Order)

1. Domain Model + Repository abstract interface + in-memory implementation + tests
2. Chroma repository implementation with schema migrations
3. Event boundary detector (the simple v1) + integration with AstrBot event stream
4. LLM event extractor with constrained output schema
5. Embedding integration + FAISS index + hybrid retrieval
6. Prompt injection at the right AstrBot pipeline stage
7. Markdown projector (read-only direction first)
8. Periodic tasks (impression aggregation, persona synthesis, summarised memory)
9. WebUI panels (Event Flow, Relation Graph, Summarised Memory)
10. Reverse sync from edited Markdown back to DB

Phases 1-6 give a working plugin. Phases 7-10 add the explainability and editability that differentiate this project from existing solutions.

### What NOT to Add Without Discussion

- Any feature that requires training or fine-tuning a model
- Community detection or hierarchical graph algorithms
- Reranker integration
- Real-time impression updates (must remain a periodic batch job)
- Reply-chain disentanglement (v2)
- Nested event structures (v2)
- Direct Markdown-as-storage (we are deliberately separating storage from projection)

### Reference Implementations Studied

- [LivingMemory](https://github.com/lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory) — borrowed: reflection threshold pattern, time decay formula, hybrid retrieval RRF
- [Memorix](https://github.com/exynos967/astrbot_plugin_memorix) — borrowed: scope routing concept, lifecycle states, graph visualization approach
- [Scriptor](https://github.com/ysf7762-dev/astrbot_plugin_scriptor) — borrowed: file-as-memory philosophy (selectively), identity unification, sleep consolidation
MaiBot — borrowed: chat_stream as first-class concept, planner-style decision making (for future when-to-speak logic)

We are explicitly not copying any of these wholesale. Each contributed one or two ideas; the synthesis is novel.