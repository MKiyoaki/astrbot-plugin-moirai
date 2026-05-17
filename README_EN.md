<div align="center">

<img src="https://raw.githubusercontent.com/MKiyoaki/astrbot-plugin-moirai/main/logo.png" width="96" alt="Moirai Logo" />

# Moirai

**Three-Axis Long-Term Memory & Data Visualisation Plugin for AstrBot**

[![version](https://img.shields.io/badge/version-v0.12.4-blueviolet)](metadata.yaml)
[![python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-APGL-green)](LICENSE)
[![zh](https://img.shields.io/badge/中文-README.md-red)](README.md)

*Episodic · Social · Narrative*

Made with ♥ by MKiyoaki & Gariton

</div>

---

## What is this

Moirai adds three-axis persistent memory to AstrBot: conversations are automatically segmented into **episodic events**, interactions between participants accumulate as **social impressions**, and daily activity is distilled into **narrative summaries**. All three axes are retrieved and injected into context at response time — no manual management required.

Highlights:

- **Visualised memory management**: 7 WebUI pages covering the full data lifecycle — event timeline, interactive social graph, narrative summary reader, hybrid recall debugger, persona library, and live statistics. All data is browsable and editable in-browser.
- **Highly configurable**: 70+ config keys; each subsystem (social graph, summaries, Soul Layer, VCM) can be toggled independently. Retrieval strategy, event boundary thresholds, and decay rates are all tunable per deployment.
- **Memory recall costs zero extra LLM calls**: Retrieving and injecting memory on every message requires no LLM calls — no added API cost, no added latency. BM25 keyword and vector semantic search run in parallel, fused via RRF, then filled to a configurable token budget.
- **Graceful degradation**: Falls back to BM25 when the embedding model is unavailable. Social graph, summaries, and Soul Layer are fully isolated — a failure in one module does not affect the memory injection hot path.

---

## Quick Start

### Installation

**Option A: AstrBot Plugin Marketplace** (recommended)

Search for `astrbot_plugin_moirai` in the AstrBot plugin marketplace and click Install. Restart AstrBot after installation.

**Option B: Manual Clone**

```bash
cd <astrbot_data_dir>/plugins
git clone https://github.com/MKiyoaki/astrbot-plugin-moirai
```

Restart AstrBot. The plugin performs automatic schema migration on first run.

**Recommended extras** (optional but advised):

```bash
pip install sentence-transformers bcrypt
```

- `sentence-transformers`: enables semantic vector search (~100 MB model, auto-downloaded on first run)
- `bcrypt`: secure WebUI password hashing (degrades to SHA-256 with a warning if missing)

### Basic Configuration

In the AstrBot admin panel → Plugin Config → Moirai, set:

| Key | Description |
|-----|-------------|
| `webui_password` | WebUI login password. Leave blank for auto-generation (check AstrBot logs). |
| `webui_port` | WebUI port, default `2655` |

### Verify the Plugin is Working

1. Open `http://<your-server-ip>:2655` in a browser and log in
2. Chat with the bot in AstrBot, then send `/mrm status`
3. If `active_sessions` is non-empty and the `events` count is growing, the memory pipeline is running correctly

---

## User Guide

### What the Plugin Does Automatically

| When | Action |
|------|--------|
| Every message | Retrieve historical events and inject into context; append message to the current event window; compute vector embedding in background |
| Conversation idle / topic drift | Close the current event window; trigger async extraction (topic, summary, tags, Big Five) |
| Daily | Salience decay · Group narrative summaries · Low-salience event cleanup |
| Weekly | Persona synthesis · Social impression aggregation |

### /mrm Command Reference

All commands require **admin-level** AstrBot permissions. Send `/mrm language en` to switch responses to English.

**Info Queries**

| Command | Description |
|---------|-------------|
| `/mrm status` | Plugin runtime status (tasks, active sessions, WebUI state) |
| `/mrm recall <keywords>` | Manual hybrid memory retrieval with scores |
| `/mrm persona <PlatID>` | User persona profile (description, Big Five scores, evidence events) |
| `/mrm soul` | Current session emotional state across 4 dimensions (requires Soul Layer) |

**Action Commands**

| Command | Description |
|---------|-------------|
| `/mrm flush` | Clear current session context window (database unaffected) |
| `/mrm webui on\|off` | Start or stop the WebUI HTTP server |
| `/mrm language <cn\|en\|ja>` | Switch command response language (persisted) |
| `/mrm run decay` | Manually trigger salience decay |
| `/mrm run synthesis` | Manually trigger persona synthesis |
| `/mrm run summary` | Manually trigger group summary generation for all groups |
| `/mrm run cleanup` | Manually trigger low-salience event cleanup |
| `/mrm help` | Show help |

**Reset Commands ⚠️**

> **2-step confirmation required**: first send returns a warning; **re-send the same command within 30 s** to execute.

| Command | Scope |
|---------|-------|
| `/mrm reset here` | All events and summaries for the current group |
| `/mrm reset event <group_id>` | All events and summaries for a specific group |
| `/mrm reset event all` | All event records globally |
| `/mrm reset persona <PlatID>` | One user's persona profile |
| `/mrm reset persona all` | All persona profiles |
| `/mrm reset all` | All plugin data (events, personas, projection files) |

### WebUI Pages

| Page | Route | Description |
|------|-------|-------------|
| Events | `/events` | Event timeline with search, tag filters, inline editing, recycle bin |
| Graph | `/graph` | Interactive relationship graph (nodes = personas, edges = impressions); click nodes to view evidence events |
| Summary | `/summary` | Group narrative summaries by date (Main Topics · Event List · Mood Dynamics) |
| Recall | `/recall` | Ad-hoc hybrid memory search with configurable result limit and RRF scores |
| Library | `/library` | Tabbed browser: Personas · Events-per-person · Impressions · Tags |
| Stats | `/stats` | Counts, tag distribution, temporal charts, pipeline performance |
| Settings | `/settings` | Theme, language, password, manual task launcher |

The WebUI uses two-tier auth: **Login** (password at `data_dir/.webui_password`) + **Sudo** (re-enter password for write operations). Set `webui_auth_enabled: false` for local-only deployments.

---

## Advanced Configuration & Tuning

### Module Toggles

| Feature | Config Key | Default |
|---------|------------|---------|
| WebUI Panel | `webui_enabled` | ✅ on |
| Semantic Search | `embedding_enabled` | ✅ on |
| Topic Drift Detection | `boundary_topic_drift_enabled` | ✅ on |
| Social Graph (IPC) | `relation_enabled` | ✅ on |
| Group Summaries | `summary_enabled` | ✅ on |
| Persona Synthesis | `persona_synthesis_enabled` | ✅ on |
| Salience Decay | `decay_enabled` | ✅ on |
| Auto Cleanup | `memory_cleanup_enabled` | ✅ on |
| Soul Layer | `soul_enabled` | ❌ off |
| Markdown Projection | `markdown_projection_enabled` | ✅ on |
| VCM State Machine | `vcm_enabled` | ✅ on |

### Memory Quality Tuning

The parameters below have the most impact on memory quality; defaults are appropriate for most deployments.

**Retrieval & Injection**

| Key | Default | Description |
|-----|---------|-------------|
| `retrieval_top_k` | `10` | Max memory events injected per prompt |
| `retrieval_token_budget` | `800` | Token ceiling for memory injection |
| `retrieval_active_only` | `true` | Exclude archived events from search |

**Event Boundaries**

| Key | Default | Description |
|-----|---------|-------------|
| `boundary_time_gap_minutes` | `30` | Idle time threshold to close an event window |
| `boundary_max_messages` | `50` | Hard cap on messages per event |
| `boundary_topic_drift_threshold` | `0.6` | Cosine distance threshold for topic drift (lower = more sensitive) |

**Embedding (API mode)**

| Key | Default | Description |
|-----|---------|-------------|
| `embedding_provider` | `"local"` | `"local"` or `"api"` |
| `embedding_api_url` | `""` | API endpoint URL |
| `embedding_api_key` | `""` | API authentication key |
| `embedding_model` | `"BAAI/bge-small-zh-v1.5"` | HuggingFace model ID or API model name |

**Decay & Cleanup**

| Key | Default | Description |
|-----|---------|-------------|
| `decay_lambda` | `0.01` | Decay rate (half-life ≈ 69 days) |
| `memory_cleanup_threshold` | `0.3` | Salience below this → permanently deleted |
| `memory_cleanup_retention_days` | `30` | Retention period for archived events before permanent deletion |

### FAQ

**WebUI is unreachable**

Check: ① `webui_enabled` is `true`; ② port `webui_port` (default 2655) is open in the firewall; ③ no WebUI startup errors in AstrBot logs.

**Embedding model download fails**

The local model is downloaded from HuggingFace on first start and may time out on restricted networks. Solutions: switch to `embedding_provider: "api"` with a remote provider, or set the `HF_ENDPOINT` environment variable to a mirror.

### Known Limitations

| Area | Limitation |
|------|-----------|
| Parallelism | Parallel conversations in the same group treated as one event (no reply-chain disentanglement) — v2 planned |
| Event structure | Flat model only; no nested or hierarchical events — v2 planned |
| Embedding model | Local model optimized for Chinese; English-heavy deployments should use an API provider |
| Graph scale | Designed for < 500 nodes; very large group histories may degrade UI performance |
| LLM quality | Extraction quality depends on configured LLM capability |
| Soul Layer | Experimental; may behave unexpectedly at extreme parameter values |
| Token budget | 800-token hard cap; relevant events may be excluded in high-activity groups |

---

## Technical Architecture (Developers)

### Three-Axis Memory Model

| Axis | Entity | Description |
|------|--------|-------------|
| Episodic | `Event` | Discrete conversation windows with topics, summaries, tags, and salience scores |
| Social | `Impression` | Directed interpersonal relationships on the Interpersonal Circumplex (IPC) plane |
| Narrative | `Summary` | Daily group digests (`YYYY-MM-DD.md`) capturing mood dynamics and key interactions |

### Data Flow & RAG Pipeline

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

**LLM Call Budget**

| Trigger | Task | LLM Calls |
|---------|------|-----------|
| Per message (hot path) | Retrieval + injection | **0** |
| Per event close | Core extraction | **1** |
| Per event (social) | Big Five scoring | **0** (unified extraction hit) or **1** |
| Weekly | Persona synthesis | **1 per active user** |
| Daily/Weekly | Group summary | **≤ 2 per active group** |
| Periodic | Impression aggregation | **0** (pure math) |

### Storage Layout

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

Single-file persistence: SQLite WAL + automatic pre-migration backup; the entire corpus is portable in one file.

### Social Inference (IPC Model)

Big Five scores (O/C/E/A/N) are mapped to IPC coordinates:

```
Benevolence = 0.70 × Agreeableness + 0.35 × Extraversion − 0.20 × Neuroticism
Power       = 0.70 × Extraversion  + 0.35 × Conscientiousness − 0.15 × Neuroticism
```

Impressions are updated via EMA (configurable α) and classified into eight octants (亲和 / 活跃 / 掌控 / 高傲 / 冷淡 / 孤避 / 顺应 / 谦让).

All entities use a stable internal `uid`. The mapping `(platform, physical_id) → uid` is maintained at the adapter boundary, enabling cross-platform persona merging.

---

## Acknowledgements

- [LivingMemory](https://github.com/lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory) — reflection threshold, time decay, hybrid retrieval RRF
- [Memorix](https://github.com/exynos967/astrbot_plugin_memorix) — scope routing, lifecycle states, graph visualization
- [Scriptor](https://github.com/ysf7762-dev/astrbot_plugin_scriptor) — identity unification, file-as-memory, sleep consolidation
- MaiBot — chat_stream as first-class concept
