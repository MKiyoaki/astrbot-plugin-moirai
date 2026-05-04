# Implementation TODO

记录当前开发分支剩余的实现任务。每个任务包含：要改哪些文件、关键接口/数据结构、实现思路。

---

## 已完成

- [x] `core/config.py` — 新增 `RetrievalConfig`、`InjectionConfig`、`DecayConfig`、`SynthesisConfig`、`SummaryConfig`、`ExtractorConfig`；`PluginConfig` 统一透传
- [x] `_conf_schema.json` — 所有新配置项（retrieval_*、injection_*、boundary_*、extractor_*、decay_*、synthesis_*、summary_*）
- [x] `core/domain/models.py` — `EventStatus` 常量 + `Event.status` 字段（默认 `"active"`）
- [x] `core/repository/base.py` — `list_by_status`、`set_status`、`get_rowid`、`get_by_rowid`、`delete_vector`
- [x] `core/repository/sqlite.py` — 实现上述方法；`upsert`/`_row_to_event` 支持 `status`
- [x] `migrations/002_event_status.sql` — `ALTER TABLE events ADD COLUMN status TEXT NOT NULL DEFAULT 'active'`
- [x] `core/managers/memory_manager.py` — `MemoryManager`（CRUD + lifecycle + decay + basic search）
- [x] `core/tasks/decay.py` — 接收 `DecayConfig`，衰减后自动归档低于阈值的事件
- [x] `core/tasks/synthesis.py` — 接收 `SynthesisConfig`，persona prompt / impression prompt 可配置
- [x] `core/tasks/summary.py` — 接收 `SummaryConfig`，group summary prompt 可配置

---

## 待完成

---

### Step 2 — repository 检索加 `active_only` 过滤

**文件：** `core/repository/base.py`、`core/repository/sqlite.py`

**接口变更：**
```python
# base.py — 两个抽象方法加参数
async def search_fts(self, query: str, limit: int = 20, active_only: bool = True) -> list[Event]: ...
async def search_vector(self, embedding: list[float], limit: int = 20, active_only: bool = True) -> list[Event]: ...
```

**SQLite 实现：**
```sql
-- search_fts with active_only=True
SELECT <cols> FROM events e
WHERE e.rowid IN (SELECT rowid FROM events_fts WHERE events_fts MATCH ? ORDER BY rank LIMIT ?)
  AND e.status = 'active'
ORDER BY e.salience DESC;

-- search_vector with active_only=True
SELECT <cols> FROM (
    SELECT rowid, distance FROM events_vec WHERE embedding MATCH ? ORDER BY distance LIMIT ?
) v JOIN events e ON e.rowid = v.rowid
WHERE e.status = 'active'
ORDER BY v.distance;
```
当 `active_only=False` 时去掉 `AND e.status = 'active'` 子句。

---

### Step 3 — rrf.py + hybrid.py 更新

**文件：** `core/retrieval/rrf.py`、`core/retrieval/hybrid.py`

**rrf.py** 新增：
```python
def rrf_scores(ranked_lists: list[list[Event]], k: int = 60) -> dict[str, float]:
    """返回 event_id → RRF 原始得分（不排序不截断），供 RecallManager 做加权融合用。"""
```

**hybrid.py** 新增方法 `search_raw()`，暴露未融合的双路结果：
```python
async def search_raw(
    self, query: str, active_only: bool = True
) -> tuple[list[Event], list[Event]]:
    """返回 (bm25_results, vec_results)，编码在 asyncio.to_thread 中执行避免阻塞热路径。"""
    bm25 = await self._event_repo.search_fts(query, limit=self._bm25_limit, active_only=active_only)
    vec: list[Event] = []
    if self._encoder.dim > 0:
        embedding = await asyncio.to_thread(self._encoder.encode, query)
        vec = await self._event_repo.search_vector(embedding, limit=self._vec_limit, active_only=active_only)
    return bm25, vec
```

原有 `search()` 方法保留，改为在内部调用 `search_raw()` + `rrf_fuse()`。

---

### Step 4 — formatter.py 注入标记

**文件：** `core/retrieval/formatter.py`

