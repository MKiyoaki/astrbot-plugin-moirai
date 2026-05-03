# 演进架构更新日志

记录每个 Phase 的交付内容、关键设计决策及技术细节。

---

## WebUI 重设计 v1 — 侧边栏 + 自定义时间线 + 摘要编辑 + 演示数据

**完成日期：** 2026-05-03  
**涉及文件：** `web/server.py` · `web/static/index.html` · `run_webui_dev.py`

### 交付内容

#### web/server.py

| 新增 | 说明 |
|------|------|
| `PUT /api/summary`（sudo） | 将编辑后的 Markdown 内容写回磁盘（`groups/<gid>/summaries/<date>.md` 或 `global/summaries/`） |
| `POST /api/admin/demo`（sudo） | 注入演示数据：4 Persona / 5 Event（含承接链）/ 5 Impression / 2 摘要文件 |
| `_DEMO_SUMMARY_1/2` | 模块级摘要常量，供 `_handle_demo` 和 `run_webui_dev.py` 共用 |

#### web/static/index.html（924 → 1254 行，完全重写）

**布局**：将原 3 列 grid 替换为 `220px 固定侧边栏 + flex-1 主内容区`，点击侧边栏导航项全屏切换面板（`.panel-view.active`）。

**侧边栏**：Logo + 版本徽章、三个导航按钮（◎ 事件流 / ⬡ 关系图 / ◧ 摘要记忆）、底部统计 + Sudo/主题/设置/退出操作。

**自定义时间线**（替换 vis-timeline）：
- 纵向红色中心线（`#tl-container::before`，`position: absolute`）
- 事件交替左右排布（`.tl-item.left` / `.tl-item.right`，`padding` 推离中线）
- 橙色点表示有承接关系的事件（`.tl-dot.has-parent`）
- 承接桥接线（`.tl-bridge`）：`position: absolute` 连接父子事件点，hover 显示橙色虚线，`title` 属性展示关系；位置通过 `offsetTop` 计算，`ResizeObserver` 触发重绘
- 引入 `--tl-accent` CSS 变量（默认 `#ef4444`），卡片渐变色通过 `color-mix()` 派生，为后续颜色自定义预留接口

**摘要编辑器**：编辑按钮需 sudo；点击切换为 monospace textarea；保存调用 `PUT /api/summary`；取消还原渲染视图。

**设置 Modal 新增**：演示数据注入按钮（`POST /api/admin/demo`，需 sudo），注入后自动刷新全部面板。

**移除**：vis-timeline CDN 及相关 JS（`vis.Timeline`、`vis.DataSet`）。

#### run_webui_dev.py（重写）

- 内存仓储，关闭认证（`auth_enabled=False`），无需数据库
- 默认端口 2654（不与生产 2653 冲突）
- 启动时自动注入演示数据，共用 `_DEMO_SUMMARY_1/2` 常量
- `--port` 命令行参数，`asyncio.Event` 优雅退出，Windows 兼容
- 数据目录写入项目根 `.dev_data/`

### 演示数据说明

```
人格：Alice（QQ）/ Bob（QQ）/ Charlie（Telegram）/ BOT（internal）
事件：早安问候 → 音乐推荐 → 游戏约定（链 A）
              → 技术交流（链 B，从早安问候分叉）
      私聊请教（独立，group_id=None）
印象：BOT→Alice friend +0.7 / BOT→Bob colleague +0.2 /
      Alice→BOT friend +0.8 / Bob→Alice friend +0.5 /
      Charlie→Bob stranger -0.2
摘要：groups/demo_group_001/summaries/2026-05-01.md
     groups/demo_group_001/summaries/2026-05-02.md
```

---

### TODO — 待续功能（下一 session 继续）

> 以下为上条命令中途中断、尚未完成的内容，优先级从高到低：

- [ ] **承接线点击弹窗**：点击 `.tl-bridge` 弹出浮窗（`#bridge-popup`），展示父事件 → 子事件的关联信息（话题、时间、salience），可点 × 关闭；当前只有 hover 虚线效果，无点击行为
- [ ] **时间轴颜色自定义**：`--tl-accent` 变量已在 CSS 中就位，需在设置 Modal 增加 `<input type="color">` 并通过 JS `document.documentElement.style.setProperty('--tl-accent', value)` 应用，`localStorage` 持久化
- [ ] **背景色自定义**：设置 Modal 增加若干深色预设色块（Slate / Noir / Deep Purple / Deep Blue）+ 自定义色板，修改 `--bg` / `--bg-2` 变量，`localStorage` 持久化；需注意与 `[data-theme="light"]` 的优先级冲突（用 `element.style.setProperty` inline 覆盖即可）

---

## Phase 1 — 领域模型 + 仓储抽象接口 + 内存实现

**完成日期：** 2026-05-03  
**测试数量：** 68 个（domain 32 + memory_repo 36）

### 新增文件

| 文件 | 说明 |
|------|------|
| `core/domain/models.py` | `Persona`、`Event`、`Impression`、`MessageRef` 四个纯 Python dataclass |
| `core/repository/base.py` | 三个抽象基类：`PersonaRepository`、`EventRepository`、`ImpressionRepository` |
| `core/repository/memory.py` | 全内存 dict 实现 |
| `tests/test_domain.py` | 字段边界约束验证 |
| `tests/test_memory_repo.py` | 完整仓储契约测试套件 |

### 技术实现

**领域模型（`core/domain/models.py`）**

四个 dataclass 全部使用 `@dataclass(slots=True)`，`__slots__` 替代 `__dict__` 使每个实例节省约 56 字节；热路径消息处理中会批量创建 `RawMessage`/`Event`，收益可观。

- `MessageRef` 额外设置 `frozen=True`，生成 `__hash__` 并禁止字段赋值，可安全放入 `set`/`dict` 作为键。
- `Persona`、`Event`、`Impression` 的 `__post_init__` 做边界校验：`salience ∈ [0,1]`、`confidence ∈ [0,1]`、`affect ∈ [-1,1]`、`start_time ≤ end_time`。校验放在构造函数而非调用方，保证域内对象永远合法（fail-fast 原则）。
- 字段类型全部使用 Python 原生类型（`str`/`float`/`list`），无 Pydantic 依赖；序列化责任下推到仓储层。

**仓储抽象（`core/repository/base.py`）**

