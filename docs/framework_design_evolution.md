# AstrBot Plugin Enhanced Memory — 演进架构文档

> **项目名称**: astrbot-plugin-enhanced-memory（工作名 TBD）
> **项目定位**: 跨平台聊天机器人三轴记忆系统
> **技术栈**: Python 3.10+, AstrBot 4.0+, SQLite + FTS5 + sqlite-vec, aiosqlite
> **文档版本**: v0.1（初始规划版）
> **生成时间**: 2026-05-02
> **项目状态**: 设计完成，待实现

---

## 📖 目录

### 第一部分：设计哲学与架构综述
1. [设计哲学与核心命题](#1-设计哲学与核心命题)
2. [与现有方案的对比分析](#2-与现有方案的对比分析)
3. [总体架构设计](#3-总体架构设计)

### 第二部分：领域模型与存储
4. [核心领域模型（三轴一体）](#4-核心领域模型三轴一体)
5. [存储层设计](#5-存储层设计)
6. [身份统一与跨平台映射](#6-身份统一与跨平台映射)

### 第三部分：数据处理管线
7. [事件边界检测器](#7-事件边界检测器)
8. [LLM 事件提取器](#8-llm-事件提取器)
9. [检索管线与 Prompt 注入](#9-检索管线与-prompt-注入)

### 第四部分：周期性任务与可视化
10. [周期性后台任务](#10-周期性后台任务)
11. [Markdown 投影系统](#11-markdown-投影系统)
12. [WebUI 三面板设计](#12-webui-三面板设计)

### 第五部分：开发计划与里程碑
13. [10 阶段实现计划](#13-10-阶段实现计划)
14. [项目文件结构规划](#14-项目文件结构规划)
15. [技术亮点总结](#15-技术亮点总结)

---

## 1. 设计哲学与核心命题

### 1.1 三轴正交记忆模型

现有 AstrBot 记忆插件的共同缺陷是**将三种本质不同的记忆需求折叠到单一维度**：

| 插件 | 主轴 | 被牺牲的信息 |
|---|---|---|
| LivingMemory | 叙事轴（摘要/反思） | 精确时序、社交关系 |
| Memorix | 情节轴（事件/时序） | 人际关系、意义积累 |
| Scriptor | 文件轴（Markdown 文档） | 结构化查询能力 |

本项目的核心命题：**三轴同时在场，以 `event_id` 为统一索引**。

```
情节轴 (Episodic)     → Event Flow     → "发生了什么，何时，与谁"
社交轴 (Social)       → Relation Graph  → "谁对谁有什么看法"
叙事轴 (Narrative)    → Summarised Mem  → "长期来看意味着什么"
```

三轴通过 `event_id` 形成可点击的交叉导航：
- 点击关系图的印象边 → 高亮支撑该印象的事件列表
- 点击事件节点 → 跳转到对应时段的摘要报告

### 1.2 工程边界（Non-Goals）

以下功能**刻意不做**，以保持系统聚焦：

- **不是通用 RAG 框架**：优化聊天记忆，不适用于文档 QA
- **不是 GraphRAG**：做异构图混合检索，但不做社区发现和图摘要
- **不替代 AstrBot 内置上下文压缩**：仅负责长期记忆，短期由框架处理
- **不追求 SOTA 分数**：目标是消费者部署（单用户/小群），优先 token 效率和可解释性

---

## 2. 与现有方案的对比分析

### 2.1 参考实现汲取的教训

#### LivingMemory
- **借鉴**：反思阈值模式、时间衰减公式（`salience × e^(-λt)`）、混合检索 RRF 融合
- **问题**：摘要粒度粗，丢失精确时序；无结构化关系存储

#### Memorix
- **借鉴**：Scope 路由（global/group/personal 三级）、生命周期状态机、图可视化思路
- **问题**：缺乏对话延续性（inherit_from 链）；向量化粒度为整条记忆而非事件

#### Scriptor（灵笔司书）
- **借鉴**：跨平台身份统一（`physical_id → logical_uid`）、睡眠巩固机制、文件监听回写
- **问题**：以文件为存储主体导致结构化查询困难；Mixin 膨胀至 40+ 模块，维护成本高
- **我们的取舍**：保留身份统一和文件-人可读投影的思路，但以 SQLite 为权威数据源，Markdown 仅为只读投影

#### MaiBot
- **借鉴**：`chat_stream` 作为一等公民概念、规划式决策框架
- **预留**：`when_to_speak` 逻辑为 v2 扩展点

### 2.2 技术选型对比

| 维度 | Scriptor | Memorix | 本项目 |
|---|---|---|---|
| 向量库 | ChromaDB | 自定义 | SQLite + sqlite-vec（单文件，零服务依赖） |
| 全文检索 | Tantivy | 无 | SQLite FTS5（内置，零依赖） |
| 身份管理 | ✅ 跨平台 UID | ❌ 无 | ✅ 跨平台 UID |
| 关系图谱 | ❌ 无 | 部分 | ✅ Impression 有向图 |
| 事件继承链 | ❌ 无 | ❌ 无 | ✅ inherit_from |
| Markdown 投影 | ✅（文件即存储） | ❌ | ✅（DB 为主，文件为影） |
| WebUI | ✅ Vue3 8 页面 | ❌ | ✅ 三面板（规划中） |

---

## 3. 总体架构设计

### 3.1 数据流概览

```
原始消息（来自 AstrBot 事件流）
       │
       ▼
[平台适配器]    ← (platform, physical_id) → stable uid
       │
       ▼
[事件边界检测器]  ← 纯启发式规则，零 LLM 调用
       │  触发条件（满足任一）：
       │  1. 距上条消息 > 30 分钟
       │  2. 消息数 ≥ 20 且 topic_drift > 0.6
       │  3. 硬上限：消息数 ≥ 50 或窗口时长 ≥ 60 分钟
       │
       ▼（事件关闭时）
[LLM 事件提取器]  ← 每事件一次 LLM 调用，约束 JSON 输出
       │  产出：topic, tags, salience, participants
       │
       ▼
[领域模型层]     ← 纯 Python dataclass，零 I/O
  Persona | Event | Impression
       │
       ▼
[仓储层]         ← 抽象接口，生产用 SQLite 实现（单文件）
  ├─► SQLite + FTS5       （结构化 + BM25 关键词搜索）
  ├─► SQLite + sqlite-vec （向量语义搜索，vec0 虚表，Phase 5 启用）
  └─► Markdown 投影器     （只读，用户可见）

周期性任务（非热路径，cron 触发）：
  • 印象聚合    — 每周
  • 人格画像合成 — 每周
  • 摘要记忆渲染 — 每日/每周
  • 显著度衰减  — 每日
```

### 3.2 热路径 LLM 调用预算

| 阶段 | LLM 调用 | 说明 |
|---|---|---|
| 每条用户消息 | **0 次** | 检索完全本地化 |
| 事件关闭 | **1 次** | 结构化提取，约束 JSON |
| 每日周期（每活跃人格） | ~1 次 | 人格画像合成 |
| 每日周期（每活跃关系对） | ~1 次 | 印象聚合 |
| 每日周期（每活跃群组） | ~1 次 | 摘要生成 |

**目标**：比 LivingMemory 基线多消耗 20-50% token，换取更丰富的本体表达。

---

## 4. 核心领域模型（三轴一体）

### 4.1 Persona（人格节点）

```python
@dataclass(slots=True)
class Persona:
    uid: str                               # 内部稳定 ID（UUID4）
    bound_identities: list[tuple[str, str]] # [(platform, physical_id), ...]
    primary_name: str
    persona_attrs: dict                    # 描述、情感倾向类型、内容标签
    confidence: float                      # LLM 提取置信度 [0, 1]
    created_at: float                      # Unix 时间戳
    last_active_at: float
```

**设计要点**：
- Bot 本身也是一个 Persona 节点（特殊标记）
- `persona_attrs` 包含：人格描述、`affect_type`（情感倾向）、`content_tags`（话题偏好）
- 跨平台合并通过 admin 命令操作 `bound_identities`

### 4.2 Event（事件节点）

```python
@dataclass(slots=True)
class Event:
    event_id: str                 # UUID4
    group_id: str | None          # None = 私聊
    start_time: float
    end_time: float
    participants: list[str]       # uid 列表
    interaction_flow: list[MessageRef]  # 原始消息引用
    topic: str                    # LLM 提取的主题
    chat_content_tags: list[str]  # 话题标签
    salience: float               # 显著度 [0,1]，随时间衰减
    confidence: float
    inherit_from: list[str]       # 父事件 ID（对话续接链）
    last_accessed_at: float
    # group_mood 在查询时从参与者 affect 派生，不持久化存储
```

**设计要点**：
- `inherit_from` 构成事件继承链，用于追踪跨时间的同一话题演化
- `salience` 衰减公式：`s_t = s_0 × e^(-λ × Δt)`，λ 可配置
- `group_mood` 是派生属性，不存储，避免状态不一致

### 4.3 Impression（印象边，有向）

```python
@dataclass(slots=True)
class Impression:
    observer_uid: str       # 印象持有者
    subject_uid: str        # 被观察者
    relation_type: str      # 枚举：friend/colleague/stranger/family/rival/...
    affect: float           # 情感值 [-1, 1]
    intensity: float        # 强度 [0, 1]
    confidence: float
    scope: str              # 'global' 或具体 group_id
    evidence_event_ids: list[str]  # 支撑该印象的事件 ID
    last_reinforced_at: float
```

**设计要点**：
- **有向性**：`Impression(A→B) ≠ Impression(B→A)`
- `evidence_event_ids` 实现可溯源性（用户可追问"为什么这么认为"）
- `scope` 支持全局印象和群内局部印象并存

### 4.4 MessageRef（消息引用，值对象）

```python
@dataclass(slots=True, frozen=True)
class MessageRef:
    sender_uid: str
    timestamp: float
    content_hash: str   # 原始消息内容的 SHA256，用于去重
    content_preview: str  # 前 200 字符，减少存储
```

---

## 5. 存储层设计

### 5.1 文件目录结构

```
data/plugins/<plugin_name>/data/
├── db/
│   └── core.db          # SQLite WAL：events, personas, impressions, fts5, vec0 (512维，sqlite-vec)
├── personas/
│   └── <uid>/
│       ├── PROFILE.md      # 客观信息（只读投影，定期从 DB 生成）
│       └── IMPRESSIONS.md  # Bot 对此人的印象（用户可编辑，触发回写）
├── groups/
│   └── <gid>/
│       ├── CHARTER.md      # 群组特征描述
│       └── summaries/
│           └── <YYYY-MM-DD>.md  # 每日/每周摘要报告
└── global/
    ├── SOP.md           # 跨群全局规则
    └── BOT_PERSONA.md   # Bot 自身人格定义
```

### 5.2 SQLite Schema（核心表）

```sql
-- 人格表
CREATE TABLE personas (
    uid TEXT PRIMARY KEY,
    primary_name TEXT NOT NULL,
    persona_attrs TEXT,          -- JSON
    confidence REAL DEFAULT 0.5,
    created_at REAL NOT NULL,
    last_active_at REAL NOT NULL
);

-- 身份绑定表（多对一）
CREATE TABLE identity_bindings (
    platform TEXT NOT NULL,
    physical_id TEXT NOT NULL,
    uid TEXT NOT NULL REFERENCES personas(uid),
    PRIMARY KEY (platform, physical_id)
);

-- 事件表
CREATE TABLE events (
    event_id TEXT PRIMARY KEY,
    group_id TEXT,               -- NULL = 私聊
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    participants TEXT NOT NULL,  -- JSON array of uids
    interaction_flow TEXT,       -- JSON array of MessageRef
    topic TEXT NOT NULL,
    chat_content_tags TEXT,      -- JSON array
    salience REAL DEFAULT 0.5,
    confidence REAL DEFAULT 0.5,
    inherit_from TEXT,           -- JSON array of event_ids
    last_accessed_at REAL NOT NULL
);

-- 事件全文检索虚表
CREATE VIRTUAL TABLE events_fts USING fts5(
    topic, chat_content_tags, content='events', content_rowid='rowid'
);

-- 印象表（有向关系）
CREATE TABLE impressions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observer_uid TEXT NOT NULL REFERENCES personas(uid),
    subject_uid TEXT NOT NULL REFERENCES personas(uid),
    relation_type TEXT NOT NULL,
    affect REAL NOT NULL,          -- [-1, 1]
    intensity REAL NOT NULL,       -- [0, 1]
    confidence REAL DEFAULT 0.5,
    scope TEXT NOT NULL DEFAULT 'global',
    evidence_event_ids TEXT,       -- JSON array
    last_reinforced_at REAL NOT NULL,
    UNIQUE(observer_uid, subject_uid, scope)
);
```

### 5.3 仓储抽象接口

```python
# repository/base.py
from abc import ABC, abstractmethod
from ..domain.models import Persona, Event, Impression

class PersonaRepository(ABC):
    @abstractmethod
    async def get(self, uid: str) -> Persona | None: ...
    @abstractmethod
    async def get_by_identity(self, platform: str, physical_id: str) -> Persona | None: ...
    @abstractmethod
    async def upsert(self, persona: Persona) -> None: ...

class EventRepository(ABC):
    @abstractmethod
    async def get(self, event_id: str) -> Event | None: ...
    @abstractmethod
    async def search_fts(self, query: str, limit: int) -> list[Event]: ...
    @abstractmethod
    async def search_vector(self, embedding: list[float], limit: int) -> list[Event]: ...
    @abstractmethod
    async def upsert(self, event: Event) -> None: ...
    @abstractmethod
    async def decay_salience(self, lambda_: float) -> int: ...  # 返回更新行数

class ImpressionRepository(ABC):
    @abstractmethod
    async def get(self, observer_uid: str, subject_uid: str, scope: str) -> Impression | None: ...
    @abstractmethod
    async def list_by_observer(self, observer_uid: str) -> list[Impression]: ...
    @abstractmethod
    async def upsert(self, impression: Impression) -> None: ...
```

---

## 6. 身份统一与跨平台映射

### 6.1 身份解析流程

```python
# adapters/identity.py
async def get_or_create_uid(
    physical_id: str,
    platform: str,
    sender_name: str,
    repo: PersonaRepository
) -> str:
    """
    (platform, physical_id) → stable internal uid
    
    流程：
    1. 查 identity_bindings 表，找到已存在的 uid → 直接返回
    2. 未找到 → 创建新 Persona，生成 UUID4 作为 uid
    3. 写入 identity_bindings 绑定关系
    """
```

**管理员命令**（跨平台合并）：
```
/memory merge <uid_a> <uid_b>
# 将 uid_b 的所有绑定身份、事件参与记录、印象转移到 uid_a
```

### 6.2 平台适配器边界原则

- **适配器边界**：唯一发生 `(platform, physical_id) → uid` 转换的地方
- **领域内部**：只看 `uid`，从不看平台原始 ID
- **测试友好**：测试可直接构造 `uid`，无需模拟平台事件

---

## 7. 事件边界检测器

### 7.1 三信号规则（v1）

```python
# boundary/detector.py
class EventBoundaryDetector:
    """
    纯启发式，零 LLM 调用。
    topic_drift = cosine_distance(embed(first_msg), embed(latest_msg))
    embedding 结果在 detector 内部 LRU 缓存。
    """
    
    def should_close(self, window: MessageWindow) -> bool:
        # 信号 1：时间间隔
        if window.gap_since_last > 1800:  # 30 分钟
            return True
        # 信号 2：消息密度 + 话题漂移
        if window.message_count >= 20 and window.topic_drift() > 0.6:
            return True
        # 信号 3：硬上限
        if window.message_count >= 50 or window.duration >= 3600:  # 60 分钟
            return True
        return False
```

### 7.2 v1 显式不处理的场景（v2 扩展点）

| 场景 | 原因 | v2 方案预留 |
|---|---|---|
| 同群并行对话 | 分离复杂，实现代价高 | 回复链解纠缠 |
| 嵌套事件（父子） | 本体复杂性不值得 | 可选层次结构 |
| 回复链解纠缠 | 需要线程感知 | 消息 `reply_to` 字段 |
| 迟滞/防抖 | v1 已够用 | 滑动窗口熵检测 |

---

## 8. LLM 事件提取器

### 8.1 约束输出 Schema

```python
# extractor/schema.py
EVENT_EXTRACTION_SCHEMA = {
    "topic": "str",             # 15 字以内的话题摘要
    "chat_content_tags": ["str"],  # 最多 5 个标签
    "salience": "float_0_1",    # 显著度
    "participants_confirmed": ["uid"],  # 验证参与者列表
    "mood_hint": "enum[positive,neutral,negative,mixed]",
    "inherit_probability": "float_0_1"  # 是否应继承前一事件
}
```

### 8.2 提取 Prompt 设计原则

- **约束枚举**：所有枚举类型字段给出合法值列表，减少幻觉
- **最小输出**：只要求 schema 内的字段，不要叙述
- **一次调用**：完整 schema 一次性提取，不分轮
- **降级策略**：LLM 失败时，用规则填充默认值，不阻塞写入

---

## 9. 检索管线与 Prompt 注入

### 9.1 查询分类（零模型）

```python
# retrieval/classifier.py
def classify_query(text: str) -> QueryType:
    """
    纯规则分类，不调用任何模型。
    
    关系查询：包含"关系"、"认识"、"觉得XX怎么样"等关键词
        → 直接查 impressions 表，格式化注入
    
    画像查询：包含"你知道我"、"关于我"等关键词  
        → 读 PROFILE.md，注入
    
    事件/通用查询：其他
        → 进入 Hybrid RAG 流程
    """
```

### 9.2 混合 RAG 流程

```
输入 query
    │
    ├──► BM25（FTS5）top-20
    │       ↓
    ├──► Vector（sqlite-vec vec0）top-20
    │       ↓
    └──► RRF 融合（k=60）→ top-10
             ↓
         邻居扩展：
           每个结果可选包含 1 个父事件 + 1 个子事件
           （通过 inherit_from 链）
           需通过相关性门槛（relevance > 0.3）
             ↓
         贪婪 Token 填充（默认 800 token 上限）
           排序权重 = salience × recency_decay × relevance_score
             ↓
         System Prompt 注入（明确分隔符）
```

### 9.3 Prompt 注入格式

```
--- [MEMORY CONTEXT START] ---
[RELATION: user_A → bot] affect=0.8, type=friend, scope=global
  evidence: event_abc, event_def

[EVENT: 2026-03-15T14:30 — 工作项目讨论]
  participants: user_A, user_B
  topic: Q2 产品路线图评审
  tags: [工作, 产品, 规划]

[EVENT: 2026-03-10T20:00 — 周末闲聊]  
  participants: user_A
  topic: 孩子学钢琴进展
  tags: [家庭, 教育]
--- [MEMORY CONTEXT END] ---
```

---

## 10. 周期性后台任务

### 10.1 任务调度表

| 任务 | 频率 | 输入 | 输出 | LLM 调用 |
|---|---|---|---|---|
| `decay_salience` | 每日 | events 表 | 更新 salience 字段 | 0 |
| `synthesize_persona` | 每周 | 近期事件 + 现有画像 | 更新 persona_attrs | ~1/活跃人格 |
| `aggregate_impressions` | 每周 | 近期事件的参与者情绪 | 更新 impressions 表 | ~1/活跃关系对 |
| `render_summary` | 每日/每周 | 事件列表 | 写 `summaries/<date>.md` | ~1/活跃群组 |
| `project_markdown` | 触发式（事件提取后） | personas/impressions | 写 PROFILE.md | 0 |
| `file_watch_sync` | 实时监听 | 用户编辑的 .md 文件 | 高权重回写 DB | 0~1 |

### 10.2 显著度衰减公式

```python
# tasks/decay.py
import math

def compute_new_salience(
    original: float,
    days_elapsed: float,
    lambda_: float = 0.01,  # 可配置，默认半衰期约 69 天
    access_boost: float = 0.1  # 每次访问提升量
) -> float:
    decayed = original * math.exp(-lambda_ * days_elapsed)
    return min(1.0, decayed + access_boost if was_accessed_recently else decayed)
```

---

## 11. Markdown 投影系统

### 11.1 投影规则（DB → 文件）

- **单向默认**：DB 是权威数据源，文件是派生输出
- **触发时机**：事件提取完成后异步触发，非热路径
- **幂等生成**：相同 DB 状态始终生成相同文件内容

### 11.2 反向同步（文件 → DB）

仅对 `IMPRESSIONS.md` 和 `BOT_PERSONA.md` 开放：

```python
# projector/file_watcher.py
class MarkdownFileWatcher:
    """
    监听用户可编辑的 .md 文件变更。
    文件变更 → 解析差异 → 以高先验权重写回 DB
    （用户编辑优先级 > LLM 推断）
    
    合并策略：
    - 字段级覆盖（用户设置的字段替换 LLM 推断值）
    - 用户未修改的字段保留 DB 最新值
    - 冲突记录到日志，不自动解决
    """
```

---

## 12. WebUI 三面板设计

### 12.1 模块定位（核心解耦）

WebUI 不在 `core/` 而是独立的根级 `web/` 模块。语义边界：

- `core/` 是数据引擎，可以离开 WebUI 单独运行（关闭 `webui_enabled` 即可）
- `web/` 仅持有指向 `core/` 的依赖，反向依赖被禁止
- 这一边界使 WebUI 可被关闭、替换，或在未来被独立的 `astrbot_plugin_unified_webui` 基座插件替代

### 12.2 模块结构

```
web/
├── server.py        # WebuiServer：aiohttp app + auth 中间件 + 路由注册
├── auth.py          # AuthManager：bcrypt 密码 + session/sudo 状态
├── registry.py      # PanelRegistry：面板/路由注册中心，支持其他插件挂载
├── static/index.html # 前端单页（vis-timeline + Cytoscape + marked，玻璃拟态）
└── README.md
```

### 12.3 三面板架构

```
WebUI（aiohttp 后端 + 单页前端）
├── Panel 1: Event Flow Diagram
│   ├── 渲染库：vis-timeline 7.7
│   ├── 节点：Event，颜色编码 salience，密度滑块控制 top-N
│   ├── 边：inherit_from 继承关系
│   └── 交互：点击事件 → 玻璃拟态侧栏显示详情；外部高亮触发 focus
│
├── Panel 2: Relation Graph
│   ├── 渲染库：Cytoscape.js 3.29，cose 力导向
│   ├── 节点：Persona，Bot 节点视觉区分（粉色边框）
│   ├── 边：Impression（有向），width 编码 intensity，line-color 编码 affect
│   └── 交互：
│       - 点击节点 → 邻域高亮（一跳邻居保持，其他变暗 0.15 opacity）
│       - 点击边 → 高亮该印象 + 在 Event Flow 高亮其 evidence_event_ids
│       - LOD：zoom < 0.6 时隐藏所有节点标签
│
└── Panel 3: Summarised Memory
    ├── 渲染：marked.js 解析 Markdown
    ├── 内容：按 (group_id, YYYY-MM-DD) 组织的摘要报告
    └── 数据源：扫描 data_dir/groups/*/summaries/ 和 data_dir/global/summaries/
```

### 12.4 二级认证（Login + Sudo）

参考 Scriptor 设计的两层权限模型：

| 层级 | 触发 | 默认 TTL | 用途 |
|------|------|----------|------|
| Login | 输入密码 → 颁发 cookie | 24 h | 读取所有数据、查看面板 |
| Sudo  | 同密码再次确认 | 30 min | 写操作：改密码、触发任务、未来的配置编辑 |
| 关闭  | `webui_auth_enabled=false` | — | 仅本机部署、无外网映射时可用 |

**密码存储**：`bcrypt` 哈希写入 `data_dir/.webui_password`，权限 0600。`bcrypt` 软导入：未安装时降级为 sha256 + warning（仅开发期可接受，生产需 `pip install bcrypt`）。

**首次访问**：`/api/auth/status` 返回 `password_set=false` → 前端进入 setup 模式，要求确认两次新密码 → POST `/api/auth/setup` 设置并自动登录。

**会话存储**：进程内 dict（`AuthManager._sessions`），重启失效。单用户场景无需持久化。

### 12.5 第三方面板挂载机制（PanelRegistry）

**问题**：用户可能开发多个互相依赖的 AstrBot 插件（关系图增强、知识图谱、长期记忆等），需要统一 WebUI 而非各自启动 HTTP 服务。

**方案**：本插件持有单例 `PanelRegistry`，通过 `EnhancedMemoryPlugin.webui_registry` 属性对外暴露。其他插件用 `context.get_registered_star("astrbot_plugin_moirai")` 获取本插件实例后注册：

```python
em = self.context.get_registered_star("astrbot_plugin_moirai")
em.webui_registry.register(
    PanelManifest(
        plugin_id="astrbot_plugin_xxx",
        panel_id="my_panel",
        title="我的面板",
        icon="🔮",
        permission="auth",       # public | auth | sudo
    ),
    routes=[
        PanelRoute("GET", "/api/ext/xxx/data", handler, permission="auth"),
    ],
)
```

注册的路由会被 `WebuiServer._build_app()` 在初始化时注入到 aiohttp router，并自动套上同样的 auth 中间件（`_wrap(permission, handler)`）。前端通过 `GET /api/panels` 拉取所有已注册面板，在设置面板中列出（动态 lazy-load 前端 bundle 是 v2 工作）。

**演进路径**：
- v1：本插件作为基座，`PanelRegistry` 为内部组件
- v2（如生态扩大）：`PanelRegistry` + auth 抽出为独立的 `astrbot_plugin_unified_webui` 插件，本插件改为消费者

### 12.6 视觉设计（Memorix 借鉴）

| 模式 | 实现 | 价值 |
|------|------|------|
| 玻璃拟态侧栏 | `backdrop-filter: blur(20px)` + 半透明背景 | 不遮挡数据可视化主区 |
| 邻域高亮 | Cytoscape `closedNeighborhood()` + `.dim` class | 在密集图中聚焦局部结构 |
| 密度滑块 | 客户端按 salience 排序后取 top-N | 大数据集下保持前端流畅 |
| LOD 缩放 | `cy.on('zoom')` 切换 `font-size` | 缩小时减少标签视觉噪音 |
| 暗/亮主题 | CSS 变量 + localStorage 持久化 | 适配不同环境 |
| 底部 dock | `position: fixed; bottom; flex` | 触屏友好、不挡内容 |
| 中底 Toast | 自动消失的非阻塞反馈 | 替代 alert/confirm 模态 |

### 12.7 后端路由清单

| 路由 | 权限 | 说明 |
|------|------|------|
| `GET /` | public | HTML 单页 |
| `GET /static/*` | public | 静态资源（已注入 `add_static`）|
| `GET /api/auth/status` | public | 是否已设置密码 / 已登录 / sudo 状态 |
| `POST /api/auth/setup` | public | 首次设置密码（含已设置时返回 409）|
| `POST /api/auth/login` | public | 密码登录，下发 session cookie |
| `POST /api/auth/logout` | auth | 销毁会话 |
| `POST /api/auth/sudo` | auth | 同密码进入 sudo |
| `POST /api/auth/sudo/exit` | auth | 退出 sudo |
| `POST /api/auth/password` | sudo | 改密码（旧密码 + 新密码）|
| `GET /api/events` | auth | 事件列表，可按 group_id 过滤 |
| `GET /api/graph` | auth | 关系图节点 + 边 |
| `GET /api/summaries` | auth | 摘要文件清单 |
| `GET /api/summary` | auth | 单个摘要内容 |
| `GET /api/stats` | auth | 顶部状态条统计 |
| `POST /api/admin/run_task` | sudo | 立刻触发指定后台任务 |
| `GET /api/panels` | auth | 列出所有已注册第三方面板 |

### 12.8 配置项（`_conf_schema.json`）

```json
{
  "webui_enabled": { "type": "bool", "default": true },
  "webui_port": { "type": "int", "default": 2653 },
  "webui_auth_enabled": { "type": "bool", "default": true },
  "webui_session_hours": { "type": "int", "default": 24 },
  "webui_sudo_minutes": { "type": "int", "default": 30 }
}
```

密码本身不在配置 schema 中（敏感信息），由前端首次访问流程写入 `data_dir/.webui_password`。

---

## 13. 10 阶段实现计划

### Phase 1 — 领域模型 + 仓储抽象 + 内存实现 + 测试
**目标**：纯 Python，零外部依赖，可单独单元测试

**交付文件**：
```
core/domain/
├── models.py        # Persona, Event, Impression, MessageRef dataclasses
└── __init__.py
core/repository/
├── base.py          # ABC 接口：PersonaRepo, EventRepo, ImpressionRepo
├── memory.py        # 内存实现（dict + list，测试用）
└── __init__.py
tests/
├── test_domain.py   # 领域模型单元测试
└── test_memory_repo.py
```

**验收标准**：`pytest tests/` 全绿，无任何 Chroma/文件/网络 I/O

---

### Phase 2 — Chroma 仓储实现 + Schema 迁移
**目标**：生产级持久化，aioChroma，WAL 模式

**交付文件**：
```
core/repository/
└── Chroma.py        # ChromaPersonaRepo, ChromaEventRepo, ChromaImpressionRepo
core/migrations/
├── 001_initial_schema.sql
└── runner.py        # 迁移运行器（无第三方依赖）
tests/
└── test_Chroma_repo.py  # 集成测试（tmpdir DB）
```

**验收标准**：内存实现的测试用例可在 Chroma 实现上全部通过（接口置换测试）

---

### Phase 3 — 事件边界检测 + AstrBot 事件流集成
**目标**：接入 AstrBot 消息流，检测事件边界，维护滑动窗口

**交付文件**：
```
core/boundary/
├── detector.py      # EventBoundaryDetector
└── window.py        # MessageWindow 数据结构
core/adapters/
├── astrbot.py       # AstrBot 事件适配器（平台 ID → uid）
└── identity.py      # get_or_create_uid
main.py              # AstrBot 插件入口，注册事件监听
metadata.yaml        # 插件元数据
```

**验收标准**：在 AstrBot 测试环境中，消息序列能正确触发事件边界

---

### Phase 4 — LLM 事件提取器
**目标**：事件关闭时异步触发一次 LLM 调用，产出结构化 JSON

**交付文件**：
```
core/extractor/
├── schema.py        # 约束输出 schema 定义
├── prompts.py       # 提取 prompt 模板
├── extractor.py     # EventExtractor（调用 AstrBot 配置的 LLM 提供商）
└── fallback.py      # LLM 失败时的规则降级
tests/
└── test_extractor.py  # Mock LLM 的单元测试
```

**验收标准**：给定消息序列，能生成合法 Event dataclass（含降级场景）

---

### Phase 5 — 向量嵌入 + FAISS 索引 + 混合检索
**目标**：向量化事件，实现 BM25 + 向量 RRF 混合检索

**交付文件**：
```
core/embeddings/
├── encoder.py       # 嵌入模型封装（bge-small-zh-v1.5，支持降级到 keyword-only）
└── faiss_store.py   # FAISS 索引的持久化包装
core/retrieval/
├── classifier.py    # 规则查询分类器
├── hybrid.py        # RRF 融合检索
└── expander.py      # inherit_from 邻居扩展
```

**验收标准**：检索结果相关性测试（手工标注 10 个查询-文档对），P@5 > 0.6

---

### Phase 6 — Prompt 注入（插件可用里程碑）
**目标**：在 AstrBot LLM 调用前注入格式化记忆上下文

**交付文件**：
```
core/injection/
├── formatter.py     # 记忆上下文格式化
└── injector.py      # AstrBot pipeline 钩子
```

**验收标准**：端到端测试，机器人能在回复中体现检索到的历史记忆（人工评估 5 组对话）

> **⭐ Phase 1-6 完成后，插件具备完整核心功能，可以部署使用**

---

### Phase 7 — Markdown 投影器（只读方向）
**目标**：DB 状态异步投影为可读 Markdown 文件

**交付文件**：
```
core/rojector/
├── persona_projector.py   # 生成 PROFILE.md
├── summary_projector.py   # 生成 summaries/<date>.md
└── renderer.py            # Jinja2 模板渲染
templates/
├── profile.md.j2
└── summary.md.j2
```

---

### Phase 8 — 周期性任务
**目标**：salience 衰减、画像合成、印象聚合、摘要生成

**交付文件**：
```
core/tasks/
├── scheduler.py      # 轻量 cron（APScheduler 或自实现）
├── decay.py          # salience 衰减
├── synthesize.py     # 人格画像合成
├── aggregate.py      # 印象聚合
└── summarize.py      # 摘要生成
```

---

### Phase 9 — WebUI 三面板
**目标**：Event Flow + Relation Graph + Summarised Memory 可视化

**交付文件**：
```
web/
├── backend/
│   ├── app.py         # FastAPI 应用
│   └── routes/        # API 路由
└── frontend/
    ├── src/
    │   ├── panels/    # 三个面板组件
    │   └── stores/    # Pinia 状态
    └── package.json
```

---

### Phase 10 — Markdown 反向同步（文件 → DB）
**目标**：监听用户编辑，高权重回写 DB

**交付文件**：
```
core/projector/
└── file_watcher.py   # 文件监听 + 差异解析 + 回写
```

---

## 14. 项目文件结构规划

```
astrbot-plugin-enhanced-memory/
├── main.py                  # AstrBot 插件入口
├── metadata.yaml            # 插件元数据
├── requirements.txt         # 依赖声明
├── _conf_schema.json        # 配置 schema
├── CLAUDE.md                # 架构设计规范（开发者参考）
├── 演进架构文档.md            # 本文档
│
├── domain/                  # ★ Phase 1：纯 Python 领域模型
│   ├── __init__.py
│   └── models.py
│
├── repository/              # ★ Phase 1-2：仓储层
│   ├── __init__.py
│   ├── base.py              # ABC 接口
│   ├── memory.py            # 内存实现（测试用）
│   └── Chroma.py            # Chroma 生产实现
│
├── migrations/              # ★ Phase 2：SQL 迁移脚本
│   ├── 001_initial_schema.sql
│   └── runner.py
│
├── boundary/                # ★ Phase 3：事件边界检测
│   ├── detector.py
│   └── window.py
│
├── adapters/                # ★ Phase 3：平台适配
│   ├── astrbot.py
│   └── identity.py
│
├── extractor/               # ★ Phase 4：LLM 事件提取
│   ├── schema.py
│   ├── prompts.py
│   ├── extractor.py
│   └── fallback.py
│
├── embeddings/              # ★ Phase 5：向量化
│   ├── encoder.py
│   └── faiss_store.py
│
├── retrieval/               # ★ Phase 5：混合检索
│   ├── classifier.py
│   ├── hybrid.py
│   └── expander.py
│
├── injection/               # ★ Phase 6：Prompt 注入
│   ├── formatter.py
│   └── injector.py
│
├── projector/               # ★ Phase 7+10：Markdown 投影
│   ├── persona_projector.py
│   ├── summary_projector.py
│   ├── renderer.py
│   └── file_watcher.py      # Phase 10
│
├── templates/               # ★ Phase 7：Jinja2 模板
│   ├── profile.md.j2
│   └── summary.md.j2
│
├── tasks/                   # ★ Phase 8：周期性任务
│   ├── scheduler.py
│   ├── decay.py
│   ├── synthesize.py
│   ├── aggregate.py
│   └── summarize.py
│
├── webui/                   # ★ Phase 9：可视化面板
│   ├── backend/
│   │   ├── app.py
│   │   └── routes/
│   └── frontend/
│       └── src/
│
└── tests/                   # 贯穿全程
    ├── test_domain.py
    ├── test_memory_repo.py
    ├── test_Chroma_repo.py
    ├── test_boundary.py
    ├── test_extractor.py
    └── test_retrieval.py
```

---

## 15. 技术亮点总结

### 15.1 架构层面

| 亮点 | 实现方式 | 价值 |
|---|---|---|
| **三轴正交记忆** | Persona + Event + Impression 三独立实体 | 任意维度独立查询，不降维 |
| **热路径零 LLM** | 检索全部本地化（FTS5 + FAISS） | 响应延迟不受 LLM 速率影响 |
| **印象可溯源** | `evidence_event_ids` 字段 | 用户可追问"为什么这么认为" |
| **事件继承链** | `inherit_from` 字段 | 跨时间追踪同一话题演化 |
| **DB 为权威** | Markdown 仅为只读投影 | 避免 Scriptor 式文件-DB 双主状态 |

### 15.2 工程层面

| 亮点 | 实现方式 | 价值 |
|---|---|---|
| **接口置换测试** | 内存实现 + Chroma 实现共用一套测试 | 早期发现接口语义不一致 |
| **零依赖迁移** | 自实现 SQL 迁移运行器 | 不引入 Alembic 等重型框架 |
| **嵌入模型降级** | keyword-only 模式作为降级路径 | 无 GPU 环境也能正常运行 |
| **模块解耦** | 关系推断模块可独立禁用 | 禁用不影响记忆功能 |
| **slots=True** | 热路径 dataclass 用 slots | 减少内存占用，加快属性访问 |

### 15.3 用户体验层面

| 亮点 | 实现方式 | 价值 |
|---|---|---|
| **三面板交叉导航** | `event_id` 作为跨面板统一索引 | 可视化与数据一致 |
| **用户可编辑印象** | `IMPRESSIONS.md` 触发回写 | 用户对 AI 认知有主动控制权 |
| **跨平台身份合并** | admin 命令 + `bound_identities` | 同一人在不同平台的记忆统一 |

---

## 附录：关键配置项清单

```yaml
# 事件边界检测
boundary:
  time_gap_minutes: 30        # 时间间隔触发阈值
  message_count_threshold: 20 # 消息数触发阈值
  topic_drift_threshold: 0.6  # 话题漂移触发阈值
  hard_cap_messages: 50       # 硬上限消息数
  hard_cap_minutes: 60        # 硬上限时长

# 检索
retrieval:
  fts_top_k: 20
  vector_top_k: 20
  rrf_k: 60
  final_top_k: 10
  token_budget: 800
  neighbor_expansion: true
  neighbor_relevance_gate: 0.3

# 显著度衰减
decay:
  lambda: 0.01                # 衰减速率（半衰期约 69 天）
  access_boost: 0.1           # 访问提升量
  run_interval_hours: 24

# 嵌入模型
embedding:
  model: "bge-small-zh-v1.5"
  fallback_to_keyword: true   # 模型不可用时降级

# 关系推断（可独立禁用）
relation_inference:
  enabled: true
  aggregation_interval_days: 7

# Markdown 投影
markdown:
  projection_enabled: true
  file_watch_enabled: true    # 反向同步（Phase 10）
```

---

*文档将随实现进度持续更新。每完成一个 Phase，对应章节补充实际实现与设计决策记录。*
