# Astrbot Plugin - Enhanced Memory (Moirai)

Version: `0.7.12`

Author: `MKiyoaki`, `Gariton`

**Description**: 基于"三轴记忆模型"与"人际环 (IPC)"理论的 AI Agent 长期记忆系统。将聊天记忆沿情节轴（Event）、社会关系轴（Impression）、叙事轴（Summary）三个维度独立建模，赋予 Bot 跨会话的社交一致性与动态性格。

## Installation

## Getting Start

## Implementation Details

本节描述**当前实际实现**的数据流，而非设计草稿。所有 LLM 调用均走 AstrBot 配置的 Provider，不需要独立部署模型服务。

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
 Boundary Detection
 Context Injection → LLM
```

---

### ① 热路径（每条消息，零 LLM 调用）

每条入站消息同步执行，不阻塞 AstrBot 主线程的 LLM 生成。

```
AstrBot 原始消息
    │
    ▼
[IdentityResolver]
    ├─ (platform, physical_id) → 内部稳定 uid
    └─ 内存缓存：同一用户后续消息不重复打 DB
    │
    ▼
[MessageRouter / EventBoundaryDetector]
    启发式判断，无 LLM，无 Encoder：
    ├─ 距上条 > 30 min            → 关闭当前窗口，开新窗口
    ├─ 消息数 ≥ 20 且              → 关闭（topic drift 检测）
    │  cosine(first_msg, last_msg) > 0.6（可选 Encoder）
    └─ 硬上限：消息数 ≥ 50 或时长 ≥ 60 min → 强制关闭
    │
    ▼（窗口关闭时）
    asyncio.create_task(EventExtractor)   ← 不阻塞热路径
    │
    ▼（窗口未关闭时，继续积累）
[PromptInjector / HybridRetriever]        ← 每次 LLM 调用前执行
    ├─ 规则分类（无模型）：
    │   is_relation_query?  → 直接查 impressions 表
    │   is_profile_query?   → 读 PERSONA.md
    │   else                → Hybrid RAG
    ├─ Hybrid RAG：
    │   BM25 top-20 (FTS5) + Vector top-20 (sqlite-vec)
    │   → RRF 融合 → top-10
    │   → 邻居扩展（可选 inherit-parent/child）
    │   → 贪心填充 token budget（默认 800 token）
    └─ 注入 system prompt 片段
```

**复杂度**：O(1) per message（缓存命中后无 DB）；RAG 为 O(log N)（FTS5 + vec0 索引）。

---

### ② 事件关闭提取（异步后台，每事件 1 次 LLM 调用）

窗口关闭时由 `asyncio.create_task` 触发，不在消息热路径上。

```
MessageWindow（一批消息）
    │
    ▼
[EventExtractor.__call__]
    │
    ├─ 1. 懒初始化 Tag Seeds（首次调用，encode_batch 一次）
    ├─ 2. 获取 bot persona（list_all 一次）
    ├─ 3. 获取高频 tag（用于 LLM few-shot 引导）
    │
    ├─ 4a. 策略 = "llm"（默认）：
    │       LlmPartitioner → 整个窗口一次 LLM 调用
    │       输出：N 个事件的 JSON 数组，含分段索引
    │       字段：topic / summary / chat_content_tags / salience /
    │             confidence / inherit / participants_personality*
    │
    └─ 4b. 策略 = "semantic"：
            SemanticPartitioner → encode_batch + DBSCAN 聚类
            每个 cluster 各一次 LLM 调用（distillation prompt）
            字段同上
    │
    ▼
[Tag Normalization]
    encode_batch(all_tags) → 并发 search_canonical_tag
    → 相似度 ≥ 阈值则对齐到已有标签，否则 upsert 新标准标签
    │
    ▼
[Event Persistence]
    event_repo.upsert(event)
    encoder.encode(topic + tags) → event_repo.upsert_vector(event_id, vec)
    │
    ▼（若 IPC 启用）
    asyncio.gather(*ipc_tasks)  → ③ IPC 分析
```

**LLM 调用次数**：
- `llm` 策略：**1 次 / 事件**（批量分段 + 提取合并）
- `semantic` 策略：**N 次 / 事件**（N = 语义 cluster 数，通常 1–3）

`participants_personality*`：统一提取（Unified Extraction）模式下，同一次 LLM 调用同时返回参与者的 Big Five 评分（O/C/E/A/N，-1.0~1.0），直接写入 `BigFiveBuffer` 缓存，跳过独立的 Big Five LLM 调用。

---

### ③ IPC 社会关系分析（异步后台，每事件触发，通常零额外 LLM 调用）

与事件提取并行，在 `EventExtractor._run_ipc_analysis` 中执行。

```
[BigFiveBuffer]（每用户独立累积）
    ├─ add_message(uid, text)：累积消息，上限 2 × x_messages 条
    ├─ 若 ② 已通过 participants_personality 写入缓存 → 跳过 LLM
    └─ 若计数达 x_messages（默认 10）且缓存未命中：
           LLMBigFiveScorer → 1 次 LLM 调用，返回 [O,C,E,A,N]
           （超时 30s 则返回零向量）
    │
    ▼