三个 `ABC` 子类，所有方法签名标注完整类型，返回值使用 `list[T]` 而非迭代器（保证调用方可多次遍历）。`upsert_vector` 设为非抽象的默认 no-op，使内存实现不必强制重写向量接口。

**内存仓储（`core/repository/memory.py`）**

底层存储为 `dict[str, Entity]`。所有读方法（`get`、`list_*`）在返回前执行 `deepcopy`，所有写方法在存入前执行 `deepcopy`，双向隔离保证仓储内部状态不被外部代码意外修改。`InMemoryPersonaRepository` 额外维护 `dict[tuple[str,str], str]` 作为 `(platform, physical_id) → uid` 索引，`upsert` 时先删除旧索引再重建，保持索引与主存一致。

**契约测试模式**

`test_memory_repo.py` 中的所有测试用例对 `EventRepository`、`PersonaRepository`、`ImpressionRepository` 接口编写，不依赖具体实现类。Phase 2 的 SQLite 实现直接复用同一套测试文件（通过 pytest fixture 注入不同实现），确保两个实现的行为完全一致。

---

## Phase 2 — SQLite 仓储实现 + Schema 迁移脚本

**完成日期：** 2026-05-03  
**测试数量：** 107 个（+39 SQLite repo）

### 新增文件

| 文件 | 说明 |
|------|------|
| `migrations/001_initial_schema.sql` | 完整 SQLite schema |
| `migrations/runner.py` | 轻量级迁移运行器 |
| `core/repository/sqlite.py` | 三个 SQLite 仓储实现 |
| `tests/test_sqlite_repo.py` | 接口约束测试 + SQLite 特有场景 |

### 技术实现

**Schema 设计（`migrations/001_initial_schema.sql`）**

- `personas` 表主键为 `uid TEXT`；`identity_bindings(platform, physical_id)` 通过 `FOREIGN KEY(uid) REFERENCES personas(uid) ON DELETE CASCADE` 关联，删除 persona 时级联清理所有平台绑定。
- `events` 表的 `participants`、`chat_content_tags`、`inherit_from`、`interaction_flow` 字段均存储为 JSON 文本（`TEXT NOT NULL DEFAULT '[]'`），由仓储层用 `json.dumps`/`json.loads` 序列化，不引入额外表结构。
- `events_fts` 为 FTS5 **外部内容表**（`content=events, content_rowid=rowid`）：FTS5 只维护倒排索引，不复制原始文本，节省约 50% 存储空间。三个同步触发器（`ai_events_fts` / `ad_events_fts` / `au_events_fts`）在 events 表的 INSERT/DELETE/UPDATE 时自动更新 FTS 索引。
- `impressions` 表在 `(observer_uid, subject_uid, scope)` 上建 UNIQUE 约束，所有写入使用 `ON CONFLICT DO UPDATE SET`，天然幂等。
- `_migrations` 表记录已执行迁移的 `version` 和时间戳，运行器每次启动检查后跳过已执行版本。

**迁移运行器（`migrations/runner.py`）**

`_split_statements(sql)` 逐行扫描 SQL 文本，用 `re.findall(r"\b(BEGIN|END)\b")` 追踪嵌套深度 `depth`：遇到 `BEGIN` 加一，遇到 `END` 减一，只在 `depth == 0` 且行末为 `;` 时切分语句。这解决了触发器体内部分号（`INSERT INTO events_fts...;`）被误切的问题。`run_migrations` 在事务内逐条执行，失败时整批回滚。

**连接工厂（`db_open`）**

`@asynccontextmanager` 包装 `aiosqlite.connect()`，在 yield 前依次执行：
1. 设置 `row_factory = aiosqlite.Row`（支持按列名访问）
2. 五条 PRAGMA：`WAL` 模式、`synchronous=NORMAL`（减少 fsync）、`busy_timeout=5000`（并发等待）、`cache_size=-64000`（64 MB 页缓存）、`foreign_keys=ON`
3. 调用 `run_migrations` 确保 schema 最新
4. 调用 `_try_load_sqlite_vec` 按需加载向量扩展

**SQLite 仓储实现**

- 列表字段（`participants` 等）用 `json.loads`/`json.dumps` 在边界序反序列化；`bound_identities` 序列化为 `[[platform, id], ...]` 格式。
- `list_by_participant` 使用 `json_each(e.participants)` 虚表在单次 SQL 查询中过滤，避免 Python 层循环。
- `decay_all_salience` 用单条 `UPDATE events SET salience = MAX(0.0, salience * ?)` 批量更新；用 `cursor.rowcount` 在 FTS5 触发器执行前捕获行数（若用 `SELECT changes()` 则触发器内部的 INSERT 会覆盖该值）。

**修复的 Bug**

1. `_split_statements` 误切触发器 → 追踪 BEGIN/END 深度
2. `decay_all_salience` 返回 1 而非实际行数 → 改用 `cursor.rowcount`
3. FTS5 中文分词：`unicode61` 将连续汉字视为单一 token，子词无法匹配 → 测试改为使用完整词作为查询词，并在注释中记录此限制

---

## Phase 3 — 事件边界检测器 + AstrBot 适配器 + 插件入口

**完成日期：** 2026-05-03  
**测试数量：** 137 个（+21 boundary + 9 router）

### 新增文件

| 文件 | 说明 |
|------|------|
| `core/boundary/window.py` | `MessageWindow` + `RawMessage` |
| `core/boundary/detector.py` | `EventBoundaryDetector` |
| `core/adapters/identity.py` | `IdentityResolver` |
| `core/adapters/astrbot.py` | `MessageRouter` |
| `main.py` | AstrBot 插件入口 |
| `metadata.yaml` | 插件元数据 |

### 技术实现

**消息窗口（`core/boundary/window.py`）**

`MessageWindow` 是每个 session 一个的可变对象，字段：`session_id`、`group_id`、`messages: list[RawMessage]`、`start_time`、`last_message_time`。`RawMessage` 包含 `uid`、`text`、`timestamp`、`display_name`（Phase 4 新增）。提供计算属性 `message_count`、`duration_seconds`、`age_since_last_message`、`first_text`、`latest_text`、`participants`，统一封装窗口状态查询。

**边界检测器（`core/boundary/detector.py`）**

