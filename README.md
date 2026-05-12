<div align="center">

# Moirai

**Three-Axis Long-Term Memory & Data Visualisation Plugin for AstrBot**

*Episodic · Social · Narrative*

[![version](https://img.shields.io/badge/version-v0.9.2-blueviolet)](metadata.yaml)
[![python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Made with ♥ by MKiyoaki & Gariton

</div>

---

## 1. Overview

Moirai is a long-term memory plugin for [AstrBot](https://docs.astrbot.app), a multi-platform LLM chatbot framework (QQ, Telegram, WeChat, Discord, etc.). It addresses a fundamental limitation of stateless LLM deployments: the inability to maintain coherent memory across sessions, users, and platforms.

The core contribution of Moirai is a **three-axis memory architecture** that models conversation history along three orthogonal dimensions simultaneously, rather than collapsing all memory into a single retrieval corpus:

| Axis | Entity | Description |
|------|--------|-------------|
| **Episodic** | `Event` | Discrete conversation windows with topics, summaries, tags, and salience scores |
| **Social** | `Impression` | Directional interpersonal relationships modelled on the Interpersonal Circumplex (IPC) |
| **Narrative** | `Summary` | Periodic group digests capturing mood dynamics and key interactions |

All three axes share a unified time coordinate and cross-reference via `event_id`, enabling retrieval that is simultaneously event-specific, person-specific, and temporally coherent.

Moirai is not a general-purpose RAG framework. It is optimized for chat memory in consumer deployments (single user / small group chat), prioritizing token efficiency and explainability over raw benchmark performance.

---

## 2. Features

### 2.1 Three-Axis Memory Model

- **Episodic Axis (Event Flow)**: Raw messages are accumulated in a `MessageWindow` and closed into discrete `Event` records upon boundary detection. Each event stores a structured summary, topic label, semantic tags, salience score, and participant list.
- **Social Axis (Impression Graph)**: Interpersonal impressions are maintained as directed `Impression` edges on a 2D plane (Benevolence × Power) derived from the Big Five personality model. The graph is queryable and visualized in the WebUI.
- **Narrative Axis (Summaries)**: A periodic task generates Markdown group digests (`YYYY-MM-DD.md`) capturing main topics, event sequences, and mood dynamics. These files are human-readable and editable; edits are merged back to the database via a file watcher.

### 2.2 Hybrid Retrieval (BM25 + Vector)

On every LLM call, Moirai performs a **zero-hot-path** retrieval:

1. Parallel BM25 search (SQLite FTS5) and vector search (sqlite-vec) — each returning top-20 candidates
2. Reciprocal Rank Fusion (RRF) to merge ranked lists
3. Greedy fill into a configurable token budget (default 800 tokens), ranked by `salience × recency_decay × relevance`
4. Optional weighted-random (Softmax) sampling as an alternative to deterministic Top-K

If the embedding model is unavailable, retrieval degrades gracefully to keyword-only BM25.

### 2.3 Event Boundary Detection

Event windows are segmented by four heuristic signals — no LLM required:

| Signal | Default Threshold |
|--------|-------------------|
| Idle time gap | 30 minutes |
| Topic drift (cosine distance from rolling centroid) | 0.6 |
| Message count hard cap | 50 messages |
| Duration hard cap | 60 minutes |

Topic drift detection uses an **O(1) incremental centroid update**: each new message embedding is folded into the running mean vector, avoiding full recomputation.

### 2.4 Social Relationship Inference (IPC Model)

Big Five personality scores (O/C/E/A/N) are extracted during event processing via the LLM. These scores are mapped to IPC coordinates using:

```
Benevolence = 0.70 × Agreeableness + 0.35 × Extraversion − 0.20 × Neuroticism
Power       = 0.70 × Extraversion  + 0.35 × Conscientiousness − 0.15 × Neuroticism
```

Impressions are updated using exponential moving average (EMA, configurable α). Each `Impression` record carries an IPC octant label (e.g. 亲和 / 掌控 / 冷淡), benevolence/power coordinates, affect intensity, and r² octant-fit confidence.

### 2.5 Soul Layer *(optional, default: off)*

An experimental 4-dimensional emotional state vector (`recall_depth`, `impression_depth`, `expression_desire`, `creativity`) that decays per turn and shifts in response to retrieved memory content. When enabled, the state vector modulates prompt construction.

### 2.6 WebUI Dashboard

A Next.js 16 + shadcn/ui administration panel (default port: 2655) providing full visibility into all three memory axes. Supports dark/light theme, multiple color schemes, two-tier authentication (login + sudo), and trilingual UI.

### 2.7 Modular Design

Every major subsystem can be independently toggled:

| Feature | Config Key | Default |
|---------|------------|---------|
| WebUI Panel | `webui_enabled` | `true` |
| Semantic Search | `embedding_enabled` | `true` |
| Topic Drift Detection | `boundary_topic_drift_enabled` | `true` |
| Social Graph (IPC) | `relation_enabled` | `true` |
| Group Summaries | `summary_enabled` | `true` |
| Persona Synthesis | `persona_synthesis_enabled` | `true` |
| Salience Decay | `decay_enabled` | `true` |
| Auto Cleanup | `memory_cleanup_enabled` | `true` |
| Soul Layer | `soul_enabled` | `false` |
| Markdown Projection | `markdown_projection_enabled` | `true` |
| VCM State Machine | `vcm_enabled` | `true` |

---

## 3. Installation

### Requirements

| Dependency | Version | Note |
|------------|---------|------|
| Python | ≥ 3.10 | Required |
| AstrBot | latest | Required host framework |
| `aiosqlite` | ≥ 0.19 | Auto-installed |
| `sqlite-vec` | ≥ 0.1 | Auto-installed; enables vector search |
| `sentence-transformers` | ≥ 3.0 | **Recommended**; required for local embedding (~100 MB model download on first run) |
| `bcrypt` | ≥ 4.0 | **Recommended**; required for WebUI password hashing (falls back to SHA-256 with warning) |

### Install via AstrBot Plugin Manager

Search for `astrbot_plugin_moirai` in the AstrBot plugin marketplace and click Install.

### Manual Install

```bash
cd <astrbot_data_dir>/plugins
git clone https://github.com/MKiyoaki/astrbot-plugin-moirai
pip install sentence-transformers bcrypt   # optional but recommended
```

Restart AstrBot after installation. The plugin performs automatic schema migration on first run.

### First-Run Setup

1. Open the AstrBot admin panel and navigate to the plugin configuration page.
2. Set a WebUI password (the field is `webui_password`; leave blank for auto-generation and check logs).
3. Access the WebUI at `http://<host>:<webui_port>` (default port: `2655`).

---

## 4. Usage

### 4.1 Memory Injection (Automatic)

Once installed, Moirai automatically intercepts every AstrBot message event. Memory is retrieved and injected into the system prompt before each LLM call — no user action required.

### 4.2 /mrm Command Reference

All management commands are issued via the `/mrm` command group in any chat where the bot is active. Commands require admin-level AstrBot permissions.

#### Info Queries

| Command | Description |
|---------|-------------|
| `/mrm status` | Plugin runtime status: registered tasks, active sessions, WebUI state |
| `/mrm persona <PlatID>` | User persona profile: description, Big Five scores (O/C/E/A/N with percentages), evidence events |
| `/mrm soul` | Current session emotional state across 4 dimensions |
| `/mrm recall <keywords>` | Manual hybrid memory retrieval; returns matched events with scores |

#### Action Commands

| Command | Description |
|---------|-------------|
| `/mrm webui on\|off` | Start or stop the WebUI HTTP server |
| `/mrm flush` | Clear the current session context window (database unaffected) |
| `/mrm language <cn\|en\|ja>` | Switch command response language (persisted across restarts) |
| `/mrm run <task>` | Manually trigger a background task: `decay` · `synthesis` · `summary` · `cleanup` |

#### Reset Commands *(require 2-step confirmation — re-send within 30 s)*

| Command | Scope |
|---------|-------|
| `/mrm reset here` | All events and summaries for the current group |
| `/mrm reset event <group_id>` | All events and summaries for a specific group |
| `/mrm reset event all` | All event records globally |
| `/mrm reset persona <PlatID>` | Persona profile for one user |
| `/mrm reset persona all` | All persona profiles |
| `/mrm reset all` | All plugin data (events, personas, projection files) |

### 4.3 Key Configuration Options

Full schema is in `_conf_schema.json`. Commonly adjusted options:

```yaml
# Embedding
embedding_enabled: true          # Disable to use BM25 only
embedding_provider: "local"      # "local" or "api"
embedding_model: "BAAI/bge-small-zh-v1.5"

# Retrieval
retrieval_top_k: 10              # Max events injected per prompt
retrieval_token_budget: 800      # Token ceiling for injection

# Event Boundary
boundary_time_gap_minutes: 30
boundary_topic_drift_threshold: 0.6

# Social
relation_enabled: true
impression_update_alpha: 0.4     # EMA smoothing factor

# Summaries
summary_enabled: true
summary_interval_hours: 24

# WebUI
webui_port: 2655
webui_auth_enabled: true
```

---

## 5. WebUI

The WebUI is accessible at `http://<host>:<webui_port>` after authentication. It provides a complete view of all memory axes with read/write capability.

| Page | Route | Description |
|------|-------|-------------|
| **Events** | `/events` | Chronological event timeline with full-text search, tag filters, date range selection, inline editing, and recycle bin |
| **Graph** | `/graph` | Interactive Cytoscape.js relationship graph; nodes = personas, edges = impressions; IPC octant label on hover; force-simulation layout |
| **Summary** | `/summary` | Narrative summary viewer and editor, organized by group and date; sections: Main Topics · Event List · Mood Dynamics |
| **Recall** | `/recall` | Ad-hoc hybrid memory search with configurable result limit and algorithm selector |
| **Library** | `/library` | Tabbed data browser: Personas · Events-per-person · Impressions · Tags |
| **Stats** | `/stats` | Dashboard: event/persona counts, tag distribution, temporal activity charts, pipeline performance timing |
| **Settings** | `/settings` | Theme selector, dark/light mode, language toggle, manual task launcher (decay · synthesis · summary · cleanup · projection · reindex), password management |

### Authentication

The WebUI uses a two-tier auth model:

- **Login** — bcrypt password stored at `data_dir/.webui_password` (not in config). Session TTL: configurable (default 24 h).
- **Sudo** — same password re-entered to authorize write operations (delete, run tasks, change password). TTL: default 30 min.
- **Disable** — set `webui_auth_enabled: false` for local-only deployments.

---

## 6. Technical Implementation

### 6.1 Architecture Overview

```
AstrBot Message Stream
        │
        ▼
 ① Hot Path (per message, 0 LLM calls)
        │  Identity Resolution → uid lookup
        │  MessageWindow accumulation
        │  Background: single-pass embedding + O(1) centroid update
        │  Hybrid RAG → system prompt injection
        │
        ▼ (on window close)
 ② Event Extraction (async, 1 LLM call per event)
        │  LLM partitioner or semantic DBSCAN clustering
        │  Unified extraction: topic / summary / tags / Big Five
        │  Tag normalization via vector similarity
        │
        ▼
 ③ IPC Analysis (async, 0 extra LLM calls if Big Five cached)
        │  Big Five → IPC coordinate mapping (pure math)
        │  EMA impression update → SQLite upsert
        │
 ④ Periodic Tasks (scheduler, concurrent)
        │  Daily:  Salience decay · Group summaries · Memory cleanup
        │  Weekly: Persona synthesis · Impression aggregation
```

### 6.2 Storage Layout

All persistent data is stored under the AstrBot `data/` directory:

```
data/plugins/<plugin_name>/data/
├── db/
│   └── core.db          # SQLite WAL: events + FTS5 + sqlite-vec (single file)
├── personas/
│   └── <uid>/
│       ├── PROFILE.md   # Read-only projection; regenerated weekly
│       └── IMPRESSIONS.md  # User-editable; changes merged back to DB
├── groups/
│   └── <gid>/
│       └── summaries/
│           └── YYYY-MM-DD.md
└── global/
    ├── SOP.md
    └── BOT_PERSONA.md
```

Markdown files are **read-only projections by default** (DB is the source of truth). The exception is `IMPRESSIONS.md`, which is monitored by a file watcher; user edits are merged back with high prior weight.

### 6.3 LLM Call Budget

| Trigger | Task | LLM Calls |
|---------|------|-----------|
| Per message (hot path) | Retrieval + injection | **0** |
| Per event close | Core extraction | **1** |
| Per event (social) | Big Five scoring | **0** (if unified extraction hit) or **1** |
| Weekly | Persona synthesis | **1 per active user** (incremental) |
| Daily/Weekly | Group summary | **≤ 2 per active group** |
| Periodic | Impression aggregation | **0** (pure math) |

### 6.4 Cross-Platform Identity

All domain entities reference a stable internal `uid` rather than platform-specific IDs. The mapping `(platform, physical_id) → uid` is maintained at the adapter boundary, enabling the same person's accounts across different platforms to be merged into a single persona node via the `/mrm` admin interface.

---

## 7. Reliability & Limitations

### Reliability

- **Single-file persistence**: SQLite WAL mode with automatic pre-migration backups (`migration_auto_backup: true`). The entire memory corpus is portable in one file.
- **Graceful degradation**: If the embedding model fails to load, the plugin falls back to BM25 keyword search without interrupting the chat pipeline.
- **Modular failure isolation**: Each subsystem (social graph, summaries, soul layer) is independently toggleable. A failure in periodic tasks does not affect hot-path retrieval.
- **Two-step destructive operations**: All `/mrm reset` commands require confirmation within 30 seconds, preventing accidental data loss.

### Known Limitations

| Area | Limitation |
|------|-----------|
| **Parallelism** | Parallel conversations within the same group are treated as one event (no reply-chain disentanglement). Planned for v2. |
| **Event Structure** | Flat event model only; no nested or parent-child event hierarchy. Planned for v2. |
| **Embedding Model** | Local model (`bge-small-zh-v1.5`) is optimized for Chinese text. English-heavy deployments should configure an API-based embedding provider. |
| **Graph Scale** | The Cytoscape graph is designed for consumer-scale deployments (< 500 nodes). Very large group histories may cause UI performance degradation. |
| **LLM Dependency** | Extraction quality (topic labeling, Big Five scoring, summaries) depends on the capability of the configured LLM provider. Weak models produce low-confidence persona profiles. |
| **Soul Layer** | The Soul Layer is experimental. Emotional state dynamics are not grounded in a validated psychological model and may behave unexpectedly at extreme parameter values. |
| **Token Budget** | The 800-token injection ceiling is a hard cap. In high-activity groups, older or lower-salience events may be excluded from the prompt context even if relevant. |

---

## Acknowledgements

Design concepts studied from:
- [LivingMemory](https://github.com/lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory) — reflection threshold, time decay, hybrid retrieval RRF
- [Memorix](https://github.com/exynos967/astrbot_plugin_memorix) — scope routing, lifecycle states, graph visualization
- [Scriptor](https://github.com/ysf7762-dev/astrbot_plugin_scriptor) — identity unification, file-as-memory, sleep consolidation
- MaiBot — chat_stream as first-class concept
