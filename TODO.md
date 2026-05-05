# Implementation TODO

按优先级排列。每项包含：目标、涉及文件、关键接口/思路。

---

## P0 — 记忆隔离（对话 / 人格 / Bot 视角）

**目标**：确保检索、Impression 聚合、Recall 注入均按 `group_id` scope 隔离，私聊与群聊事件不互相污染，Bot 在不同群有独立视角。

**涉及文件**：
- `core/repository/base.py` — `search_fts`、`search_vector` 加 `group_id` 参数
- `core/repository/sqlite.py` — SQL WHERE 追加 `AND (? IS NULL OR e.group_id = ?)`
- `core/retrieval/hybrid.py` — `search_raw()` 透传 `group_id`
- `core/managers/recall_manager.py` — `recall()` 将 `group_id` 传入 `search_raw()`
- `core/tasks/synthesis.py` — `run_impression_aggregation` 按 scope 分组取事件，只取 `e.group_id = scope` 的 event 作为 evidence

**关键接口变更**：
```python
# base.py
async def search_fts(self, query: str, limit: int = 20,
                     active_only: bool = True, group_id: str | None = None) -> list[Event]: ...
async def search_vector(self, embedding: list[float], limit: int = 20,
                        active_only: bool = True, group_id: str | None = None) -> list[Event]: ...

# hybrid.py
async def search_raw(self, query: str, active_only: bool = True,
                     group_id: str | None = None) -> tuple[list[Event], list[Event]]: ...

# recall_manager.py — recall() 内部
bm25, vec = await self._retriever.search_raw(
    query, active_only=cfg.active_only, group_id=group_id
)
```

**SQL 追加片段**（sqlite.py，放在 status 过滤之后）：
```sql
AND (? IS NULL OR e.group_id = ?)
```
绑定参数 `(group_id, group_id)`，`group_id=None` 时两个占位符都传 `None`，IS NULL 条件成立，不过滤。

---

## P1 — retrieval 模块整理 + formatter 迁移到 utils

**目标**：`core/retrieval/` 只放纯粹的检索算法实现；格式化工具类迁移到 `core/utils/`。

**当前 `core/retrieval/` 文件**：
- `rrf.py` — RRF 算法 → **保留**，重命名建议：`rrf_fusion.py`
- `hybrid.py` — BM25 + vector 混合检索 → **保留**，重命名建议：`hybrid_retriever.py`
- `formatter.py` — 事件格式化为 prompt 文本 → **迁移到 `core/utils/formatter.py`**

**迁移步骤**：
1. `mv core/retrieval/formatter.py core/utils/formatter.py`
2. 修改所有引用：`core/managers/recall_manager.py`（`from ..retrieval.formatter` → `from ..utils.formatter`）
3. 更新 `core/retrieval/__init__.py` 和 `core/utils/__init__.py`

**重命名步骤**（可选，若要保持一致性）：
- `core/retrieval/rrf.py` → `core/retrieval/rrf_fusion.py`，更新 `hybrid.py` 内 import
- `core/retrieval/hybrid.py` → `core/retrieval/hybrid_retriever.py`，更新所有引用

---

## P1 — 关系图谱功能开关 + WebUI 面板联动

**目标**：允许用户通过配置禁用整个社交关系图谱模块（Impression 推断、关系图 WebUI 面板），禁用时系统内存功能完整保留。

**涉及文件**：
- `_conf_schema.json` — 已有 `relation_enabled`，确认描述准确
- `core/config.py` — 已有 `PluginConfig.relation_enabled` 属性，确认透传
- `core/plugin_initializer.py` — `run_impression_aggregation` 注册调度任务前检查 `cfg.relation_enabled`
- `web/server.py` — `/api/graph` 和 `/api/impressions` 相关路由在 `relation_enabled=False` 时返回 `{"enabled": false, "data": []}` 而非 404，前端据此锁定面板
- 前端 `web/frontend/app/graph/page.tsx` — 检查 `/api/config` 中的 `relation_enabled`，为 false 时显示"功能已关闭"占位组件并禁用所有操作按钮

**server.py 改动思路**：`WebuiServer.__init__` 接收 `relation_enabled: bool` 参数（从 `initial_config` 读取），在 `_build_app` 中对图谱路由统一加前置守卫：
```python
async def _graph_disabled_guard(self, request):
    if not self._relation_enabled:
        return _json({"enabled": False, "nodes": [], "edges": []})
    return None  # continue to real handler
```

---

## P2 — 核心数据流验证 + API 整理 + 开发测试入口

**目标**：梳理 manager 层数据流，将前后端交互接口集中到 `core/api.py`，添加 `run_core_dev.py` 做端到端数据流冒烟测试。

### 2a. 接口整理到 core/api.py

**新文件** `core/api.py`：将 `web/server.py` 中的 handler 函数调用的所有业务逻辑（目前散在 server.py 的匿名 lambda 或内联代码）抽取为独立函数，server.py 只做 HTTP 适配。