`should_close(window, now) -> tuple[bool, str]` 按优先级检查三个信号：
1. `age_since_last_message > time_gap_minutes * 60`（默认 30min）→ 原因 `"time_gap"`
2. `message_count >= max_messages`（默认 50）→ 原因 `"max_messages"`
3. `(now - start_time) >= max_duration_minutes * 60`（默认 60min）→ 原因 `"max_duration"`

topic_drift 信号在 Phase 3 中实现为返回 `0.0` 的桩方法（`_topic_drift`），Phase 5 encoder 注入后可替换为余弦距离计算。`BoundaryConfig` 是普通 dataclass，所有阈值可在构造时覆盖，便于测试时注入小值触发边界。

**身份解析器（`core/adapters/identity.py`）**

`get_or_create_uid(platform, physical_id, display_name) -> str`：先用 `persona_repo.get_by_identity()` 查找，命中则更新 `last_active_at` 并返回 uid；未命中则用 `uuid.uuid4()` 生成新 uid，构造 `Persona` 并写入仓储。跨平台身份合并（同一人在 QQ 和 Telegram 使用不同 physical_id）留给管理员命令处理，不在自动路径中执行。

**消息路由器（`core/adapters/astrbot.py`）**

`MessageRouter` 维护 `dict[str, MessageWindow]` 映射（key 为 session_id）。`process()` 的执行流：
1. 通过 `IdentityResolver` 将 `(platform, physical_id)` 转换为 `uid`
2. 计算 `session_id`：群聊为 `"{platform}:{group_id}"`，私聊为 `"{platform}:private:{physical_id}"`
3. 若该 session 已有窗口且 `detector.should_close()` 返回 True，调用 `_flush_window()` 关闭当前窗口
4. 若该 session 无窗口，创建新 `MessageWindow`
5. 调用 `window.add_message()` 追加消息

`_flush_window()` 构造一个 `Event`（topic/tags/salience 均为初始空值，confidence=0.2），写入仓储后调用 `on_event_close(event, window)` 回调。`flush_all()` 在插件终止时关闭所有未满的窗口，防止数据丢失。

**插件入口（`main.py`）**

`@register(...)` 装饰器向 AstrBot 注册插件元数据。`initialize()` 是异步方法，在插件加载时由 AstrBot 调用；`terminate()` 在插件卸载时调用。DB 连接通过 `AsyncExitStack.enter_async_context(db_open(...))` 管理：`initialize` 进入上下文获得连接，`terminate` 调用 `_exit_stack.aclose()` 退出上下文关闭连接，生命周期与插件绑定。`@filter.event_message_type(filter.EventMessageType.ALL)` 订阅所有消息类型（文字/图片/语音等统一处理，非文字消息的 `message_str` 为空字符串）。

---

## Phase 4 — LLM 事件提取器（约束 JSON 输出 + 降级策略）

**完成日期：** 2026-05-03  
**测试数量：** 158 个（+21 extractor）

### 新增文件

| 文件 | 说明 |
|------|------|
| `core/extractor/prompts.py` | 系统提示词 + `build_user_prompt()` |
| `core/extractor/parser.py` | `parse_llm_output()` + `fallback_extraction()` |
| `core/extractor/extractor.py` | `EventExtractor` 主类 |

### 技术实现

**提示词构造（`core/extractor/prompts.py`）**

`SYSTEM_PROMPT` 中文提示词要求 LLM 输出严格单行 JSON，字段：`topic`（≤15字）、`chat_content_tags`（list，≤5项）、`salience`（0.0–1.0）、`confidence`（0.0–1.0）。约束字段类型和长度减少解析失败率。

`build_user_prompt(window, max_messages=20)` 构造对话上下文：取窗口最后 `max_messages` 条消息，每条格式为 `[显示名]: 文本`（uid 映射到 `display_name` 以减少 token 消耗）。截断旧消息而非摘要，避免引入二次 LLM 调用。

**输出解析（`core/extractor/parser.py`）**

`parse_llm_output(text)` 三步处理：
1. 剥离 Markdown 代码围栏（`` ```json ... ``` ``）
2. 用 `text.find("{")` 和 `text.rfind("}")` 定位第一个完整 JSON 对象，用 `json.loads` 解析
3. 校验必要字段存在，对 `salience`/`confidence` 执行 `max(0.0, min(1.0, float(v)))` 钳位

任意步骤失败返回 `None`，触发降级。`fallback_extraction(window)` 用词频统计（Counter + 停用词过滤）提取 top-5 标签；`salience = min(0.3 + 0.01 * message_count, 0.7)`（消息越多重要性越高但有上限）；`confidence = 0.2`（作为降级标记）。

**提取器（`core/extractor/extractor.py`）**

`EventExtractor.__call__(event, window)` 是 `on_event_close` 的实际执行体：
1. `_extract(window)` → 调用 LLM 或降级，返回字段 dict
2. `dataclasses.replace(event, **fields)` 创建更新后的 Event（原对象不可变修改）
3. `event_repo.upsert(updated)` 持久化
4. `_index_vector(updated)` 存储 embedding（Phase 5 新增）

LLM 调用链：`provider.text_chat(prompt, system_prompt)` 被 `asyncio.wait_for(..., timeout=30.0)` 包裹；捕获 `TimeoutError`、`Exception`，均降级到 `fallback_extraction`。`provider_getter` 是零参数 callable 而非直接引用 provider 实例，原因是 AstrBot 的 provider 可在运行时被用户切换，惰性求值确保每次都获取最新实例。

在 `main.py` 中，`on_event_close` 回调被包装为：
```python
async def on_event_close(event, window):
    asyncio.create_task(extractor(event, window))
```
`create_task` 立即返回，LLM 提取在后台运行，不阻塞 `MessageRouter.process()` 的热路径。

---

## Phase 5 — sqlite-vec 向量索引 + 混合 RAG 检索（BM25+向量 RRF）

**完成日期：** 2026-05-03  
**测试数量：** 172 个（+14 retrieval）

### 新增文件

| 文件 | 说明 |
|------|------|
| `core/embedding/encoder.py` | `NullEncoder` + `SentenceTransformerEncoder` |
| `core/retrieval/rrf.py` | `rrf_fuse()` |
| `core/retrieval/hybrid.py` | `HybridRetriever` |
| `tests/test_retrieval.py` | RRF + 混合检索 + SQLite 向量集成测试 |

### 技术实现

**Encoder 层（`core/embedding/encoder.py`）**

