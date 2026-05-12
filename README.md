# Astrbot Plugin - Enhanced Memory (Moirai)

Version: `0.7.35`

Author: `MKiyoaki`, `Gariton`

**Description**: 基于"三轴记忆模型"与"人际环 (IPC)"理论的 AI Agent 长期记忆系统。将聊天记忆沿情节轴（Event）、社会关系轴（Impression）、叙事轴（Summary）三个维度独立建模，赋予 Bot 跨会话的社交一致性与动态性格。

## Modular Features

Moirai is designed with high modularity. Almost every major feature can be independently toggled via `_conf_schema.json` or the AstrBot config panel:

| Feature | Toggle Key | Default | Description |
|---------|------------|---------|-------------|
| **WebUI Panel** | `webui_enabled` | `true` | The 3D memory dashboard (Event Flow, Graph, etc.) |
| **Semantic Search** | `embedding_enabled` | `true` | Vector-based memory recall. Falls back to BM25 if disabled. |
| **Topic Drift Detection** | `boundary_topic_drift_enabled` | `true` | Real-time conversation segmentation using embeddings. |
| **Social Graph (IPC)** | `relation_enabled` | `true` | Impression inference and relationship graph building. |
| **Group Summary** | `summary_enabled` | `true` | Daily generation of `YYYY-MM-DD.md` group summaries. |
| **Persona Synthesis** | `persona_synthesis_enabled` | `true` | Weekly generation of user profile Markdown files. |
| **Salience Decay** | `decay_enabled` | `true` | Gradual fading of importance scores for old memories. |
| **Memory Cleanup** | `memory_cleanup_enabled` | `true` | Automatic archiving/deletion of low-salience events. |
| **Soul Layer** | `soul_enabled` | `false` | Dynamic 4D emotional state tracking and prompt injection. |
| **Markdown Projection** | `markdown_projection_enabled` | `true` | Syncing database state to readable/editable `.md` files. |
| **VCM State Machine** | `vcm_enabled` | `true` | Context window optimization using Virtual Context Management. |

## Installation

## Getting Started

## Implementation Details

本节描述**当前实际实现 (v0.7.35)** 的数据流。所有 LLM 调用均走 AstrBot 配置的 Provider。本系统采用“计算减法”设计，旨在实现主流程零延迟与算力零浪费。

---

### 架构总览

```
                          ┌─────────────────────────────────────────┐
  AstrBot 消息流          │           三轴 Domain Model              │
      │                  │  Persona │ Event │ Impression            │
      ▼                  └─────────────────────────────────────────┘
 ① 热路径 (每条消息)               ▲              ▲              ▲
      │                           │              │              │
      ▼                      ② 事件关闭       ③ IPC 分析    ④ 周期任务
 Identity Resolution        (异步, 每事件)   (异步, 每事件)  (日/周, 定时)
 Background Brain Task
 Context Injection → LLM
```

---

### ① 热路径（每条消息，零阻塞，零 LLM）

消息处理完全异步化，不阻塞 AstrBot 主线程，确保对话响应毫秒级达成。

```
AstrBot 原始消息
    │
    ▼
[IdentityResolver]
    └─ (platform, physical_id) → 内部稳定 uid (缓存命中后无 DB 开销)
    │
    ▼
[MessageRouter / EventBoundaryDetector]
    ├─ 1. 消息立即入库：立即存入 MessageWindow 并允许 Bot 继续回复逻辑
    ├─ 2. 触发“脑干任务” (Background Brain Task):
    │   ├─ 单次编码 (Single-pass Encoding): 计算消息向量 v，挂载至 RawMessage
    │   ├─ 滚动质心 (Rolling Centroid): O(1) 复杂度增量维护当前窗口语义重心
    │   └─ 异步检测: 若检测到话题漂移 (Topic Drift)，给窗口打上标记
    │
    ▼（窗口关闭时）
    MessageRouter.flush_all() 等待后台任务完成 → 触发 EventExtractor
    │
    ▼（窗口未关闭时，执行 RAG）
[PromptInjector / HybridRetriever]
    ├─ 混合检索 (Hybrid RAG)：
    │   BM25 top-20 (FTS5) + Vector top-20 (sqlite-vec)
    │   → RRF 融合 → top-10 → 邻居扩展 → 贪心填充 (默认 800 token)
    └─ 注入 system prompt 片段
```

**性能特性**：
- **主循环零延迟**：向量计算与漂移检测均在后台异步进行。
- **单次编码**：每条消息在整个生命周期内仅被编码一次，向量在检测、切分、索引间全量复用。

---

### ② 事件关闭提取（异步后台，每事件 1 次 LLM 调用）

```
MessageWindow（已挂载所有消息向量）
    │
    ▼
[EventExtractor]
    ├─ 1. 向量复用：直接读取 RawMessage.embedding，跳过所有编码计算
    ├─ 2. 分段策略：
    │   ├─ "llm" (默认): 整个窗口一次 LLM 调用完成分段与提取
    │   └─ "semantic": 利用已有向量执行 DBSCAN 聚类，每个分段一次 LLM 调用
    │
    ├─ 3. 统一提取 (Unified Extraction):
    │   在提取事件的同时，顺带提取参与者的 Big Five 评分，合并 LLM 开销。
    │
    ▼
[Tag Normalization]
    向量并发比对已有标签 → 自动对齐到标准标签库 (如 "Coding" -> "技术")
```

---

### ③ IPC 社会关系分析（异步后台，通常零额外 LLM 调用）

```
[SocialOrientationAnalyzer]
    ├─ 若 ② 已通过“统一提取”获得评分 → 直接计算
    └─ 若缓存未命中且消息达标 → LLMBigFiveScorer (1 次 LLM 调用)
    │
    ▼
    纯数学计算：Big Five 映射 → IPC 坐标 (Benevolence, Power) → EMA 印象更新
```

---

### ④ 周期任务（TaskScheduler 调度，并发执行）

周期任务全面引入了 **`asyncio.gather`** 与 **`Semaphore`**，极大缩短了任务耗时。

| 任务 | 优化点 | 调用预算 |
|--------|------|--------|
| **Persona Synthesis** | **增量合成**：跳过自上次合成以来无新对话的用户；**并行处理**：并发执行 LLM 请求。 | 1 次 / 活跃 Persona / 周 |
| **Group Summary** | **内外部并行**：多群组间并发处理，单个群组内“话题总结”与“情感分析”并行执行。 | 1 次 / 活跃群组 / 日 |
| **Memory Cleanup** | 纯算法：根据衰减分值清理过期事件，无 LLM。 | 0 次 |

---

### LLM 调用预算汇总 (v0.7.35)

| 触发时机 | 任务 | 优化后的调用次数 |
|----------|------|----------|
| 每条消息 | 检索 / 注入 | **0** |
| 每个事件关闭 | 核心提取 | **1** |
| 每 x 消息 / 用户 | 人格推断 | **0** (统一提取命中) 或 1 |
| 每周 | 画像合成 | **1 / 活跃用户** |
| 每日/周 | 群组摘要 | **2 / 活跃群组** (拟进一步合并为 1) |

---

### 存储布局 (Data Layer)
系统持久化层由 **SQLite (WAL 模式)** 驱动，集成了 **FTS5 (全文搜索)** 与 **sqlite-vec (向量检索)**。数据统一存放在 `data/plugins/<plugin_name>/data/db/core.db`，支持单文件无损迁移。
