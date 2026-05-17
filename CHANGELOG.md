# CHANGELOG

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

