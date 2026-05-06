# Astrbot Plugin - Enhanced Memory

Version: `0.0.1`

Author: `MKiyoaki`, `Gariton`

**Description**: 一个基于“虚拟上下文管理 (VCM)”与“人际环 (Interpersonal Circle)”理论的 AI Agent 长短期记忆系统。通过事件化存储、社会关系建模与实时情感门控，赋予 Bot 跨会话的社交一致性与动态性格。

## Installation

## Getting Start

## Implementation Details

### 数据流全景

#### 1. 消息入库与事件代谢 (Event Lifecycle)
```
AstrBot 原始消息流
    │
    ▼
[Identity Unification] — (platform, physical_id) → 内部稳定 uid
    │
    ▼
[Event Boundary & Merge Detector] — 启发式 + Embedding 相似度
    ├─ 触发新建：距上条 > 30min 或 topic_drift > 0.6
    └─ 触发合并：若新消息与末尾 Event 语义高度重合 (cos_sim > 0.85)，则追加并标记摘要更新
    │
    ▼
[LLM Event Extractor] — 异步处理，生成结构化 Event
    - 字段：topic, salience, participants, interaction_flow
    - 写入 SQLite (FTS5 + sqlite-vec)
```

#### 2. 社交认知快回路 (Social Cognitive Circuit)
此回路为“热路径”，每轮对话触发，不调用 LLM。
```
当前消息 (Query)
    │
    ▼
[Encoder-based Perception] — 小型 Encoder (如 BERT/Qwen-0.5B)
    ├─ Sentiment: 提取情感极性 (S)，负面权重 > 正面权重
    ├─ Interpersonal: 提取 Dominance (D) 与 Affiliation (A) 维度的 Logits
    └─ Calculation: 
       - Mood = f(D, A) 决定当前情绪基调
       - ΔAffinity = S × Salience × Decay 累加至 User-Bot 好感度
    │
    ▼
[Memory Gating] — 借鉴 LSTM 逻辑
    - Input Gate: 过滤噪音（如“哈哈”），决定是否写入长期记忆
    - Forget Gate: 根据 Token 负载，决定踢出哪些陈旧的 Active Context Slot
```

#### 3. 关系图（Impression）与人格合成
```
[Periodic Task] — 每日/每周
    │
    ▼
Impression Aggregation — 利用多分类 Logits 强度更新关系标签
    - Relation Labels: [Stranger, Friend, Rival, Mentor, etc.]
    - Affect & Intensity: 基于历史 ΔAffinity 的 IIR 滤波更新
    ↓
Persona Synthesis — 合成 User Profile 与 Bot 的自我意识镜像
```

#### 4. VCM 状态机 → 影响 Prompt 生成
在每次生成前，由状态机决定“意识桌面”的布局：

```
[VCM Session State Machine]
    │
    ├─ [Focused Mode]: 话题连续且 Token 低 -> 仅保留 Core Profile + 最近对话
    ├─ [Recall Mode]: 意图不明确/触发主动回想 -> 启动 Dual-Route Hybrid RAG
    ├─ [Eviction Mode]: Token 溢出 -> 执行“换页”，将长文本 Event 压缩为 Summary
    └─ [Drift Mode]: 话题突变 -> 清空 Active Slots，快照保存当前上下文
    │
    ▼
[Context Injection]
    - System Prompt: 注入 [Mood, Affinity_Level, Relation_Tag]
    - Memory Slot: 注入 [Active_Events, Summaries]
    - Dynamic Weighting: 抑制近期高频话题，引入 RRF 排序后的多样化记忆
```

### 关键设计决策摘要

| 设计点 | 说明 | 本质逻辑 |
| :--- | :--- | :--- |
| **热路径零 LLM** | 检索与情感计算完全本地化，由小模型和数学公式驱动 | **快思考 (Intuition)**：实时反馈，低延迟 |
| **VCM 状态管理** | 将 Context Window 视为内存，数据库为磁盘，自动进行“换页”与“剔除” | **意识流控制**：防止语义空转与话题拟合 |
| **三轴分离架构** | 事件 (时间)、印象 (社会)、摘要 (叙事) 独立索引 | **多维时空建模**：解决长程逻辑关联问题 |
| **Gating 门控** | 模拟 LSTM 的遗忘与输入逻辑，动态调节信息流 | **代谢机制**：让 Bot 拥有“选择性记忆”能力 |
| **社会认知坐标** | 利用 Dominance 与 Affiliation 向量化定义社交地位与亲和力 | **人格一致性**：基于心理学模型而非随机语气 |
| **Session 隔离** | 状态机基于 Session ID 独立运行，支持跨群全局信息透传 | **隐私与环境适配**：认识人，但分得清场子 |