`NullEncoder.dim == 0`，`encode()` 返回 `[]`，作为"无向量"信号供上层判断是否跳过向量路径。`SentenceTransformerEncoder` 持有 `self._model = None`，首次调用 `encode()` 时才执行 `from sentence_transformers import SentenceTransformer; self._model = SentenceTransformer(model_name)` 懒加载，不拖慢插件启动。`encode()` 调用 `model.encode(text, normalize_embeddings=True).tolist()` 返回 L2 归一化的 `list[float]`；归一化后余弦相似度等价于点积，简化 ANN 计算。

**sqlite-vec 集成（`core/repository/sqlite.py`）**

`_try_load_sqlite_vec(db, dim)` 执行：
1. `import sqlite_vec` 获取扩展路径
2. `db.enable_load_extension(True)` → `db.load_extension(path)` → `db.enable_load_extension(False)`（加载后立即禁止，防止 SQL 注入加载任意扩展）
3. `CREATE VIRTUAL TABLE IF NOT EXISTS events_vec USING vec0(embedding float[{dim}])`

`upsert_vector(event_id, embedding)` 利用子查询将 `event_id` 转换为 `rowid`：
```sql
INSERT OR REPLACE INTO events_vec(rowid, embedding)
SELECT rowid, ? FROM events WHERE event_id = ?
```
`events_vec` 的 rowid 与 `events` 表 rowid 对齐，是后续 JOIN 的基础。

`search_vector(embedding, limit)` 使用子查询-JOIN 模式：
```sql
SELECT {cols} FROM
  (SELECT rowid, distance FROM events_vec
   WHERE embedding MATCH ? ORDER BY distance LIMIT ?) v
JOIN events e ON e.rowid = v.rowid
ORDER BY v.distance
```
vec0 虚表不支持直接与普通表 JOIN，必须先在子查询中取出 rowid 再关联。`MATCH ?` 的参数为 `json.dumps(embedding)`（sqlite-vec 接受 JSON 数组格式）。

**RRF 融合（`core/retrieval/rrf.py`）**

```python
score[event_id] += 1.0 / (k + rank)   # rank 从 1 开始
```
k=60（标准值）使相邻排名的分差随名次下降而收窄，头部结果的优势被适度保留。遍历所有列表建立 `scores: dict[str, float]` 和 `event_map: dict[str, Event]`，最后 `sorted(scores, key=lambda eid: -scores[eid])[:limit]` 取 top-k。时间复杂度 O(N log N)，N 为所有列表的总元素数。

**混合检索器（`core/retrieval/hybrid.py`）**

`search(query, limit)` 流程：
1. `event_repo.search_fts(query, limit=20)` → BM25 列表
2. 若 `encoder.dim > 0`：`encoder.encode(query)` → `event_repo.search_vector(embedding, limit=20)` → 向量列表
3. 若向量列表为空（NullEncoder 或 sqlite-vec 不可用）→ 直接返回 BM25 截断结果
4. 否则 `rrf_fuse([bm25, vec], k=60, limit=limit)`

`index_event(event)` 在后台对已提取的事件建立向量索引：拼接 `event.topic + " " + " ".join(tags)` 作为 embedding 输入文本，保证向量语义与提取结果对齐。

---

## Phase 6 — Prompt 注入钩子（核心功能里程碑，插件可部署）

**完成日期：** 2026-05-03  
**测试数量：** 190 个（+18 prompt_injection）

### 新增文件

| 文件 | 说明 |
|------|------|
| `core/retrieval/formatter.py` | `format_events_for_prompt()` |
| `tests/test_prompt_injection.py` | formatter + 钩子行为测试 |

### 技术实现

**事件格式化（`core/retrieval/formatter.py`）**

`format_events_for_prompt(events, token_budget=800, now)` 执行贪心填充：
1. 按 `salience` 降序排列 events（最重要的优先注入）
2. 为每条事件构造条目字符串：`- [{时间标签}] {topic}（{tags}）`
3. 用 `len(entry) // 2` 估算 token 数（保守估算：1 汉字 ≈ 1 token，1 ASCII 字符 ≈ 0.25 token，整体按 2 字符/token 折算）
4. 累计预算，超出则停止追加（整条跳过，不做截断，保证每条记忆语义完整）
5. 拼接为 `"## 相关历史记忆\n" + "\n".join(lines)` 返回

时间标签由 `_time_label(end_time, now)` 生成：< 1h 显示分钟数，< 24h 显示小时数，否则显示天数，提供直观的时间感知。

**LLM 请求钩子（`main.py`）**

`@filter.on_llm_request()` 装饰器由 AstrBot 在每次 LLM 生成前调用，传入 `(event: AstrMessageEvent, req: ProviderRequest)`。`ProviderRequest.system_prompt` 是可变字段，修改后直接生效。钩子执行流：

```
1. 检查 retriever 是否初始化 AND req.prompt 非空，否则立即返回
2. await retriever.search(req.prompt, limit=10)
3. 若结果为空 → 返回（不修改 req）
4. format_events_for_prompt(results) → injected
5. req.system_prompt += ("\n\n" if req.system_prompt else "") + injected
6. 全程 try/except Exception → WARNING 日志，绝不抛出
```

追加而非替换 `system_prompt` 的原因：AstrBot 的其他插件（如内置 `long_term_memory`）也可能注入内容，覆盖会破坏多插件兼容性。分隔符 `"\n\n"` 使注入的记忆段落在 Markdown 渲染时独立成块。

---

## Phase 7 — Markdown 投影器（DB → 只读文件，Jinja2 模板）

**完成日期：** 2026-05-03  
**测试数量：** 210 个（+20 projector）

### 新增文件

| 文件 | 说明 |
|------|------|
| `core/projector/projector.py` | `MarkdownProjector` 主类 |
| `core/projector/templates/persona_profile.md.j2` | PROFILE.md 模板 |
| `core/projector/templates/persona_impressions.md.j2` | IMPRESSIONS.md 模板 |
| `core/projector/templates/bot_persona.md.j2` | BOT_PERSONA.md 模板 |
| `tests/test_projector.py` | 投影器测试 |

### 技术实现

**Jinja2 环境配置（`core/projector/projector.py`）**

