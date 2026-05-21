# 变更日志

## [v0.15.0] - 2026-05-20

### 记忆反馈回路 & Soul Layer 信号驱动重构

#### Event Stream 可视化重构

- `/events` 默认视图从旧的多列 `EventTimeline` 改为 spindle grid：按群组 / 私聊聚合事件，展示 knot 数、锁定数、归档数、高显著度统计、热门标签和 mini-thread 预览。
- 点击 spindle 后进入单组 thread view：只渲染当前群组事件，保留时间间隔聚类、日期分隔、会话括号、事件卡片、编辑 / 删除 / 归档入口和右侧详情面板。
- 从关系图跳转事件的 `em_focus_event` / `em_highlight_events` 链路保持可用：进入 `/events` 会自动展开对应 spindle 并高亮 knot。
- `DetailPanel` 保持对外 props 不变，内部更新为更贴合 Moirai 视觉的丝线装饰、KNOT 标识、空态统计与分组 accent。
- 新增 `events-aggregator.ts` 与 `session-clustering.ts`，前端派生 spindle 数据和 thread session layout；后端 API、`ApiEvent` 数据形状、全局 store 与事件 dialogs 均未改动。
- 新增 silk/thread/knot 动画，并支持 `prefers-reduced-motion` 收敛；i18n 补充 spindle / knot / unspool 等三语文案。
- 修复 SVG knot 焦点矩形框问题，并将选中 / 聚焦指示调整为以锚点为中心的莫比乌斯轨道运动效果。
- 前端结构测试更新至新架构，静态产物已同步到 `pages/moirai/`。

#### AstrBot 配置归组修复

- 修复 WebUI 保存配置时把 `embedding_provider`、`llm_concurrency`、`retrieval_top_k`、`webui_enabled` 等 schema 字段写入 root config 的问题。
- 配置保存现在会按 `_conf_schema.json` 自动归组后再写入本地配置并同步 AstrBot live config，避免 AstrBot 原生配置页底部出现未分类设置。
- WebUI 配置读取兼容旧 flat 保存和新的 grouped 配置文档。

#### 记忆反馈回路（Feedback Loop）

- `Event` 模型新增 `access_count: int` 字段，记录每条记忆被注入给 LLM 的累计次数。
- 新增数据库迁移 `014_access_count.sql`，为存量数据补全该字段（默认 0）。
- `RecallManager` 新增 `_last_injected_ids` 缓存：每次 `recall_and_inject` 成功注入后，将本轮 event_ids 记录至 `session_id → [event_ids]`，供 LLM 回复后的 bump 使用。
- 新增 `RecallManager.get_last_injected_ids(session_id)`：读取最近一次注入的 event ID 列表。
- 新增 `RecallManager.bump_salience_on_use(event_ids, response_text, boost)`：LLM 回复后，对注入的记忆执行 salience 提升、`last_accessed_at` 更新、`access_count` 自增。内置 **token overlap 过滤**：仅 `chat_content_tags` 中有词出现在回复文本中的事件才触发 boost；无 tags 的事件默认 bump（无过滤依据）。
- `EventRepository` 接口新增 `increment_access_count(event_id)`，`SQLiteEventRepository` 与 `InMemoryEventRepository` 均已实现。

#### 访问加权衰减（Access-Weighted Decay）

- `core/tasks/decay.py` 新增 `run_access_weighted_decay`：衰减速率按 `λ_eff = λ_base / (1 + access_count × 0.1)` 计算，高频访问的记忆自然衰减更慢，从不被召回的记忆正常衰减直至归档。

#### Soul Layer 信号驱动重构

- `soul_state.py` 新增 `update_from_signals` 函数，四个轴改为由真实信号驱动，不再是静态衰减的空转旋钮：
  - `recall_depth` ← 召回事件数 × 平均 salience（认知投入度）
  - `expression_desire` ← IPC benevolence 均值（关系温度 → 表达欲）
  - `impression_depth` ← relation_count × power 加权（社交投入度）
  - `creativity` ← 事件时间跨度 + EPISODE/NARRATIVE 混合度（记忆广度 → 发散性）
- `RecallManager` soul state 更新块从 `apply_decay + 手写 SoulState(...)` 改为调用 `update_from_signals`，IPC 信号从已预取的 `relation_debug` 中零成本提取。

#### Bug Fix

- 修复 `recall_and_inject` 中 `asyncio.gather` 返回值的嵌套解构 bug：`relation_debug` 之前因 `isinstance(relation_segment, tuple)` 判断在解构后恒为 False，导致 impression 数据从未传入 soul state 及 injection debug，现已改为对原始 `relation_result` 做类型检查。

## [v0.14.1] - 2026-05-20

### 配置文案与设置页整理

- AstrBot 原生设置页顶部说明从「基础设置」调整为「基础配置说明」，并将「新手」统一改为「基础用户」。
- WebUI 配置档位文案统一为「基础 / 进阶 / 专家」，同步中 / 日 / 英三语与快速设置说明。
- WebUI 配置页新增各分组中基础 / 进阶 / 专家项数量提示；设置页语言、主题、第三方面板卡片视觉整理。

## [v0.14.0] - 2026-05-20

### WebUI 配置体验重构

