<div align="center">

# Moirai

**Three-Axis Long-Term Memory & Data Visualisation Plugin for AstrBot**

**AstrBot 三轴长期记忆与数据可视化插件**

*Episodic · Social · Narrative*

[![version](https://img.shields.io/badge/version-v0.9.2-blueviolet)](metadata.yaml)
[![python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Made with ♥ by MKiyoaki & Gariton

</div>

---

## 1. Overview · 概述

Moirai is a long-term memory plugin for [AstrBot](https://docs.astrbot.app), a multi-platform LLM chatbot framework (QQ, Telegram, WeChat, Discord, etc.). It addresses a fundamental limitation of stateless LLM deployments: the inability to maintain coherent memory across sessions, users, and platforms.

Moirai 是一款适用于 [AstrBot](https://docs.astrbot.app) 的长期记忆插件。AstrBot 是一个跨平台 LLM 聊天机器人框架，支持 QQ、Telegram、微信、Discord 等平台。本插件旨在解决无状态 LLM 部署的根本性缺陷：无法在会话、用户和平台之间保持连贯的记忆。

The core contribution of Moirai is a **three-axis memory architecture** that models conversation history along three orthogonal dimensions simultaneously, rather than collapsing all memory into a single retrieval corpus:

Moirai 的核心设计是**三轴记忆架构**，将对话历史沿三个正交维度同时建模，而非将所有记忆压缩进单一检索库：

| Axis | Entity | Description |
|------|--------|-------------|
| **Episodic** · 情节轴 | `Event` | Discrete conversation windows with topics, summaries, tags, and salience scores · 离散对话窗口，含主题、摘要、标签与显著度评分 |
| **Social** · 社交轴 | `Impression` | Directional interpersonal relationships modelled on the Interpersonal Circumplex (IPC) · 基于人际环 (IPC) 模型的有向人际关系 |
| **Narrative** · 叙事轴 | `Summary` | Periodic group digests capturing mood dynamics and key interactions · 周期性群组摘要，记录情绪动态与关键交互 |

All three axes share a unified time coordinate and cross-reference via `event_id`, enabling retrieval that is simultaneously event-specific, person-specific, and temporally coherent.

三条轴共享统一时间坐标，并通过 `event_id` 相互交叉引用，使检索结果能够同时做到事件精准、人物精准与时序连贯。

Moirai is not a general-purpose RAG framework. It is optimized for chat memory in consumer deployments (single user / small group chat), prioritizing token efficiency and explainability over raw benchmark performance.

Moirai 并非通用 RAG 框架，而是针对消费级部署（单用户 / 小型群聊）中的对话记忆场景进行优化，以 Token 效率和可解释性为优先目标，而非追求原始检索基准分数。

---

## 2. Features · 功能特性

### 2.1 Three-Axis Memory Model · 三轴记忆模型

- **Episodic Axis (Event Flow)**: Raw messages are accumulated in a `MessageWindow` and closed into discrete `Event` records upon boundary detection. Each event stores a structured summary, topic label, semantic tags, salience score, and participant list.
  **情节轴（事件流）**：原始消息在 `MessageWindow` 中累积，边界触发时关闭并写入离散的 `Event` 记录。每条事件包含结构化摘要、主题标签、语义标签、显著度评分与参与者列表。

- **Social Axis (Impression Graph)**: Interpersonal impressions are maintained as directed `Impression` edges on a 2D plane (Benevolence × Power) derived from the Big Five personality model. The graph is queryable and visualized in the WebUI.
  **社交轴（印象图谱）**：人际印象以有向 `Impression` 边的形式维护在由 Big Five 人格模型推导的二维平面（亲和度 × 权力感）上。图谱可查询，并在 WebUI 中可视化呈现。

- **Narrative Axis (Summaries)**: A periodic task generates Markdown group digests (`YYYY-MM-DD.md`) capturing main topics, event sequences, and mood dynamics. These files are human-readable and editable; edits are merged back to the database via a file watcher.
  **叙事轴（摘要）**：周期任务生成 Markdown 群组摘要（`YYYY-MM-DD.md`），记录主要话题、事件序列和情绪动态。这些文件可直接阅读与编辑；修改内容由文件监听器自动合并回数据库。

### 2.2 Hybrid Retrieval (BM25 + Vector) · 混合检索

On every LLM call, Moirai performs a **zero-hot-path** retrieval:

每次 LLM 调用前，Moirai 执行**零热路径延迟**检索：

1. Parallel BM25 search (SQLite FTS5) and vector search (sqlite-vec) — each returning top-20 candidates
   并行执行 BM25 搜索（SQLite FTS5）与向量搜索（sqlite-vec），各返回 top-20 候选
2. Reciprocal Rank Fusion (RRF) to merge ranked lists
   通过互惠排名融合（RRF）合并两路排名列表
3. Greedy fill into a configurable token budget (default 800 tokens), ranked by `salience × recency_decay × relevance`
   按 `显著度 × 时间衰减 × 相关度` 贪心填充至可配置的 Token 预算（默认 800 tokens）
4. Optional weighted-random (Softmax) sampling as an alternative to deterministic Top-K
   可选 Softmax 加权随机采样，替代确定性 Top-K

If the embedding model is unavailable, retrieval degrades gracefully to keyword-only BM25.

若 Embedding 模型不可用，检索自动降级为纯 BM25 关键词搜索，不影响主流程。

### 2.3 Event Boundary Detection · 事件边界检测

Event windows are segmented by four heuristic signals — no LLM required:

事件窗口通过四个启发式信号分段，无需 LLM：

| Signal · 信号 | Default Threshold · 默认阈值 |
|--------|-------------------|
| Idle time gap · 空闲时间间隔 | 30 minutes · 30 分钟 |
| Topic drift (cosine distance from rolling centroid) · 话题漂移（与滚动质心的余弦距离） | 0.6 |
| Message count hard cap · 消息数量硬上限 | 50 messages · 50 条 |
| Duration hard cap · 时长硬上限 | 60 minutes · 60 分钟 |

Topic drift detection uses an **O(1) incremental centroid update**: each new message embedding is folded into the running mean vector, avoiding full recomputation.

话题漂移检测采用 **O(1) 增量质心更新**：每条新消息的向量增量式折叠入运行均值向量，避免全量重算。

### 2.4 Social Relationship Inference (IPC Model) · 社交关系推断（IPC 模型）

Big Five personality scores (O/C/E/A/N) are extracted during event processing via the LLM. These scores are mapped to IPC coordinates using:

Big Five 人格评分（O/C/E/A/N）在事件处理阶段由 LLM 提取，并通过以下公式映射至 IPC 坐标：

```
Benevolence = 0.70 × Agreeableness + 0.35 × Extraversion − 0.20 × Neuroticism
Power       = 0.70 × Extraversion  + 0.35 × Conscientiousness − 0.15 × Neuroticism
```

Impressions are updated using exponential moving average (EMA, configurable α). Each `Impression` record carries an IPC octant label (e.g. 亲和 / 掌控 / 冷淡), benevolence/power coordinates, affect intensity, and r² octant-fit confidence.

印象使用指数移动平均（EMA，α 可配置）更新。每条 `Impression` 记录包含 IPC 象限标签（如 亲和 / 掌控 / 冷淡）、亲和度/权力感坐标、情感强度及 r² 象限拟合置信度。

### 2.5 Soul Layer *(optional, default: off)* · Soul Layer（可选，默认关闭）

An experimental 4-dimensional emotional state vector (`recall_depth`, `impression_depth`, `expression_desire`, `creativity`) that decays per turn and shifts in response to retrieved memory content. When enabled, the state vector modulates prompt construction.

实验性的四维情绪状态向量（`recall_depth`、`impression_depth`、`expression_desire`、`creativity`），每轮对话衰减，并随检索到的记忆内容发生偏移。启用后，该状态向量将参与 Prompt 构建的调制。

### 2.6 WebUI Dashboard · WebUI 管理面板

A Next.js 16 + shadcn/ui administration panel (default port: 2655) providing full visibility into all three memory axes. Supports dark/light theme, multiple color schemes, two-tier authentication (login + sudo), and trilingual UI.

基于 Next.js 16 + shadcn/ui 构建的管理面板（默认端口 2655），提供三轴记忆的完整可视化与操作能力。支持深色/浅色主题、多套配色方案、双层认证（登录 + Sudo 提权）以及中英日三语界面。

### 2.7 Modular Design · 模块化设计

Every major subsystem can be independently toggled:

每个主要子系统均可独立开关：

| Feature · 功能 | Config Key | Default · 默认 |
|---------|------------|---------|
| WebUI Panel · WebUI 面板 | `webui_enabled` | `true` |
| Semantic Search · 语义检索 | `embedding_enabled` | `true` |
| Topic Drift Detection · 话题漂移检测 | `boundary_topic_drift_enabled` | `true` |
| Social Graph (IPC) · 社交图谱 | `relation_enabled` | `true` |
| Group Summaries · 群组摘要 | `summary_enabled` | `true` |
| Persona Synthesis · 人格合成 | `persona_synthesis_enabled` | `true` |
| Salience Decay · 显著度衰减 | `decay_enabled` | `true` |
| Auto Cleanup · 自动清理 | `memory_cleanup_enabled` | `true` |
| Soul Layer | `soul_enabled` | `false` |
| Markdown Projection · Markdown 投影 | `markdown_projection_enabled` | `true` |
| VCM State Machine · VCM 状态机 | `vcm_enabled` | `true` |

---

## 3. Installation · 安装

### Requirements · 依赖

| Dependency · 依赖 | Version · 版本 | Note · 说明 |
|------------|---------|------|
| Python | ≥ 3.10 | Required · 必需 |
| AstrBot | latest | Required host framework · 必需宿主框架 |
| `aiosqlite` | ≥ 0.19 | Auto-installed · 自动安装 |
| `sqlite-vec` | ≥ 0.1 | Auto-installed; enables vector search · 自动安装；启用向量检索 |
| `sentence-transformers` | ≥ 3.0 | **Recommended**; required for local embedding (~100 MB model download on first run) · **推荐**；本地 Embedding 所需（首次运行下载约 100 MB 模型） |
| `bcrypt` | ≥ 4.0 | **Recommended**; required for WebUI password hashing (falls back to SHA-256 with warning) · **推荐**；WebUI 密码哈希所需（缺失时降级为 SHA-256 并输出警告） |

### Install via AstrBot Plugin Manager · 通过 AstrBot 插件市场安装

Search for `astrbot_plugin_moirai` in the AstrBot plugin marketplace and click Install.

在 AstrBot 插件市场中搜索 `astrbot_plugin_moirai`，点击安装即可。

### Manual Install · 手动安装

```bash
cd <astrbot_data_dir>/plugins
git clone https://github.com/MKiyoaki/astrbot-plugin-moirai
pip install sentence-transformers bcrypt   # optional but recommended
```

Restart AstrBot after installation. The plugin performs automatic schema migration on first run.

安装完成后重启 AstrBot。插件将在首次运行时自动执行数据库 Schema 迁移。

### First-Run Setup · 首次配置

1. Open the AstrBot admin panel and navigate to the plugin configuration page.
   打开 AstrBot 管理面板，进入插件配置页。
2. Set a WebUI password (the field is `webui_password`; leave blank for auto-generation and check logs).
   设置 WebUI 密码（字段名 `webui_password`；留空则自动生成，请查看日志获取密码）。
3. Access the WebUI at `http://<host>:<webui_port>` (default port: `2655`).
   访问 `http://<host>:<webui_port>`（默认端口 `2655`）打开 WebUI。

---

## 4. Usage · 使用指南

### 4.1 Memory Injection (Automatic) · 记忆注入（自动）

Once installed, Moirai automatically intercepts every AstrBot message event. Memory is retrieved and injected into the system prompt before each LLM call — no user action required.

安装完成后，Moirai 自动拦截所有 AstrBot 消息事件。在每次 LLM 调用前，相关记忆将被检索并注入 System Prompt，无需用户手动操作。

### 4.2 /mrm Command Reference · /mrm 指令参考

All management commands are issued via the `/mrm` command group in any chat where the bot is active. Commands require admin-level AstrBot permissions.

所有管理指令通过 `/mrm` 指令组在机器人所在的任意会话中发送，需要 AstrBot 管理员权限。

#### Info Queries · 信息查询

| Command · 指令 | Description · 说明 |
|---------|-------------|
| `/mrm status` | Plugin runtime status: registered tasks, active sessions, WebUI state · 插件运行状态：已注册任务、活跃会话、WebUI 状态 |
| `/mrm persona <PlatID>` | User persona profile: description, Big Five scores (O/C/E/A/N with percentages), evidence events · 用户人格档案：描述、Big Five 百分比、支撑事件 |
| `/mrm soul` | Current session emotional state across 4 dimensions · 当前会话的四维情绪状态 |
| `/mrm recall <keywords>` | Manual hybrid memory retrieval; returns matched events with scores · 手动混合记忆检索，返回匹配事件与评分 |

#### Action Commands · 操作指令

| Command · 指令 | Description · 说明 |
|---------|-------------|
| `/mrm webui on\|off` | Start or stop the WebUI HTTP server · 启动或停止 WebUI HTTP 服务 |
| `/mrm flush` | Clear the current session context window (database unaffected) · 清除当前会话上下文窗口（不影响数据库） |
| `/mrm language <cn\|en\|ja>` | Switch command response language (persisted across restarts) · 切换指令响应语言（重启后保留） |
| `/mrm run <task>` | Manually trigger a background task: `decay` · `synthesis` · `summary` · `cleanup` · 手动触发后台任务 |

#### Reset Commands · 重置指令 *(require 2-step confirmation — re-send within 30 s · 需二次确认，30 秒内重发)*

| Command · 指令 | Scope · 范围 |
|---------|-------|
| `/mrm reset here` | All events and summaries for the current group · 当前群所有事件与摘要 |
| `/mrm reset event <group_id>` | All events and summaries for a specific group · 指定群所有事件与摘要 |
| `/mrm reset event all` | All event records globally · 全部事件记录 |
| `/mrm reset persona <PlatID>` | Persona profile for one user · 指定用户人格档案 |
| `/mrm reset persona all` | All persona profiles · 全部人格档案 |
| `/mrm reset all` | All plugin data (events, personas, projection files) · 全部插件数据（事件、人格、投影文件） |

### 4.3 Key Configuration Options · 核心配置项

Full schema is in `_conf_schema.json`. Commonly adjusted options:

完整配置项见 `_conf_schema.json`，常用配置如下：

```yaml
# Embedding · 向量嵌入
embedding_enabled: true          # Disable to use BM25 only · 关闭则仅用 BM25
embedding_provider: "local"      # "local" or "api" · 本地或远程 API
embedding_model: "BAAI/bge-small-zh-v1.5"

# Retrieval · 检索
retrieval_top_k: 10              # Max events injected per prompt · 每次注入最大事件数
retrieval_token_budget: 800      # Token ceiling for injection · 注入 Token 上限

# Event Boundary · 事件边界
boundary_time_gap_minutes: 30
boundary_topic_drift_threshold: 0.6

# Social · 社交
relation_enabled: true
impression_update_alpha: 0.4     # EMA smoothing factor · EMA 平滑系数

# Summaries · 摘要
summary_enabled: true
summary_interval_hours: 24

# WebUI
webui_port: 2655
webui_auth_enabled: true
```

---

## 5. WebUI

The WebUI is accessible at `http://<host>:<webui_port>` after authentication. It provides a complete view of all memory axes with read/write capability.

WebUI 在认证后通过 `http://<host>:<webui_port>` 访问，提供三轴记忆的完整读写视图。

| Page · 页面 | Route | Description · 说明 |
|------|-------|-------------|
| **Events · 事件流** | `/events` | Chronological event timeline with full-text search, tag filters, date range selection, inline editing, and recycle bin · 按时序展示事件，支持全文搜索、标签过滤、日期范围、内联编辑与回收站 |
| **Graph · 关系图谱** | `/graph` | Interactive Cytoscape.js relationship graph; nodes = personas, edges = impressions; IPC octant label on hover; force-simulation layout · 交互式关系图，节点为人格，边为印象；悬停显示 IPC 象限标签；力导向布局 |
| **Summary · 叙事摘要** | `/summary` | Narrative summary viewer and editor, organized by group and date; sections: Main Topics · Event List · Mood Dynamics · 按群组与日期组织的摘要查看与编辑器，含主要话题、事件列表、情绪动态三节 |
| **Recall · 记忆检索** | `/recall` | Ad-hoc hybrid memory search with configurable result limit and algorithm selector · 临时混合记忆搜索，支持自定义结果数量与算法选择 |
| **Library · 数据库** | `/library` | Tabbed data browser: Personas · Events-per-person · Impressions · Tags · 分标签数据浏览器：人格 · 人物事件 · 印象 · 标签 |
| **Stats · 统计** | `/stats` | Dashboard: event/persona counts, tag distribution, temporal activity charts, pipeline performance timing · 仪表盘：事件/人格数量、标签分布、时序活跃图、流水线性能计时 |
| **Settings · 设置** | `/settings` | Theme selector, dark/light mode, language toggle, manual task launcher, password management · 主题选择、深浅色模式、语言切换、手动任务触发、密码管理 |

### Authentication · 认证机制

The WebUI uses a two-tier auth model:

WebUI 采用双层认证模型：

- **Login · 登录** — bcrypt password stored at `data_dir/.webui_password` (not in config). Session TTL: configurable (default 24 h).
  bcrypt 密码存储于 `data_dir/.webui_password`（不在配置文件中）。会话有效期可配置，默认 24 小时。
- **Sudo · 提权** — same password re-entered to authorize write operations (delete, run tasks, change password). TTL: default 30 min.
  重新输入密码以授权写操作（删除、运行任务、修改密码）。有效期默认 30 分钟。
- **Disable · 禁用** — set `webui_auth_enabled: false` for local-only deployments.
  纯本地部署可设置 `webui_auth_enabled: false` 跳过认证。

---

## 6. Technical Implementation · 技术实现

### 6.1 Architecture Overview · 架构总览

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

### 6.2 Storage Layout · 存储布局

All persistent data is stored under the AstrBot `data/` directory:

所有持久化数据存储于 AstrBot `data/` 目录下：

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

Markdown 文件默认为**只读投影**（数据库是唯一真实来源）。例外是 `IMPRESSIONS.md`——该文件受文件监听器监控，用户编辑将以高优先级合并回数据库。

### 6.3 LLM Call Budget · LLM 调用预算

| Trigger · 触发时机 | Task · 任务 | LLM Calls · 调用次数 |
|---------|------|-----------|
| Per message (hot path) · 每条消息（热路径） | Retrieval + injection · 检索与注入 | **0** |
| Per event close · 每个事件关闭 | Core extraction · 核心提取 | **1** |
| Per event (social) · 每个事件（社交） | Big Five scoring · Big Five 评分 | **0** (if unified extraction hit) or **1** |
| Weekly · 每周 | Persona synthesis · 人格合成 | **1 per active user · 每活跃用户 1 次** |
| Daily/Weekly · 每日/每周 | Group summary · 群组摘要 | **≤ 2 per active group · 每活跃群组 ≤ 2 次** |
| Periodic · 周期 | Impression aggregation · 印象聚合 | **0** (pure math · 纯数学) |

### 6.4 Cross-Platform Identity · 跨平台身份统一

All domain entities reference a stable internal `uid` rather than platform-specific IDs. The mapping `(platform, physical_id) → uid` is maintained at the adapter boundary, enabling the same person's accounts across different platforms to be merged into a single persona node via the `/mrm` admin interface.

所有领域实体引用内部稳定的 `uid`，而非平台特定 ID。映射关系 `(platform, physical_id) → uid` 在适配器边界维护，支持通过 `/mrm` 管理指令将同一用户在不同平台的账号合并为单一人格节点。

---

## 7. Reliability & Limitations · 可靠性与局限性

### Reliability · 可靠性

- **Single-file persistence · 单文件持久化**: SQLite WAL mode with automatic pre-migration backups (`migration_auto_backup: true`). The entire memory corpus is portable in one file.
  SQLite WAL 模式，迁移前自动备份（`migration_auto_backup: true`）。全部记忆语料库可在单文件内完整迁移。

- **Graceful degradation · 优雅降级**: If the embedding model fails to load, the plugin falls back to BM25 keyword search without interrupting the chat pipeline.
  若 Embedding 模型加载失败，插件自动降级为 BM25 关键词搜索，不中断对话流程。

- **Modular failure isolation · 模块化故障隔离**: Each subsystem (social graph, summaries, soul layer) is independently toggleable. A failure in periodic tasks does not affect hot-path retrieval.
  每个子系统（社交图谱、摘要、Soul Layer）均可独立开关。周期任务的故障不影响热路径检索。

- **Two-step destructive operations · 二步式危险操作**: All `/mrm reset` commands require confirmation within 30 seconds, preventing accidental data loss.
  所有 `/mrm reset` 指令均需 30 秒内二次确认，防止误操作导致数据丢失。

### Known Limitations · 已知局限

| Area · 领域 | Limitation · 局限说明 |
|------|-----------|
| **Parallelism · 并行对话** | Parallel conversations within the same group are treated as one event (no reply-chain disentanglement). Planned for v2. · 同群内并行对话视为单一事件（无回复链解缠）。v2 规划中。 |
| **Event Structure · 事件结构** | Flat event model only; no nested or parent-child event hierarchy. Planned for v2. · 仅支持平铺事件模型，无嵌套或父子层级结构。v2 规划中。 |
| **Embedding Model · 嵌入模型** | Local model (`bge-small-zh-v1.5`) is optimized for Chinese text. English-heavy deployments should configure an API-based embedding provider. · 本地模型针对中文优化。以英文为主的部署建议配置 API 嵌入提供商。 |
| **Graph Scale · 图谱规模** | The Cytoscape graph is designed for consumer-scale deployments (< 500 nodes). Very large group histories may cause UI performance degradation. · Cytoscape 图谱面向消费级规模设计（< 500 节点）。超大群组历史可能导致 UI 性能下降。 |
| **LLM Dependency · LLM 依赖** | Extraction quality (topic labeling, Big Five scoring, summaries) depends on the capability of the configured LLM provider. Weak models produce low-confidence persona profiles. · 提取质量（话题标注、Big Five 评分、摘要）取决于所配置 LLM 的能力。弱模型将产生低置信度人格档案。 |
| **Soul Layer** | The Soul Layer is experimental. Emotional state dynamics are not grounded in a validated psychological model and may behave unexpectedly at extreme parameter values. · Soul Layer 为实验性功能，情绪状态动力学未经过验证的心理学模型支撑，极端参数下行为可能异常。 |
| **Token Budget · Token 预算** | The 800-token injection ceiling is a hard cap. In high-activity groups, older or lower-salience events may be excluded from the prompt context even if relevant. · 800 Token 注入上限为硬性限制。在高活跃群组中，较旧或显著度较低的事件即使相关也可能被排除在 Prompt 之外。 |

---

## Acknowledgements · 致谢

Design concepts studied from · 参考与致谢：
- [LivingMemory](https://github.com/lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory) — reflection threshold, time decay, hybrid retrieval RRF
- [Memorix](https://github.com/exynos967/astrbot_plugin_memorix) — scope routing, lifecycle states, graph visualization
- [Scriptor](https://github.com/ysf7762-dev/astrbot_plugin_scriptor) — identity unification, file-as-memory, sleep consolidation
- MaiBot — chat_stream as first-class concept
