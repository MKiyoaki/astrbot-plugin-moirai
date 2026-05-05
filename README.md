# Astrbot Plugin - Enhanced Memory

Version: `0.0.1`

Author: `MKiyoaki`, `Gariton`

TODO: Add Description here

## Installation

## Getting Start


## Implementation Details

### 数据流全景
1. 原始消息 → 事件生成
```
AstrBot 事件流（QQ/Telegram/WeChat 等原始消息）
    │
    ▼
[Identity Unification]  — 平台 adapter 将 (platform, physical_id) → 内部稳定 uid
    │
    ▼
[Event Boundary Detector]  — 纯启发式，零 LLM 调用
    触发条件（满足任一）：
    ① 距上条消息 > 30 分钟
    ② 消息数 ≥ 20 且 topic_drift > 0.6
       (topic_drift = 首条消息 embedding 与最新消息 embedding 的余弦距离)
    ③ 硬上限：消息数 ≥ 50 或窗口时长 ≥ 60 分钟
```
事件边界触发后：

```
[LLM Event Extractor]  — 每个事件仅一次 LLM 调用
    输出：constrained JSON schema（字段尽量 enum 化以省 token）
    填充 Event dataclass：
    - topic, chat_content_tags, salience, participants, interaction_flow
    - inherit_from（与哪些前驱事件是连续关系）
    ↓
写入 SQLite (core.db)：
    - events 表（结构化字段）
    - FTS5 虚拟表（BM25 全文检索）
    - sqlite-vec vec0（向量索引，需 embedding 模型）
```
2. 关系图（Impression）的生成
关系图不是从原始消息直接提取的，而是批处理周期任务：

```
[Periodic: 每日/每周]
    ↓
Impression Aggregation  — 约 1 次 LLM 调用 / 活跃的 (observer, subject) 对
    输入：evidence_event_ids（相关事件）
    输出：Impression dataclass
    - relation_type, affect [-1,1], intensity [0,1]
    - scope (global / group_id)
    ↓
写入 impressions 表

Persona Synthesis  — 约 1 次 LLM 调用 / 活跃 Persona / 天
    更新 Persona.persona_attrs（人格描述、情感倾向、内容标签）
    ↓
写入 personas 表 + 投影到 personas/<uid>/PROFILE.md
```
关系图是单向的（A→B 的印象 ≠ B→A 的印象），Bot 本身也是 Persona 节点。

3. 召回 → 影响 Prompt 生成
在每次 LLM 调用之前（热路径，零额外 LLM 调用）：

```
[Query Classification]  — 纯规则，无模型
    │
    ├─ is_relation_query?  → 直接查 impressions 表，格式化注入
    ├─ is_profile_query?   → 读 PERSONA.md，注入
    └─ is_event_query / general → 进入 Hybrid RAG

[Hybrid RAG]
    ① BM25 top-20 (FTS5)
    ② Vector top-20 (sqlite-vec)
    ③ RRF 融合 → top-10
    ④ Neighbor expansion：
       每个检索到的事件，可选择性加入其 inherit-parent 和 inherit-child
       （需通过 relevance gate）
    ⑤ Greedy 填充 token budget（默认 800 token，硬上限）
       排序依据：salience × recency_decay × relevance_score
    │
    ▼
以清晰分隔符注入 system prompt
```

### 关键设计决策摘要
|设计点	| 说明 |
|------|------|
|热路径零 LLM	|检索完全本地，不增加延迟|
|三轴分离	|事件（时间轴）、印象（社会轴）、摘要（叙事轴）各自独立，共用 event_id 做交叉引用 |
|事件是唯一索引 | impression 的 evidence_event_ids 指向具体事件，摘要也按事件聚合，三者通过 event_id 互相可跳转 ｜
｜Salience 衰减	｜ 重要性随时间衰减（每日 decay 任务），避免旧事件永远占满 token budget ｜
｜Relation 模块可选	｜ relation_inference.enabled = false 时记忆系统仍完整工作，只是不注入印象信息 ｜
