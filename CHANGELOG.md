# CHANGELOG

## [v0.11.1] — 2026-05-17

### ipc_orientation 字段统一化

**Refactor — 将两条写入路径统一为 8 个英文 key**

- `classify_octant` 返回值从硬编码中文改为英文 key（`affinity` / `active` / `dominant` / `arrogant` / `cold` / `withdrawn` / `submissive` / `deferential`）
- LLM 提取 prompt（3 处）约束列表同步更新为英文 key
- `i18n.py` 的 IPC 标签 key 从 `ipc.亲和` 等改为 `ipc.affinity` 等，翻译值不变（zh/en/ja 均已更新）
- Jinja2 投影模板通过 `get_string("ipc." + imp.ipc_orientation)` 输出本地化显示名
- `parser.py` 新增 `_ORIENTATION_NORMALIZE` 映射，将文件中读取到的中文显示名/历史变体统一归一化为英文 key，保证读写双向兼容
- 前端 `getLocalizedOrientation` 重写：主路径直接映射英文 key，同时保留中文历史变体的 fallback
- 前端关系图边标签通过 `getLocalizedOrientation` 翻译，不再裸显原始字段值

**Migration**

- 新增 `migrations/010_normalize_ipc_orientation.sql`：将数据库中所有历史中文值及 LLM 变体映射为英文 key，未知值 fallback 为 `affinity`


## [v0.11.0] — 2026-05-17

### 群组/私聊分域关系图

**Feature — 关系图按群组/私聊分域展示**

- WebUI 关系图页面现在按群组和私聊分别显示独立的关系卡片，而非仅展示全局视图
- 后端 `graph_data()` 将 `group_id=None`（私聊）映射为 `"__private__"` 键，保证 JSON 安全
- 前端 `buildGroupCards()` 实现 scope 感知的边过滤：
  - 群聊卡片只显示 `scope === group_id` 的印象关系
  - 私聊卡片（`__private__`）只显示 `scope === "global"` 的印象关系
- 私聊卡片显示标识 "私聊 / DM"，全局视图（无群组数据时 fallback）显示 "全局"
- 新增 `GROUP_ID_GLOBAL` 和 `GROUP_ID_PRIVATE` 常量统一管理特殊键值

**Tests**

- 新增 `tests/test_graph_scope.py`：涵盖 `__private__` 键映射、群组键映射、混合场景及边 scope 字段验证（共 8 个测试）


## [v0.10.15] — 2026-05-17

### 对话轮数进度追踪

**Feature — `/mrm status` 增强**

- `/mrm status` 现在会显示当前会话的对话轮数进度（`当前 n / 总 m 轮`）及已累积消息数
- 同步展示记忆库统计：活跃 event 数、人格数、印象数
- 展示平均响应时间（来自 perf tracker）
- `CommandManager` 新增 `impression_repo` 和 `summary_trigger_rounds` 参数

**Feature — WebUI Stats 页面新增活跃会话进度卡片**

- Stats 页最下方新增 "活跃会话轮数进度" 卡片，列出所有活跃 session 的进度条
- 进度条颜色随进度变化（正常/黄色警告/红色接近触发）
- 显示群聊/私聊标识和 session 短 ID
- 支持中/英/日三语言

**Internal**

- `get_stats()` 新增 `context_manager` 和 `summary_trigger_rounds` 参数，返回 `active_sessions` 和 `summary_trigger_rounds` 字段
- `PluginRoutes` / `PluginInitializer` 传入对应依赖
- 新增 `tests/test_session_progress.py`（8 个测试用例，覆盖 get_stats active_sessions、CommandManager.status 轮数显示与统计行）


## [v0.10.14] — 2026-05-16

### napcat 事件异常 + SQLite 并发事务嵌套修复

**Bug Fix — napcat / OneBot v11 适配**

- 修复事件标题 "（无内容）"：`fallback_extraction` 改为找首个非空消息文本，避免首条消息仅含 CQ 段被剥离后触发占位
- 新增消息规范化层（`core/adapters/message_normalizer.py`）：在 adapter 边界统一处理 CQ 码与 napcat 显示名残留
  - `[CQ:at,...]` → `@用户`；图片/表情/语音/视频/卡片各有占位符；`[CQ:reply,...]` 等删除
  - `@昵称(QQ号)` → `@昵称`，保留语义、剥离数字 ID
  - sender display name 同样剥离尾部 `(数字)`