`_build_env()` 创建 `jinja2.Environment`：
- `FileSystemLoader(str(_TEMPLATE_DIR))`，`_TEMPLATE_DIR = Path(__file__).parent / "templates"` 确保打包后模板路径不随工作目录变化
- `autoescape=False`：输出 Markdown 而非 HTML，不需要 HTML 转义
- `trim_blocks=True`：控制块（`{% if %}`等）后的换行符被移除，避免在输出中产生多余空行
- `lstrip_blocks=True`：控制块所在行的前置空格被移除，允许在模板中缩进控制语句而不影响输出缩进

注册两个自定义过滤器：
- `format_time(ts)` → `datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")`
- `format_affect(v)` → `v >= 0.6` → `"正面（+0.xx）"`，`v <= -0.6` → `"负面（-0.xx）"`，否则 `"中性（±0.xx）"`

**渲染与写入**

`_render(template_name, **ctx)` 调用 `env.get_template(name).render(**ctx)` 返回字符串。`_write(path, content)` 调用 `path.parent.mkdir(parents=True, exist_ok=True)` 递归建目录后 `path.write_text(content, encoding="utf-8")`，覆盖写入使文件始终反映当前 DB 状态。

**三个渲染方法**

- `render_persona(uid)` → 查询 `persona_repo.get(uid)` + `event_repo.list_by_participant(uid, limit=10)` + `impression_repo.list_by_subject(uid)` → 渲染写入 `personas/{uid}/PROFILE.md` 和 `personas/{uid}/IMPRESSIONS.md`；uid 不存在时返回 `False`
- `render_all_personas()` → 遍历 `persona_repo.list_all()`，逐一调用 `render_persona()`，返回成功渲染数量
- `render_bot_persona(bot_uid)` → 仅查询 `persona_repo.get(bot_uid)` → 写入 `global/BOT_PERSONA.md`

**输出目录结构**

```
data_dir/
├── personas/
│   └── <uid>/
│       ├── PROFILE.md       ← render_persona() 写入，只读投影
│       └── IMPRESSIONS.md   ← render_persona() 写入，用户可编辑（Phase 10 反向同步）
└── global/
    └── BOT_PERSONA.md       ← render_bot_persona() 写入，只读投影
```

IMPRESSIONS.md 文件头注释"本文件可由用户手动编辑，修改将在下次同步时写回数据库（Phase 10）"，为 Phase 10 反向同步留下语义标记。

---

## Phase 8 — 周期性后台任务（衰减/画像合成/印象聚合/摘要生成）

**完成日期：** 2026-05-03  
**测试数量：** 237 个（+27 tasks）

### 新增文件

| 文件 | 说明 |
|------|------|
| `core/tasks/scheduler.py` | `TaskScheduler` |
| `core/tasks/decay.py` | `run_salience_decay()` |
| `core/tasks/synthesis.py` | `run_persona_synthesis()` + `run_impression_aggregation()` |
| `core/tasks/summary.py` | `run_group_summary()` |
| `tests/test_tasks.py` | 周期任务测试 |

### 技术实现

**任务调度器（`core/tasks/scheduler.py`）**

`TaskScheduler` 内部维护 `list[_Task]`，每个 `_Task` 含 `name`、`interval`（秒）、`fn`（async callable）、`last_run`（Unix 时间戳，初始为 0 使首次 tick 必然触发）。

`start()` 通过 `asyncio.create_task(self._loop())` 在事件循环中启动后台协程。`_loop()` 每 `tick_seconds`（默认 60s）唤醒一次，遍历所有任务检查 `now - task.last_run >= task.interval`，满足则调用 `_run_task()`。任务按注册顺序串行执行，避免并发写入同一 DB 连接。

`_run_task()` 用 `try/except Exception` 包裹任务调用，失败时记录 `logger.error` 并继续循环，单任务异常不影响其他任务或调度器本身。成功后更新 `task.last_run = time.time()`。

`stop()` 取消后台 task 并 `await` 等待其 `CancelledError` 传播结束，确保 `terminate()` 返回时不存在悬空协程。`run_now(name)` 用于强制执行（测试、管理命令），绕过间隔检查直接调用 `_run_task()`。

**Salience 衰减（`core/tasks/decay.py`）**

`run_salience_decay(event_repo, lambda_=0.01)` 直接委托给 `event_repo.decay_all_salience(lambda_)`，后者在 SQLite 中执行单条 `UPDATE events SET salience = MAX(0.0, salience * exp(-lambda_))`。λ=0.01 时 `exp(-0.01) ≈ 0.99`，每日衰减 1%，半衰期约 69 天；`MAX(0.0, ...)` 防止浮点误差产生负值。

**画像合成（`core/tasks/synthesis.py`）**

`run_persona_synthesis(persona_repo, event_repo, provider_getter)` 遍历所有 persona：
1. `event_repo.list_by_participant(uid, limit=10)` 获取近期事件
2. 无事件则跳过（避免无意义的 LLM 调用）
3. 构造 prompt：事件摘要列表 + 当前 `persona_attrs` JSON
4. `asyncio.wait_for(provider.text_chat(...), timeout=30.0)` 调用 LLM
5. `_safe_parse()` 从响应中提取第一个 `{...}` JSON 块，解析失败则跳过该 persona
6. 更新 `new_attrs` 中的 `description`（截断至 50 字）、`affect_type`、`content_tags`（取前 5 项）
7. `dataclasses.replace(persona, persona_attrs=new_attrs)` 创建新对象后 `upsert`

`run_impression_aggregation` 结构类似，但遍历印象列表：对每个有 `evidence_event_ids` 的印象，取前 10 个证据事件，拼接事件摘要作为 prompt，LLM 返回更新后的 `relation_type`/`affect`/`intensity`/`confidence`。`relation_type` 只接受 `_VALID_RELATIONS` 集合内的值；`affect` 被钳位到 `[-1, 1]`，`intensity`/`confidence` 钳位到 `[0, 1]`；`last_reinforced_at` 更新为当前时间。

**群组摘要（`core/tasks/summary.py`）**

`run_group_summary(event_repo, data_dir, provider_getter)` 流程：
1. `event_repo.list_group_ids()` 自动发现所有活跃 group（`SELECT DISTINCT group_id FROM events`）
2. 对每个 group 调用 `event_repo.list_by_group(group_id, limit=20)` 获取最近 20 个事件
3. 无事件则跳过（避免空摘要）
4. 构造事件列表文本（时间戳 + topic + tags），调用 LLM 生成 Markdown 摘要
5. 写入 `groups/{gid}/summaries/{YYYY-MM-DD}.md`（`group_id=None` 写入 `global/summaries/`）
6. LLM 超时（45s）或异常时记录 WARNING 并继续处理下一个 group