- 从 `core.config` 导入 `MEMORY_INJECTION_HEADER`、`MEMORY_INJECTION_FOOTER`、`FAKE_TOOL_CALL_ID_PREFIX`
- `format_events_for_prompt()` 不再直接返回裸字符串，而是返回不带 wrapper 的正文（wrapper 由 RecallManager 加）
- 新增 `format_events_for_fake_tool_call(events, query) -> list[dict]`，返回两条 OpenAI 格式消息：

```python
# 消息1：assistant 宣布调用工具
{
    "role": "assistant",
    "content": None,
    "tool_calls": [{
        "id": f"{FAKE_TOOL_CALL_ID_PREFIX}{uuid}",
        "type": "function",
        "function": {"name": "recall_memory", "arguments": json.dumps({"query": query})}
    }]
}
# 消息2：tool 返回结果
{
    "role": "tool",
    "tool_call_id": f"{FAKE_TOOL_CALL_ID_PREFIX}{uuid}",
    "content": <format_events_for_prompt(events)>
}
```

---

### Step 5 — managers/base.py 重构

**文件：** `core/managers/base.py`

当前 `base.py` 只有 `BaseMemoryManager`。改为三层：

```
BaseManager                  # 通用基类：仅提供 logger
  ├── BaseMemoryManager      # 现有接口不变，继承 BaseManager
  └── BaseRecallManager      # 新增，定义 RecallManager 公共契约
```

```python
class BaseManager:
    """通用基类，提供 logger。所有 Manager 继承此类。"""
    def __init__(self) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)

class BaseMemoryManager(BaseManager, ABC):
    # 现有所有抽象方法保持不变

class BaseRecallManager(BaseManager, ABC):
    @abstractmethod
    async def recall(self, query: str, group_id: str | None = None) -> list[Event]: ...

    @abstractmethod
    async def recall_and_inject(
        self, query: str, req, session_id: str, group_id: str | None = None
    ) -> int:
        """返回实际注入的事件数量。"""
        ...

    @abstractmethod
    def clear_previous_injection(self, req) -> int:
        """从 req 中清除上轮注入的标记块，返回清除数量。"""
        ...
```

---

### Step 6 — recall_manager.py

**文件：** `core/managers/recall_manager.py`

**构造：**
```python
class RecallManager(BaseRecallManager):
    def __init__(
        self,
        retriever: HybridRetriever,
        retrieval_config: RetrievalConfig,
        injection_config: InjectionConfig,
    ) -> None: ...
```

**recall() 逻辑：**
1. 调用 `retriever.search_raw(query, active_only=cfg.active_only)` 获得 `(bm25, vec)`
2. 计算 `scores = rrf_scores([bm25, vec], k=cfg.rrf_k)`
3. 合并去重为候选池（最多 `bm25_limit + vec_limit` 条）
4. vector_fallback：若 `bm25` 为空且 `vector_fallback_enabled=True`，直接用 `vec` 候选
5. 对候选池做加权重排：
   ```python
   max_rrf = max(scores.values()) or 1.0
   recency = exp(-log(2) * days_since_end / half_life_days)
   final_score = (relevance_weight * scores[id] / max_rrf
                + salience_weight * event.salience
                + recency_weight * recency)
   ```
6. 按 `final_score` 降序，截取 `final_limit` 条

**recall_and_inject() 逻辑：**
1. 若 `auto_clear`，先调用 `clear_previous_injection(req)`
2. 调用 `recall(query, group_id)` 得到 events
3. `format_events_for_prompt(events, token_budget=cfg.token_budget)` 得到正文
4. 用 `MEMORY_INJECTION_HEADER` + 正文 + `MEMORY_INJECTION_FOOTER` 包装
5. 按 `position` 分支注入：
   - `system_prompt` → `req.system_prompt += "\n\n" + wrapped`
   - `user_message_before` → `req.prompt = wrapped + "\n\n" + req.prompt`
   - `user_message_after` → `req.prompt = req.prompt + "\n\n" + wrapped`
   - `fake_tool_call` → `req.contexts.extend(format_events_for_fake_tool_call(events, query))`
     （fake_tool_call 模式不加 header/footer wrapper，通过 FAKE_TOOL_CALL_ID_PREFIX 识别清理）