- fallback 标签过滤：跳过纯数字、`@`/`#`/`http(s)`/`qq=` 前缀、超长 token 与常见虚词，防止 `#@卢比鹏(1783088492)` 这类污染再到达 UI / 向量索引
- LLM 提示词重名消歧：同一窗口里同名不同 uid 自动加 `#2`/`#3` 后缀
- LLM fallback 触发可观测性：写结构化 warning（reason=provider_none/timeout/exception/parse_error），节流避免高活跃群刷屏

**Bug Fix — 数据库**

- 修复 `cannot start a transaction within a transaction`：单一共享 `aiosqlite.Connection` + 多并发协程导致 `BEGIN IMMEDIATE` 嵌套报错
- 在 connection 上挂 `asyncio.Lock`（三个 repo 共享），引入 `_txn` 上下文管理器串行化所有写事务；读操作不变

**Tests**

- 新增 `tests/test_message_normalizer.py`（CQ 段规范化 22 用例）
- 新增 `tests/test_sqlite_concurrency.py`（50 并发 upsert、跨 repo 并发、rollback 后续事务）
- 扩展 `tests/test_extractor.py`（首条非空、tag 防污染、重名消歧）
- 扩展 `tests/test_message_router.py`（端到端验证规范化文本不再带 CQ/QQ 号）


## [v0.10.13] — 2026-05-16

### 核心引擎日志优化与系统功能升级

**Bug Fixes**

- **静默本地向量模型进度条** (`core/embedding/encoder.py`)
  - 显式关闭 `sentence-transformers` 的 `show_progress_bar` 选项，解决 AstrBot 日志中频繁出现 `Batches: 100%` 导致日志污染的问题。

**Features**

- **新增记忆生成机制**：增加「总结触发轮次」配置（`summary_trigger_rounds`），用户可自定义每隔多少轮对话触发一次 LLM 总结。
- **自动备份系统**：新增每日自动备份机制，支持自定义备份保留天数（`backup_retention_days`），确保数据库安全。
- **配置项全面开放**：
    - **VCM**：支持配置单会话历史消息上限及批量清理数量。
    - **检索**：支持独立的主动检索上限、RRF 融合常数、重要性权重，以及注入位置（system/user/fake_tool）切换。
    - **Embedding**：支持精细化配置读取批量、API 请求批量、并发数及各项时间间隔。
    - **衰减**：支持自定义每周期重要度衰减率（`decay_lambda`）。
- **WebUI 配置页升级**：重构了「插件配置」页面，将上述所有新参数及原先仅限后端配置的项目全部暴露给用户。

**Tests**

- 新增 `tests/test_new_configs.py`，完整覆盖了新增配置项的解析逻辑与「总结触发轮次」的边界检测。


## [v0.10.12] — 2026-05-16

### 事件流页面体验优化与 Bug 修复

**Bug Fixes**

- 优化事件节点 Hover 判定：增大热区面积（20px -> 24px），并调整悬浮清理延迟（200ms），解决 Tooltip 闪烁及难以触发的问题。
- 修正统计面板图标：将「已锁定」统计项的图标从 `Zap` 改为中性色的 `Lock`。

**UI/UX Improvements**

- 详细面板自适应：右侧详细面板现在支持自适应宽度（320px ~ 500px），在宽屏下提供更好的视觉体验。
- 显著度分布图表主题适配：图表颜色现已适配 shadcn 主题色，使用 `primary` 变量及其透明度梯度。
- 增强内容间距：优化了详细面板内卡片的 Padding 与自适应表现。

**Refactor**

- 统一 WebUI 筛选组件：将「事件流」页面的紧凑型标签和日期筛选工具栏提取为通用的 `FilterBar` 组件。
- 替换「关系图」和「信息库」原有的筛选栏，实现全站视觉一致性。
- 移除冗余的 `TagFilter` 组件，优化前端代码结构。


## [v0.10.10] — 2026-05-15

### WebUI 登录页视觉升级

**Features**

- 全新编辑风格登录页：左右分栏布局、丝线背景动画、右下角悬浮设置控件
- 字体统一为 PT Serif（400/700），品牌标题 `π` 与 `.` 使用 primary color
- 登录页版本号直接读取后端 `/api/auth/status`，不再硬编码
- `run_webui_dev.py` 新增 `--auth` 参数，可本地预览登录页
- 「忘记密码」Hover 提示，引导用户查看 AstrBot Token 或插件配置

**Bug Fix**

- 补全 `api.ts` 缺失的 `listArchived` / `archive` / `unarchive` 方法，修复构建报错

完整更新日志见 [docs/CHANGELOG.md](docs/CHANGELOG.md)。