[SocialOrientationAnalyzer.analyze()]
    纯数学，无 LLM：
    ├─ bigfive_to_ipc(O,C,E,A,N) → (Benevolence B, Power P)
    │      B = 0.5·A + 0.3·E − 0.2·N
    │      P = 0.4·E + 0.3·C − 0.3·A
    ├─ classify_octant(B, P) → IPC 标签（友好/掌控/活跃/孤避/…）
    ├─ EMA 更新 Impression（α = salience × 0.3，上限 0.3）
    │      B_new = (1−α)·B_old + α·B_score
    │      P_new = (1−α)·P_old + α·P_score
    ├─ derive_fields(B, P) → affect_intensity, r_squared, confidence
    │      r² = cos²(angle) — 角度拟合度，中立点默认 0.5
    └─ impression_repo.upsert(Impression)
         追加 event_id 至 evidence_event_ids（上限 100 条）
```

**LLM 调用次数**：
- 正常情况（Unified Extraction 命中）：**0 次 / 事件**
- 计数触发（每 x_messages 条消息且缓存未命中）：**1 次 / 用户**

---

### ④ 周期任务（TaskScheduler 定时，非热路径）

由 `plugin_initializer.py` 注册，通过 `TaskScheduler` 按间隔调度。

#### 4a. `daily_maintenance`（日级，默认每 86400 秒）

三个子任务顺序执行，**零 LLM 调用**：

| 子任务 | 操作 | 复杂度 |
|--------|------|--------|
| Salience Decay | 对所有 Event 执行 `salience × exp(−λ)` | O(N events) |
| Memory Cleanup | 删除 `salience < threshold` 且未锁定的事件 | O(N events) |
| Persona Projection | 将 DB 中的 Persona 渲染为 Markdown 文件 | O(P personas) |

#### 4b. `impression_recalculation`（周级，默认每 604800 秒）

纯算法重算，**零 LLM 调用**：

```
1. 批量预加载：每个涉及 uid 各查一次 list_by_participant(limit=200)
   → 构建 uid → set[event_id] 内存映射          O(U) DB 查询，U=去重uid数
2. 遍历所有 Impression：
   - derive_fields(B, P) 重算 ipc_orientation / affect_intensity /
     r_squared / confidence（保持与公式常数同步）
   - set_intersection(obs_ids, subj_ids)[-100:] 重建 evidence_event_ids
   → impression_repo.upsert                     O(I) in-memory，I=印象数
```

#### 4c. `persona_synthesis`（周级，默认每 604800 秒）

**每个 Persona 1 次 LLM 调用**：

```
对每个 Persona：
1. list_by_participant(uid) → 近期事件列表
2. 算法：Counter(chat_content_tags) → top-5 content_tags（无 LLM）
3. LLM：输入事件主题列表 → 输出 description(≤50字) + affect_type
   系统 prompt 只要求两个字段，schema 极小
```

#### 4d. `group_summary`（周级，默认每 604800 秒）

**每个群组 1 次 LLM 调用**：

```
对每个 group_id（含 None = 私聊 → global/）：
1. list_by_group(group_id) → 近期事件列表
2. LLM：输入事件摘要 + Impression 概况 + Persona 信息
   → 输出 Markdown 群组周报
3. 写入 data/groups/<gid>/summaries/<YYYY-MM-DD>.md
```

---

### LLM 调用预算汇总

| 触发时机 | 任务 | 调用次数 | 模型需求 |
|----------|------|----------|----------|
| 每条消息（热路径） | 检索 / 注入 | **0** | — |
| 每个事件关闭 | EventExtractor（llm 策略） | **1** | 主 LLM Provider |
| 每个事件关闭 | EventExtractor（semantic 策略） | **N**（cluster 数） | 主 LLM Provider |
| 每 x_messages 条消息 / 用户（缓存未命中） | BigFiveScorer | **1 / 用户** | 主 LLM Provider |
| 每日 | daily_maintenance | **0** | — |
| 每周 | impression_recalculation | **0** | — |
| 每周 | persona_synthesis | **1 / Persona** | 主 LLM Provider |
| 每周 | group_summary | **1 / 群组** | 主 LLM Provider |

典型消费者场景（10 活跃用户、5 群）：每日约 5–15 次事件提取 LLM 调用 + 每周约 15 次周期性调用，**远低于主 LLM 对话本身的调用量**。

---

### 存储布局

```
data/plugins/<plugin_name>/data/
├── db/
│   └── core.db          # SQLite WAL：events, personas, impressions
│                        #   FTS5 虚拟表（BM25 全文检索）
│                        #   sqlite-vec vec0 表（向量检索）
├── personas/
│   └── <uid>/
│       ├── PROFILE.md   # DB 投影，只读（由 Persona Projection 生成）
│       └── IMPRESSIONS.md
├── groups/
│   └── <gid>/
│       └── summaries/
│           └── <YYYY-MM-DD>.md
└── global/
    └── summaries/
        └── <YYYY-MM-DD>.md  # 私聊合并摘要
```

---

### 关键设计决策

| 设计点 | 当前实现 | 动机 |
|--------|----------|------|
| **热路径零 LLM** | 检索与上下文注入完全本地，RAG 基于 FTS5 + sqlite-vec | 不增加每条消息的延迟 |
| **三轴分离** | Event / Impression / Summary 独立表与索引 | 各轴可独立禁用、独立查询 |
| **统一提取（Unified Extraction）** | 事件提取同时输出 Big Five 评分，一次 LLM 调用替代两次 | 减少 IPC 开启时的 LLM 调用开销 |
| **算法化周期任务** | impression_recalculation / content_tags 统计不调 LLM | 避免 LLM 幻觉，降低周期成本 |
| **IPC 坐标系** | Big Five → (Benevolence, Power) → IPC 八象限 | 基于心理学模型的可解释社会关系表示 |
| **单文件 SQLite** | FTS5 + sqlite-vec 同库，无额外服务依赖 | 消费者部署友好，单文件备份 |