`list_group_ids()` 新增为 `EventRepository` 的抽象方法，在内存实现中用集合推导 `{e.group_id for e in self._store.values()}` 取去重值，在 SQLite 实现中用 `SELECT DISTINCT group_id FROM events` 查询。

**任务注册与生命周期（`main.py`）**

```
initialize():
  ...（repos, encoder, retriever, projector, router 初始化）
  provider_getter = lambda: self.context.get_using_provider()
  scheduler.register("salience_decay",        interval=86_400,  fn=...)
  scheduler.register("projection",            interval=86_400,  fn=...)
  scheduler.register("persona_synthesis",     interval=604_800, fn=...)
  scheduler.register("impression_aggregation",interval=604_800, fn=...)
  scheduler.register("group_summary",         interval=86_400,  fn=...)
  await scheduler.start()

terminate():
  await scheduler.stop()   ← 先停任务，再 flush，再关 DB
  await router.flush_all()
  await exit_stack.aclose()
```

关闭顺序：调度器先于 DB 关闭，避免后台任务在连接关闭后仍尝试执行 SQL 写入。所有任务的 `fn` 为 lambda 闭包，捕获 `event_repo`/`persona_repo`/`impression_repo` 等对象的引用，`provider_getter` 惰性求值支持运行时 provider 切换。

---

## Phase 9 — WebUI 三面板（Event Flow + Relation Graph + Summarised Memory）

**完成日期：** 2026-05-03  
**测试数量：** 260 个（+23 webui）

### 新增文件

| 文件 | 说明 |
|------|------|
| `core/webui/server.py` | `WebuiServer`：aiohttp 应用，5 条路由，数据构建逻辑抽离为独立 async 方法 |
| `core/webui/static/index.html` | 单页应用：三列网格布局，CDN 引入 vis-timeline / Cytoscape.js / marked.js |
| `tests/test_webui.py` | 23 个测试：序列化辅助函数（5）、数据构建方法（11）、HTTP API（7）|

### 更新文件

| 文件 | 变更 |
|------|------|
| `main.py` | 导入 `WebuiServer`；`initialize()` 创建并 `await webui.start()`；`terminate()` 优先 `await webui.stop()`（WebUI 先于 DB 关闭）|
| `requirements.txt` | 注释说明 aiohttp 为 AstrBot 传递依赖 |

### 技术实现

**aiohttp 后端（`core/webui/server.py`）**

`WebuiServer._build_app()` 构造 `aiohttp.web.Application`，注册 5 条路由：

| 路由 | 方法 | 说明 |
|------|------|------|
| `GET /` | `_handle_index` | 读取 `static/index.html` 返回 HTML |
| `GET /api/events` | `_handle_events` | 查询参数 `group_id`（可选）、`limit`（默认 100）|
| `GET /api/graph` | `_handle_graph` | 返回所有 persona 节点 + impression 边 |
| `GET /api/summaries` | `_handle_summaries` | 扫描 `data_dir/groups/*/summaries/*.md` 和 `global/summaries/*.md` |
| `GET /api/summary` | `_handle_summary` | 查询参数 `group_id`（可空）+ `date`，返回文件内容 |

数据构建逻辑抽离为 `events_data()`、`graph_data()`、`summaries_data()`、`summary_content()` 四个方法，HTTP handler 仅做参数解析和 JSON 包装，使测试可绕过 HTTP 层直接调用。`start()` 使用 `web.AppRunner` + `web.TCPSite`，`stop()` 调用 `runner.cleanup()` 优雅关闭。

**`/api/events` 多群组聚合逻辑**

当 `group_id` 为空时，先调用 `event_repo.list_group_ids()` 获取所有活跃 group，然后对每个 group 按 `per_group = limit // len(group_ids)` 分配配额并合并，最终截断到 `limit`，避免单一大群独占配额。

**JSON 序列化格式**

- `event_to_dict`：时间戳用 `datetime.fromtimestamp(..., timezone.utc).isoformat()` 转为 ISO 8601（vis-timeline 原生支持）；salience 保留 3 位小数
- `persona_to_node`：包裹在 `{"data": {...}}` 内，匹配 Cytoscape.js elements 格式
- `impression_to_edge`：`id = "{observer}--{subject}--{scope}"`，`line-color` 映射到 `affect`，`width` 映射到 `intensity`

**单页前端（`static/index.html`）**

CSS Grid 三列等宽布局，`height: calc(100vh - header)`，每个面板内部 `display: flex; flex-direction: column` 确保内容区占满剩余高度。

- **vis-timeline**：`tlItems = new vis.DataSet(...)` 将事件数组装入数据集；`highlightEvents(ids)` 遍历数据集更新 `className` 为 `"highlighted"`（红色高亮），并调用 `timeline.focus(ids)` 滚动定位
- **Cytoscape.js**：`mapData(affect, -1, 1, #f44336, #4caf50)` 将情感值映射为边颜色（红=负面，绿=正面）；`mapData(intensity, 0, 1, 1, 5)` 映射为边宽度；布局使用 `cose`（力导向，适合中小规模图）
- **跨面板联动**：Cytoscape `tap edge` 事件读取 `evidence_event_ids`，调用 `highlightEvents()` 在事件流面板高亮对应事件
- **Summarised Memory**：`marked.parse(content)` 将 Markdown 渲染为 HTML；列表项点击触发 `loadSummary()` 发起 `/api/summary` 请求；首次加载自动渲染最新摘要

**测试策略**

使用 `aiohttp.test_utils.TestClient(TestServer(srv.app))` 作为异步上下文管理器，无需 `pytest-aiohttp`，与现有 `pytest-asyncio` auto 模式兼容。序列化函数和数据构建方法作为纯函数/async 方法单独测试，HTTP 集成测试只覆盖状态码和关键字段。

---

## Phase 10 — Markdown 反向同步（文件监听 + 高权重回写 DB）

**完成日期：** 2026-05-03  
**测试数量：** 26 个（parser 12 + watcher 5 + syncer 9）  
**累计测试：** 286 个，全部通过

### 新增 / 修改文件

