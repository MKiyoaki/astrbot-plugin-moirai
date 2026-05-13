<div align="center">

<img src="static/logo.png" width="96" alt="Moirai Logo" />

# Moirai

**Three-Axis Long-Term Memory & Data Visualisation Plugin for AstrBot**

[![version](https://img.shields.io/badge/version-v0.9.11-blueviolet)](metadata.yaml)
[![python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![zh](https://img.shields.io/badge/中文-README.md-red)](README.md)

*Episodic · Social · Narrative*

Made with ♥ by MKiyoaki & Gariton

</div>

---

## ⚡ Quick Start

### Step 1: Install

**Option A: AstrBot Plugin Marketplace** (recommended)

Search for `astrbot_plugin_moirai` in the AstrBot plugin marketplace and click Install.

**Option B: Manual Clone**

```bash
cd <astrbot_data_dir>/plugins
git clone https://github.com/MKiyoaki/astrbot-plugin-moirai
```

Restart AstrBot after installation. The plugin performs automatic schema migration on first run.

> **Recommended extras** (optional but strongly advised):
> ```bash
> pip install sentence-transformers bcrypt
> ```
> - `sentence-transformers`: enables semantic vector search (~100 MB model, auto-downloaded on first run)
> - `bcrypt`: secure WebUI password hashing (degrades to SHA-256 with a warning if missing)

### Step 2: Set a WebUI Password

Go to AstrBot admin panel → Plugin Config → Moirai → set `webui_password`. Leave blank for auto-generation (check AstrBot logs for the generated password).

### Step 3: Open the WebUI

Navigate to `http://<your-server-ip>:2655` in your browser, log in, and explore the full memory dashboard.

> Default port is `2655`, configurable via `webui_port`.

---

## ✨ Features

Moirai uses a **three-axis memory architecture**, modelling conversation history along three independent dimensions:

| Axis | Entity | Description |
|------|--------|-------------|
| **Episodic** | `Event` | Discrete conversation windows with topics, summaries, tags, and salience scores |
| **Social** | `Impression` | Directed interpersonal relationships on the Interpersonal Circumplex (IPC) plane |
| **Narrative** | `Summary` | Daily group digests (`YYYY-MM-DD.md`) capturing mood dynamics and key interactions |

**Core capabilities:**

- **Hybrid Retrieval**: Parallel BM25 (FTS5) + vector search (sqlite-vec), RRF fusion, greedy fill within token budget
- **Event Boundary Detection**: Heuristic-only (no LLM) — idle time, topic drift, message count
- **WebUI Dashboard**: 7 visualization pages for full memory management
- **Soul Layer** (experimental, off by default): 4D emotional state vector that modulates reply style

**Module toggles:**

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

---

## 📋 /mrm Command Reference

All management commands require **admin-level** AstrBot permissions.

> Use `/mrm language en` to switch command responses to English.

### Info Queries

| Command | Description |
|---------|-------------|
| `/mrm status` | Plugin runtime status (tasks, active sessions, WebUI state) |
| `/mrm persona <PlatID>` | User persona profile (description, Big Five scores, evidence events) |
| `/mrm soul` | Current session emotional state across 4 dimensions |
| `/mrm recall <keywords>` | Manual hybrid memory retrieval with scores |

### Action Commands

| Command | Description |
|---------|-------------|
| `/mrm webui on\|off` | Start or stop the WebUI HTTP server |
| `/mrm flush` | Clear current session context window (database unaffected) |
| `/mrm language <cn\|en\|ja>` | Switch command response language (persisted) |
| `/mrm run decay` | Manually trigger salience decay |
| `/mrm run synthesis` | Manually trigger persona synthesis |
| `/mrm run summary` | Manually trigger group summary generation for all groups |
| `/mrm run cleanup` | Manually trigger low-salience event cleanup |
| `/mrm help` | Show help |

### Reset Commands ⚠️

> **2-step confirmation required**: first send returns a warning; **re-send the same command within 30 s** to execute.

| Command | Scope |
|---------|-------|
| `/mrm reset here` | All events and summaries for the current group |
| `/mrm reset event <group_id>` | All events and summaries for a specific group |
| `/mrm reset event all` | All event records globally |
| `/mrm reset persona <PlatID>` | One user's persona profile |
| `/mrm reset persona all` | All persona profiles |
| `/mrm reset all` | All plugin data (events, personas, projection files) |

---

## ⚙️ Configuration Quick Reference

Adjust in AstrBot plugin config panel or `_conf_schema.json`. Most common options:

| Key | Default | Description |
|-----|---------|-------------|
| `webui_port` | `2655` | WebUI HTTP port |
| `webui_auth_enabled` | `true` | Require login to access WebUI |
| `embedding_enabled` | `true` | Disable to use BM25 only |
| `embedding_provider` | `"local"` | `"local"` or `"api"` |
| `retrieval_top_k` | `10` | Max memory events injected per prompt |
| `retrieval_token_budget` | `800` | Token ceiling for memory injection |
| `boundary_time_gap_minutes` | `30` | Idle time threshold to close an event window |
| `summary_interval_hours` | `24` | Group summary generation frequency |
| `relation_enabled` | `true` | Build social relationship graph |
| `soul_enabled` | `false` | Enable emotional state (experimental) |

<details>
<summary>📖 Full Configuration Reference (expand)</summary>

### Embedding

| Key | Default | Description |
|-----|---------|-------------|
| `embedding_model` | `"BAAI/bge-small-zh-v1.5"` | HuggingFace model ID or API model name |
| `embedding_api_url` | `""` | API endpoint URL |
| `embedding_api_key` | `""` | API authentication key |
| `embedding_batch_size` | `1` | Messages per encoding batch |
| `embedding_retry_max` | `3` | Max retry attempts on failure |

### Retrieval

| Key | Default | Description |
|-----|---------|-------------|
| `retrieval_weighted_random` | `false` | Softmax sampling instead of Top-K |
| `retrieval_sampling_temperature` | `1.0` | Sampling temperature (weighted random only) |
| `retrieval_active_only` | `true` | Exclude archived events from search |
| `retrieval_recency_half_life_days` | `30.0` | Recency decay half-life in days |

### Event Boundary

| Key | Default | Description |
|-----|---------|-------------|
| `boundary_max_messages` | `50` | Hard cap on messages per event |
| `boundary_max_duration_minutes` | `60` | Hard cap on event duration (minutes) |
| `boundary_topic_drift_threshold` | `0.6` | Cosine distance threshold for topic drift |
| `boundary_topic_drift_min_messages` | `20` | Min messages before drift detection activates |

### Social Relations

| Key | Default | Description |
|-----|---------|-------------|
| `impression_update_alpha` | `0.4` | EMA smoothing factor (higher = faster response to new data) |
| `impression_event_trigger_threshold` | `5` | Shared events needed to trigger impression update |
| `impression_aggregation_interval_hours` | `168` | Impression aggregation frequency (default: weekly) |

### Decay & Cleanup

| Key | Default | Description |
|-----|---------|-------------|
| `decay_lambda` | `0.01` | Decay rate (half-life ≈ 69 days) |
| `decay_archive_threshold` | `0.05` | Salience below this → archived |
| `memory_cleanup_threshold` | `0.3` | Salience below this → permanently deleted |
| `memory_cleanup_interval_days` | `7` | Cleanup task frequency (days) |
| `memory_cleanup_retention_days` | `30` | Retention period for archived events before permanent deletion |

### Soul Layer

| Key | Default | Description |
|-----|---------|-------------|
| `soul_decay_rate` | `0.1` | Per-turn decay rate (0.1 = 10%) |
| `soul_recall_depth_init` | `0.0` | Memory retrieval drive initial value (−20 to +20) |
| `soul_impression_depth_init` | `0.0` | Social attention initial value (−20 to +20) |
| `soul_expression_desire_init` | `0.0` | Expression drive initial value (−20 to +20) |
| `soul_creativity_init` | `0.0` | Creativity initial value (−20 to +20) |

</details>

---

## 🖥️ WebUI Pages

| Page | Route | Description |
|------|-------|-------------|
| **Events** | `/events` | Event timeline with search, tag filters, inline editing, recycle bin |
| **Graph** | `/graph` | Cytoscape.js interactive relationship graph (nodes = personas, edges = impressions) |
| **Summary** | `/summary` | Group narrative summaries by date (Main Topics · Event List · Mood Dynamics) |
| **Recall** | `/recall` | Ad-hoc hybrid memory search with configurable result limit |
| **Library** | `/library` | Tabbed browser: Personas · Events-per-person · Impressions · Tags |
| **Stats** | `/stats` | Counts, tag distribution, temporal charts, pipeline performance |
| **Settings** | `/settings` | Theme, language, password, manual task launcher |

> The WebUI uses two-tier auth: **Login** (password at `data_dir/.webui_password`) + **Sudo** (re-enter password for write operations). Set `webui_auth_enabled: false` for local-only deployments.

---

## 🛡️ Reliability & Limitations

**Reliability:**
- Single-file persistence: SQLite WAL + auto pre-migration backup; corpus portable in one file
- Graceful degradation: falls back to BM25 if embedding model unavailable
- Modular isolation: social graph, summaries, Soul Layer failures don't affect hot-path retrieval
- Two-step confirmation: all `/mrm reset` commands require re-send within 30 s

**Known Limitations:**

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

<details>
<summary>🔧 Technical Implementation (Developers / Advanced Users)</summary>

### Architecture Overview

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

### LLM Call Budget

| Trigger | Task | LLM Calls |
|---------|------|-----------|
| Per message (hot path) | Retrieval + injection | **0** |
| Per event close | Core extraction | **1** |
| Per event (social) | Big Five scoring | **0** (unified extraction hit) or **1** |
| Weekly | Persona synthesis | **1 per active user** |
| Daily/Weekly | Group summary | **≤ 2 per active group** |
| Periodic | Impression aggregation | **0** (pure math) |

### IPC Social Inference Formula

Big Five scores (O/C/E/A/N) are mapped to IPC coordinates:

```
Benevolence = 0.70 × Agreeableness + 0.35 × Extraversion − 0.20 × Neuroticism
Power       = 0.70 × Extraversion  + 0.35 × Conscientiousness − 0.15 × Neuroticism
```

Impressions are updated via EMA (configurable α) and classified into eight octants (亲和 / 活跃 / 掌控 / 高傲 / 冷淡 / 孤避 / 顺应 / 谦让).

### Cross-Platform Identity

All entities use a stable internal `uid`. The mapping `(platform, physical_id) → uid` is maintained at the adapter boundary, enabling cross-platform persona merging.

</details>

---

## Acknowledgements

- [LivingMemory](https://github.com/lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory) — reflection threshold, time decay, hybrid retrieval RRF
- [Memorix](https://github.com/exynos967/astrbot_plugin_memorix) — scope routing, lifecycle states, graph visualization
- [Scriptor](https://github.com/ysf7762-dev/astrbot_plugin_scriptor) — identity unification, file-as-memory, sleep consolidation
- MaiBot — chat_stream as first-class concept