- 插件配置页从 12 个平铺 section 重组为 6 个父类（常规 / 信息流 / 事件流 / 关系图 / 摘要记忆 / 数据库维护），对齐「三轴记忆」心智模型；原 section 作为子分组卡片，TOC 改为两级导航。
- `_conf_schema.json` 每个字段的 `level` 由 `basic|advanced` 扩展为 `basic|advanced|expert`，全部 102 个字段重新打标。配置页用「基础 / 进阶 / 专家」三段切换替代原二元开关，基础档只保留功能主开关。
- Soul 情绪四维标记为实验性（schema `experimental: true`），配置页与快速设置向导显示「实验性」徽章，默认关闭。
- 配置页工具栏新增全局搜索框，按字段 key / 标签 / 提示跨全部六大类过滤，命中结果平铺展示并带「父类 / 子分组」面包屑。
- 新增快速设置向导：四步引导（进入 Sudo → 功能选择 → 预设参数包 → 应用并跳转配置页）。首次进入 WebUI 时在 Persona 选择之后自动弹出，配置页头部也有常驻「快速设置」入口。三套使用场景预设：「仅聊天 + 记忆优化」/「均衡社交记忆」（推荐）/「完整 / 研究」。
- 新增配置 `webui_auto_restart_on_save`（默认开启）：在 WebUI 保存配置会通过 AstrBot 插件管理器自动重载本插件，使新配置立即生效。保存响应返回 `restarting` 标志；前端显示「正在重启插件」遮罩并轮询登录态，WebUI 恢复后自动刷新（约 1–3 秒）。重载作为延迟后台任务执行，保证 HTTP 响应先返回。

## [v0.13.2] - 2026-05-20

### Persona 数据归库固化

- 新增 `bot_persona_name_override`（relation 配置组）：非空时所有事件 / 印象强制归入该 `bot_persona_name` 桶，绕过自动解析 —— 同一性格跨多平台（如 QQ 与 Discord）运行时进入同一数据集的确定性「锁定」。
- `_resolve_persona_name` 在入口短路返回 override，使 bot 回复、原始消息、窗口全部携带统一名（SSOT）。
- `EventExtractor` 在事件 `bot_persona_name` 最终确定处应用 override，覆盖无 bot 消息的 0-bot 窗口。
- 加固 `resolve_bot_persona_context`：不再用 `next(...)` 任取第一个 `internal`-bound persona；存在多个时按 `last_active_at` 确定性选择并记录歧义日志。该函数现仅用于生成 prompt persona 描述，不再作为归桶键来源。无法解析时事件落 `NULL` 遗留桶，不再出现随机 / 账号派生名。
- 新增只读诊断脚本 `tools/diagnose_persona_buckets.py`，打印 `bot_persona_name` 分桶计数与内部 persona 行。已产生的错桶数据可经 WebUI「Persona 归属管理」(`merge_bot_persona`) 合并。

## [v0.13.1] - 2026-05-20

### 手动摘要与关系修复

- 移除未使用的 `summary_word_limit` 配置项；字数上限固定为内部常量 300 字。
- 修复 `regenerate_single_summary`：新增并透传 `summary_config`、`llm_manager`、`encoder`，使手动重新生成遵循用户配置、走 LLM 并发控制，并保持数据库中的 NARRATIVE 事件与 Markdown 文件一致。
- 修复 `plugin_routes.py` 与 `server.py` 中的 `_handle_regenerate_summary`：向任务函数传入由 `PluginConfig` 实时派生的 `summary_config`、`llm_manager`、`encoder`。
- 修复 `reanalyze_impressions_llm`：移除无用的 `extractor_config` 参数；新增可选 `persona_repo`，在 LLM prompt 中用显示名替代 UID。
- 修复 `_handle_reanalyze_impressions_guarded`（LLM 分支）：传入 `persona_repo`，使分析 prompt 中出现参与者显示名。

## [v0.13.0] - 2026-05-20

### 原始消息持久化

- 新增短期 `raw_messages` / `event_messages` 存储，保留详细的消息证据。
- 新增原始消息异步批量写入、事件-消息链接、基于原始细节的重新提取、召回细节补全，以及原始数据保留期清理。
- 新增配置 `raw_message_retention_days`，默认 14 天，硬限制在 1–14 天。

## [v0.12.14] - 2026-05-20

### 缓存工具统一 & 无界字典修复

- 新增 `core/utils/cache.py`：泛型有界 LRU 缓存 `_LRUCache`、多平行字典统一驱逐框架 `BoundedKeysMixin`。
- 修复两处无界字典：`IdentityResolver._cache` 改为 `_LRUCache(maxsize=2000)`；`BigFiveBuffer` 继承 `BoundedKeysMixin(maxkeys=500)`，超限时统一清理 5 个平行字典并取消进行中的评分任务。

## [v0.12.13] - 2026-05-20

### 编码器性能优化 & 默认配置调整

- `encoder.py` 新增 `_normalise(text)`：折叠空白、截断至 200 字符，作为统一 LRU 缓存键与推理输入，使等价查询合并。
- `SentenceTransformerEncoder` 使用独立单线程 `ThreadPoolExecutor`，保持模型权重常驻同一线程 CPU 缓存。
- `markdown_projection_enabled` 默认值改为 `false`、level 降为 `advanced`。

## [v0.12.12] - 2026-05-19

### 性能优化（高优先级批次）

- SQLite 新增 PRAGMA：`mmap_size=256MB`、`temp_store=MEMORY`、`wal_autocheckpoint=500`；新增迁移 `012_perf_composite_index.sql` 复合索引 `(status, event_type, group_id)`。
- `search_vector` 热路径剥离 `interaction_flow` 大 JSON，降低向量检索 I/O。
- 向量嵌入接入 128 条 LRU 缓存；`RecallManager` 统一编码一次查询并复用，消除重复推理。
- `RecallManager._soul_states` 新增 TTL 驱逐，新增配置 `soul_states_ttl_hours`（默认 24h），修复多群组长期运行的内存泄漏。

完整变更记录维护在 [`docs/CHANGELOG.md`](docs/CHANGELOG.md)。

根目录此文件保留，是为兼容仅读取插件根目录 `CHANGELOG.md` 的 AstrBot / 插件管理器。