| 文件 | 变更 |
|------|------|
| `core/sync/__init__.py` | 空包初始化 |
| `core/sync/watcher.py` | `FileWatcher`：asyncio 轮询，`register/unregister/start/stop/_check_once` |
| `core/sync/parser.py` | `parse_impressions_md(content, subject_uid) -> list[Impression]` |
| `core/sync/syncer.py` | `ReverseSyncer`：注册文件、`_on_change()`、置信度下限应用 |
| `core/projector/templates/persona_impressions.md.j2` | 修复：`{{ imp.observer_uid[:8] }}` → `{{ imp.observer_uid }}`（完整 uid，反向解析需要） |
| `main.py` | 导入 `FileWatcher`、`ReverseSyncer`；`initialize()` 创建并启动监听器；`terminate()` 优先停止监听器 |
| `tests/test_sync.py` | 26 个测试覆盖解析、监听、同步三个子系统 |

### 技术实现

**模板修复（`persona_impressions.md.j2`）**

原模板使用 `{{ imp.observer_uid[:8] }}` 截断观察者 uid，反向解析时无法还原完整主键 `(observer_uid, subject_uid, scope)` 导致 upsert 出错。Phase 10 首要操作即移除截断，保持 uid 完整输出。这是一个向后不兼容的格式变更——旧的已渲染文件若被同步将以截断 uid 写回，因此文件只在下次投影周期重新生成后才可被正确同步。

**FileWatcher（`core/sync/watcher.py`）**

基于 `asyncio.create_task` 的轮询监听器，不依赖平台文件系统事件（`inotify`/`FSEvents`/`ReadDirectoryChangesW`），保证跨平台一致性：

- 内部状态：`dict[Path, (last_mtime: float, callback)]`；`register()` 初始化 mtime 快照（文件不存在则记 0.0）
- `_check_once()` 遍历所有注册路径，调用 `path.stat().st_mtime`，值变化则触发回调并更新快照；返回变化路径列表供测试断言
- 回调异常在 `_check_once()` 内部被 `logger.exception` 捕获，不中断监听循环
- `stop()` 取消后台 task，等待 `CancelledError` 确保 asyncio 事件循环干净退出
- 默认轮询间隔 30 s（反向同步不要求低延迟，过短则增加磁盘 I/O）

**parse_impressions_md（`core/sync/parser.py`）**

纯函数，无 I/O，使用正则表达式解析 `persona_impressions.md.j2` 的固定输出格式：

| 字段 | 正则提取逻辑 |
|------|-------------|
| `observer_uid`、`scope` | 标题行 `## 来自 \`{uid}\` 的印象（范围：{scope}）` 一次捕获两组 |
| `relation_type` | 表格行 `\| 关系类型 \| ... \|` 提取第二列并 `.strip()` |
| `affect` | 表格行提取全角括号内的带符号浮点数 `（[+-]?d+.d+）` |
| `intensity`、`confidence` | 整数百分比 `\d+%` 除以 100 |
| `evidence_event_ids` | `**依据事件：** e1, e2` 按逗号分割 |

解析步骤：先用 `_SECTION_RE`（MULTILINE）找出所有标题匹配，再逐段提取；任一必填字段缺失则静默跳过该块，保证解析健壮性。`affect`/`intensity`/`confidence` 在传入 `Impression()` 构造函数之前被 `max/min` 显式夹紧到合法范围，防止用户手动编辑越界触发 `__post_init__` ValueError。`last_reinforced_at` 设为 `time.time()`（文件刚被修改，当前时间即为最近强化时刻）。

**ReverseSyncer（`core/sync/syncer.py`）**

将 `FileWatcher` 与 `ImpressionRepository` 桥接：

- `register_all()`：遍历 `data_dir/personas/*/IMPRESSIONS.md`，逐文件注册回调；返回注册数量
- `register_persona(uid)`：单个 persona 投影完成后立即注册，无需等待下一次 `register_all()`
- `_on_change(path, subject_uid)`：读取文件 → 调用 `parse_impressions_md` → 对每条 `Impression` 执行置信度下限：若解析到的置信度 < 0.9，则以 0.9 替换；最终调用 `impression_repo.upsert()`
- **用户编辑置信度下限（0.9）**：LLM 提取的置信度通常在 0.6–0.8，用户主动编辑的事实可信度天然更高。下限 0.9 确保手动编辑在后续 `run_impression_aggregation` 的加权合并中具有更强的先验权重，不会被 LLM 推理结果轻易覆盖。若用户自行填写 95%，则保留 0.95（下限只升不降）

**main.py 集成**

在 `initialize()` 末尾，WebUI 启动后：

1. 创建 `FileWatcher()` 和 `ReverseSyncer(...)`
2. 调用 `await syncer.register_all()` 初始化所有已有文件的 mtime 快照
3. 调用 `await watcher.start()` 启动后台轮询 task

投影任务 `"projection"` 的 lambda 改为 `_projection_and_register()` 异步函数：先 `render_all_personas()`，再 `syncer.register_all()` 确保新生成的 IMPRESSIONS.md 也被监控。

`terminate()` 最先停止 `_watcher`（取消后台 task），再关闭 WebUI、调度器和数据库，保证不会有已取消的回调在 DB 关闭后访问仓储。

---

## Phase 11 — WebUI 重构（独立 `web/` 模块 + 二级认证 + 第三方面板挂载）

**完成日期：** 2026-05-03  
**测试数量：** 39 个（test_webui 重构后；累计 302 个，2 skip 不变）

### 设计动机

Phase 9 的 WebUI 实现位于 `core/webui/`，与数据引擎位于同一命名空间，但其生命周期、依赖方向、扩展需求都与 `core/` 不同：

1. **依赖反转**：WebUI 单向依赖 `core/`（domain + repository），反向依赖被禁止
2. **可关闭**：用户可通过 `webui_enabled=false` 完全禁用 WebUI 而不影响数据采集和检索
3. **可扩展**：未来需要支持其他 AstrBot 插件挂载新面板到统一 WebUI（插件生态联动）
4. **认证缺失**：原实现无密码保护，公开端口即任意访问

将 WebUI 提升为根级 `web/` 模块从架构层面表达"它是表现/管理层而非数据引擎组件"。

### 文件变动