**clear_previous_injection() 逻辑：**
参考 LivingMemory EventHandler._remove_injected_memories_from_context 的实现：
- 用 `re.compile(re.escape(HEADER) + r".*?" + re.escape(FOOTER), re.DOTALL)` 清理 `req.system_prompt` 和 `req.prompt`
- 遍历 `req.contexts`，清理字符串内容中的标记块
- 另用 FAKE_TOOL_CALL_ID_PREFIX 识别并删除 fake tool call 消息对（assistant + tool）

**更新 `core/managers/__init__.py`：**
```python
from .memory_manager import MemoryManager
from .recall_manager import RecallManager
__all__ = ["MemoryManager", "RecallManager"]
```

---

### Step 7 — PluginInitializer + EventHandler

**文件：** `core/plugin_initializer.py`、`core/event_handler.py`

参考 LivingMemory 的 `plugin_initializer.py` + `event_handler.py` 分离模式。

**PluginInitializer** 职责：
- 接收 `context`、`PluginConfig`、`data_dir`
- `initialize()` 按顺序构建所有组件，存为 instance 属性：
  ```
  db → repos (persona/event/impression) → encoder → retriever
  → memory_manager → recall_manager → extractor → router
  → scheduler (注册5个任务) → webui → watcher → syncer
  ```
- `teardown()` 按逆序关闭：watcher → webui → scheduler → router.flush_all() → exit_stack.aclose()

**EventHandler** 职责：
- 接收 `PluginInitializer` 实例（通过属性访问各组件）
- `handle_llm_request(event, req)` — 调用 `recall_manager.recall_and_inject()`
- `handle_message(event)` — 调用 `router.process()`

**关键接口依赖：**
```python
# event.unified_msg_origin → session_id（str）
# event.get_group_id() → group_id（str | None）
# event.message_str → 原始用户文本（用作召回查询，避免 req.prompt 被污染）
# req.system_prompt / req.prompt / req.contexts → 注入目标
```

---

### Step 8 — 重构 main.py

**文件：** `main.py`

重构为轻量的 Star 壳，所有逻辑委托给 PluginInitializer + EventHandler：

```python
class EnhancedMemoryPlugin(Star):
    def __init__(self, context):
        super().__init__(context)
        self._initializer: PluginInitializer | None = None
        self._handler: EventHandler | None = None

    async def initialize(self):
        cfg = PluginConfig(self.config or {})
        data_dir = StarTools.get_data_dir("astrbot_plugin_enhanced_memory")
        self._initializer = PluginInitializer(self.context, cfg, data_dir)
        await self._initializer.initialize()
        self._handler = EventHandler(self._initializer)

    @filter.on_llm_request()
    async def on_llm_request(self, event, req):
        if self._handler:
            await self._handler.handle_llm_request(event, req)

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event):
        if self._handler:
            await self._handler.handle_message(event)

    async def terminate(self):
        if self._initializer:
            await self._initializer.teardown()
```

---

### Step 9 — CHANGELOG.md

记录所有已完成和本次开发的变更，格式参考 Keep a Changelog。
内容涵盖：domain model 变化、config 扩展、retrieval 改进、manager 架构、注入模式、数据安全TODO。

---

## 数据安全（后续处理，非本次 sprint）

以下问题已在分析文档中记录，留作下一个 sprint：

| 问题 | 方案 |
|------|------|
| 迁移前无自动备份 | `migrations/runner.py` 开头加 `shutil.copy(db_path, db_path.with_suffix(".db.bak"))` |
| `delete_event` 两步无事务 | `MemoryManager.delete_event()` 用单一 `BEGIN…COMMIT` 包裹两步 |
| `PersonaRepository.upsert` 假事务 | 改为 `async with db.execute("BEGIN")` 真正的事务块（aiosqlite 需用 `await db.execute("BEGIN")` 手动管理） |
| 检索无 group_id scope | `RecallManager.recall()` 已预留 `group_id` 参数，Step 6 实现时补充 SQL 过滤条件 |
| 跨平台合并无管理入口 | WebUI Settings 页添加 "合并身份" 操作，调用 `PersonaRepository.bind_identity()` |