```python
# core/api.py 草案（函数签名）
async def get_stats(memory: MemoryManager) -> dict: ...
async def list_events(event_repo, group_id, limit) -> list[dict]: ...
async def get_event(event_repo, event_id) -> dict | None: ...
async def update_event(memory, event_id, patch: dict) -> dict: ...
async def delete_event(memory, event_id) -> bool: ...
async def list_personas(persona_repo) -> list[dict]: ...
async def get_graph(persona_repo, impression_repo, scope) -> dict: ...  # nodes + edges
async def update_impression(impression_repo, observer, subject, scope, patch) -> dict: ...
async def recall_preview(recall_manager, query, group_id) -> list[dict]: ...
```

### 2b. run_core_dev.py（根目录）

**用途**：在不启动 AstrBot 的情况下，用 mock 事件测试完整数据流：消息接入 → 边界检测 → 事件提取 → 存储 → 检索 → Impression 更新 → 召回注入。

**思路**：
```python
# run_core_dev.py
import asyncio
from pathlib import Path
from core.repository.sqlite import db_open, SQLiteEventRepository, ...
from core.managers import MemoryManager, RecallManager
# ...

async def main():
    async with db_open(Path("/tmp/dev_core.db")) as db:
        # 构造各 repo
        # 构造 mock Event，手动调用 memory.add_event()
        # 调用 recall.recall("测试查询") 验证检索结果
        # 打印输出，验证 Impression 是否生成
        ...

asyncio.run(main())
```

---

## P2 — 后端数据安全

**目标**：修复已知事务安全问题，加可配置开关，补充测试。

| 问题 | 文件 | 修复方案 |
|------|------|---------|
| 迁移前无自动备份 | `migrations/runner.py` | `run_migrations()` 开头加 `shutil.copy(db_path, db_path.with_suffix(".db.bak"))`，开关：`migration_auto_backup: bool = true` |
| `delete_event` 两步无事务 | `core/managers/memory_manager.py` | 用 `async with db.execute("BEGIN"): delete_vector → delete`，或在 repo 层暴露原子删除方法 |
| `PersonaRepository.upsert` 假事务 | `core/repository/sqlite.py` | `await db.execute("BEGIN")` → 批量操作 → `await db.commit()`，失败时 `await db.rollback()` |
| 检索无 group_id scope | 见 P0 | 已在 P0 中解决 |
| 跨平台合并无管理入口 | `web/server.py` + 前端 Settings 页 | WebUI Settings 加"合并身份"操作，调用 `PersonaRepository.bind_identity()` |

**新增配置项**（`_conf_schema.json` + `core/config.py`）：
```json
"migration_auto_backup": {"type": "bool", "default": true, "description": "迁移前自动备份数据库文件"}
```

**测试**：在 `run_core_dev.py` 中加事务回滚场景验证。

---

## P3 — WebUI Config 页面联通

**目标**：`web/frontend/app/config/page.tsx` 实现对 `_conf_schema.json` 中所有配置项的读取和修改，CRUD 一致。

**后端需要的接口**（加入 `core/api.py` + `web/server.py`）：
```
GET  /api/config          → 返回当前配置值（从 initial_config + 运行时覆盖合并）
PUT  /api/config          → 接受 {key: value} patch，写回持久化配置文件，需 sudo
GET  /api/config/schema   → 返回 _conf_schema.json 内容（前端据此渲染表单）
```

**前端思路**：`/api/config/schema` 驱动动态表单渲染（按 type 字段选择 bool/int/float/string 控件），提交时调用 `PUT /api/config`（需 sudo guard）。

---

## P3 — ML Impression 生成器 + Event 数量触发聚合

**目标**：双轨制 Impression 更新——每次 event close 后 ML 快速更新，LLM 周期任务降频做深度校正。

### ML 聚合器

**新文件** `core/impression/ml_aggregator.py`：

```python
class MLImpressionAggregator:
    def fit_impression(self, observer_uid, subject_uid, scope,
                       events: list[Event], existing: Impression | None) -> Impression: ...
```

特征向量：`event_count`、`avg_salience`、`tag_sentiment`（内置情感词典）、`recency_score`、`interaction_frequency`。

降级：`scikit-learn` 未安装时自动回落到规则模式（event_count 阈值 + tag 关键词）。冷启动（event_count < 3）直接返回 `relation_type="stranger"`。

### Event 数量触发

**修改** `core/plugin_initializer.py` 的 `on_event_close` 回调：
```python
if cfg.relation_enabled and cfg.impression_event_trigger_enabled:
    asyncio.create_task(_maybe_trigger_impression(event, impression_repo, aggregator, cfg))
```

**新增配置项**：
```json
"impression_event_trigger_enabled": {"type": "bool", "default": true},
"impression_event_trigger_threshold": {"type": "int", "default": 5},
"impression_trigger_debounce_hours": {"type": "float", "default": 1.0}
```

触发逻辑：遍历 event.participants 中所有 (obs, subj) 对，检查 `last_reinforced_at` 距今是否超过 debounce，以及该 scope 下新事件数是否 ≥ threshold，满足则调用 `aggregator.fit_impression()` 并 upsert。