| 文件 | 操作 |
|------|------|
| `web/__init__.py` | 新建（空包标记）|
| `web/server.py` | 新建（接管原 `core/webui/server.py` 实现，加 auth + registry + 新路由）|
| `web/auth.py` | 新建（`AuthManager` + `AuthState` + `_hash_password` / `_verify_password`）|
| `web/registry.py` | 新建（`PanelRegistry` + `PanelManifest` + `PanelRoute`）|
| `web/static/index.html` | 重写（玻璃拟态 + 邻域高亮 + 密度滑块 + 登录页 + sudo 模式）|
| `web/README.md` | 新建（用户向文档：API 参考、扩展指南）|
| `core/webui/server.py` | 清空（仅留迁移说明注释）|
| `main.py` | 导入路径 `core.webui.server` → `web.server`；接入 `task_runner` 和 auth 配置；新增 `webui_registry` 属性对外暴露 |
| `_conf_schema.json` | 新增 `webui_auth_enabled`、`webui_session_hours`、`webui_sudo_minutes` |
| `requirements.txt` | 新增 `bcrypt>=4.0` |
| `tests/test_webui.py` | 重写（39 个用例：序列化 5、数据构建 11、HTTP API 6、auth 7、PanelRegistry 4、AuthManager 单测 6）|

### 技术实现

**AuthManager（`web/auth.py`）**

bcrypt 通过 `try import` 软依赖：未安装时降级为 `sha256$<hex>` 格式（带 warning），保证开发期 / 离线测试可用。密码文件 `data_dir/.webui_password` 写入后调用 `chmod 0o600`（失败则忽略，Windows 跳过）。

会话存储为进程内 `dict[str, _Session]`，重启失效；session token 由 `secrets.token_urlsafe(32)` 生成。`check(token)` 检查总时长（默认 24h，超时即删除并返回未认证）；同时计算 `is_sudo` 和 `sudo_remaining_seconds`，前端用此倒计时显示。

**PanelRegistry（`web/registry.py`）**

`PanelManifest` 是纯数据 dataclass，描述一个面板的元信息（plugin_id、panel_id、title、icon、permission 等）。`PanelRoute` 描述一个 HTTP 路由（method、path、handler、permission）。`PanelRegistry.register(manifest, routes)` 同时存入 `_panels` 和 `_routes` 两个 dict，前者供 `/api/panels` 列出给前端，后者由 `WebuiServer._build_app()` 在初始化时注入到 aiohttp router。

`on_change(callback)` 提供变更通知，但 v1 不使用——前端轮询 `/api/panels` 已经够用。

**WebuiServer auth 中间件（`web/server.py`）**

使用 `_wrap(level, handler)` 工厂函数生成包装版 handler：

```
- public：任何请求直接放行
- auth：检查 cookie 中 session token；无效返回 401
- sudo：检查 token 有效且 sudo_until > now；否则返回 403
```

`auth_enabled=False` 时 `_wrap` 全部放行，便于测试和单机部署。

**任务触发器解耦**

WebuiServer 不直接持有 `TaskScheduler` 引用，而是接受一个 `task_runner: Callable[[str], Awaitable[bool]]`。`main.py` 注入 `self._scheduler.run_now`。这样 WebuiServer 可以在测试中独立构造（传 None → 触发任务 API 返回 503）。

**前端重构（`web/static/index.html`）**

整体改用 CSS 变量主题系统（`--bg`, `--accent` 等）+ `[data-theme="light"]` 切换，localStorage 持久化主题选择。

**登录覆盖层**：固定全屏 `#login-overlay`，根据 `password_set` 状态切换为登录或首次设置模式（后者要求两次输入一致）。`hideLogin()` 将 `#app` 的 `display: none` 改为 `flex`，避免认证完成前主界面闪烁。

**事件流密度滑块**：`State.rawEvents` 全量缓存，每次拖动滑块在客户端按 salience 降序取 top-N 重渲染 vis.DataSet。借鉴 Memorix 的 saliency-density 模式但简化为客户端实现（避免增加后端 API 复杂度）。

**关系图邻域高亮**：Cytoscape 的 `node.closedNeighborhood()` 返回节点本身 + 一跳邻居 + 邻居间的边；其余元素加 `.dim` class（opacity 0.15）。点击边时类似处理，并将 `evidence_event_ids` 传递给 `highlightEvents()` 在事件流面板同步高亮。LOD 通过 `cy.on('zoom')` 监听缩放，zoom < 0.6 时把节点 `font-size` 设为 0 隐藏标签。

**详情侧栏（玻璃拟态）**：`#detail-panel` 固定在右上角，`backdrop-filter: blur(20px)` + `slideIn` 关键帧动画。点击节点/事件/边时填充对应信息，带 `×` 关闭按钮。

**Sudo UI**：顶部按钮根据 `State.sudo` 状态切换文本和颜色（`.sudo-active` 黄底）；每 30s 轮询 `/api/auth/status` 自动同步剩余时间。

**设置 modal**：包含密码修改、5 个后台任务的手动触发按钮（每个 POST `/api/admin/run_task`）、已注册第三方面板列表。Sudo 检查在前端先做（按钮 disable）+ 后端再做（中间件 403），双层保护。

### 测试更新

`tests/test_webui.py` 重构后 39 个用例：

- **序列化（5）**：`event_to_dict` / `persona_to_node` / `impression_to_edge` 字段断言
- **数据构建（11）**：`events_data` / `graph_data` / `summaries_data` / `summary_content` / `stats_data` 各场景
- **HTTP API（6）**：`/api/events` / `/api/graph` / `/api/summary` / `/` / `/api/panels` 等核心路由的状态码和响应结构
- **认证流（7）**：setup / login / sudo / 改密 / 401 / 403 / 任务运行
- **PanelRegistry（4）+ AuthManager（6）**：纯单测，覆盖注册、注销、路由暴露、密码生命周期、session 管理

`_server` 工厂函数默认 `auth_enabled=False` 简化测试；需要测 auth 时显式打开。`TestClient` 自动管理 cookie，登录后续请求无需手动添加 header。

### 插件生态接口

`EnhancedMemoryPlugin.webui_registry` 属性对外暴露 `PanelRegistry` 实例，文档化用法：

```python
em = self.context.get_registered_star("astrbot_plugin_enhanced_memory")
if em and em.webui_registry:
    em.webui_registry.register(PanelManifest(...), routes=[...])
```

这是本插件作为"WebUI 基座"的对外契约。当 `webui_enabled=false` 时 `webui_registry` 返回 `None`，调用方需做空检查（已在文档示例中体现）。
