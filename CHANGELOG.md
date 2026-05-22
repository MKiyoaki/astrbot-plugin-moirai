# 变更日志

## [v0.16.3] - 2026-05-22

### 事件提取效率、召回质量与摘要事件绑定

#### 实时管线与召回效率

- `run_realtime_dev.py` 进一步对齐实际插件路径：LLM 提取模式下默认仍加载 retrieval/indexing encoder，能够同时验证事件提取质量与向量召回质量。
- 本地 embedding 默认节流从 `5000ms / 5000ms` 调整为 `50ms / 0ms`，避免本地 encoder 召回固定等待约 5 秒；远端 embedding API 用户仍可在高级配置中调大间隔以规避限流。
- realtime dev 新增/完善事件质量、未链接 raw message、召回 benchmark、细分性能指标输出，用于对比 LLM / encoder 模式。
- 召回 no-evidence guard、query term 抽取和 tag/category bridge 继续收敛，避免“无原神证据”类查询注入无关事件，同时保留 Gariton / 明日方舟 / 大五人格等有证据查询的命中能力。

#### Tag 层级与事件质量

- 保留具体 `chat_content_tags`，新增派生式 `tag_categories`：每个具体 tag 对应一个预设母类 category，用于 WebUI 展示和召回桥接。
- tag/category 目前不落库，属于动态派生字段；后续若支持用户手动修改母类或保存具体映射，将通过 taxonomy version + relink/reindex 机制处理。
- LLM 单事件完整窗口覆盖、JSON repair、topic/tag sanitizer 和事件诊断日志继续保留，减少碎片事件、低质量 fallback event 与无效 tag。

#### 摘要 [事件列表] 绑定 Event Stream

- 摘要 `[事件列表]` 从纯文本快照升级为 event_id 驱动的可同步区块：后端读取摘要时解析 `[event_id8]`，按事件库最新 topic 重建事件列表并写回 Markdown。
- 事件在 WebUI 中手动编辑 title 或调用 LLM reextract 后，会主动刷新所有引用该 event_id 的摘要文件，使摘要事件列表实时反映并固化最新标题。
- `/api/summary` 与 `/api/summary/regenerate` 新增 `linked_events` 结构化 metadata，Summary UI 可直接渲染可点击事件链。
- Summary UI 中点击事件列表项会跳转到 Event Stream 并聚焦对应事件；standalone WebUI 与 AstrBot plugin routes 均接入同一套 core helper，避免运行环境差异。

#### 验证

- 新增 summary event-link 同步单测，覆盖 stale title 刷新、文件持久化、standalone WebUI API 和 AstrBot plugin routes。
- 后端与前端结构测试、typecheck、构建和静态资源同步均已执行。

## [v0.16.2] - 2026-05-21

### Soul Layer 增强 & 注入架构优化

#### Soul Layer 行为指令化

- `format_soul_for_prompt` 输出从抽象数值描述（`表达欲 +5.0/20（偏高）`）改为面向 LLM 的具体行为指令。四个维度各有强弱两档文本，例如 `expression_desire > 7` 输出"表达欲强，可主动展开话题，回复可以详细"；以 ±0.5 为强弱分界，近零维度依然跳过不注入。
- Creativity 信号重新设计：原公式单纯依赖事件时间跨度（满格需 30 天，最大 delta 0.8），实际几乎不变化。新公式叠加三路信号：时间跨度（7 天满格，贡献 2.0）+ 召回事件显著度方差（高低对比贡献 1.5）+ 召回事件标签多样性（5 个不同 tag 贡献 1.5），最大 delta 从 0.8 提升至 5.0，日常对话中 creativity 可稳定维持在可见范围。

#### Soul 注入块与记忆块分离（方案 B）

- 新增常量 `SOUL_INJECTION_HEADER / FOOTER`（`<!-- EM:SOUL:START/END -->`），Soul 状态拥有独立的注入块标记，与记忆块的 `<!-- EM:MEMORY:START/END -->` 完全分离。
- **Soul 块始终注入 `system_prompt`**，不受 `injection_position` 配置影响（行为指令属于角色底层设定，不应随用户消息位置飘移）。
- 记忆块（事件 + 人格摘要 + 社交印象）继续遵循 `injection_position` 配置。
- `clear_previous_injection` 扩展，在清除 MEMORY 标记后额外扫描并清除 SOUL 标记，两处字段均做防御性清除。
- 新增 `_SOUL_INJECTION_RE` 正则；新增测试文件 `tests/backend/test_soul_injection_separation.py`（12 个测试，覆盖标记隔离、位置固定、双块清除及各类边界情况）。

#### 记忆注入默认位置调整

- `injection_position` 默认值从 `system_prompt` 改为 `user_message_before`。记忆内容注入用户消息头部，保持 system_prompt 稳定，有利于 DeepSeek / Claude 等提供商的前缀缓存命中，降低 API 成本。已有用户配置中显式设置过此项的不受影响。

### 事件粒度与 Event 页面修复

#### 连续窗口事件粒度

- 默认 extractor prompt 调整为“系统截取的连续消息窗口优先生成一个会话事件”，避免自然推进、追问、补充、评价、情绪表达、解决方案和相邻子话题切换被拆成多个数据库事件。
- `summary` 继续使用多个 `[What]/[Who]/[How]` 三元组承载相关小话题，`chat_content_tags` 覆盖这些小话题，只有明显跨时间、完全无关、无法同语境理解的片段才拆成多个事件。
- extractor 与手动 reextract 路径新增解析兜底：当 LLM 仍把同一系统窗口切成多个相邻片段时，会合并回一个覆盖完整窗口的 Event，保留合并后的 topic、summary、tags、salience 与 confidence。

#### Event WebUI 展示

- 事件 API 在保留 `participants` UID 列表的同时新增 `participant_names`，standalone WebUI、AstrBot plugin routes 和通用 API 均支持；缺失 persona 名称时回退 UID。
- Event 右侧 `DetailPanel` 摘要态与详情态统一桌面宽度，修复 sidebar / main inset 结构导致的缩进、压缩或覆盖异常。
- Event 摘要统计中的参与者列表优先显示 persona 名称，不再直接暴露 UUID。

#### 验证

- 新增 extractor 合并、WebUI `participant_names`、DetailPanel 宽度和 sidebar inset 结构回归测试。
- 相关后端 / API / 前端结构测试通过，前端构建完成并同步静态产物到 `pages/moirai/`。
- `run_realtime_dev.py` 默认改为优先验证 LLM extractor 路径，并接入 raw message、账号绑定与 provider 列表 wiring，作为更完整的实时管线 smoke test。

## [v0.16.1] - 2026-05-21

### 人格归属修复 & 手动操作进度弹窗

#### 人格归属诊断与修复

- 修复人格切换后新事件仍持续归入旧人格的问题。根因：AstrBot 的 `/persona` 命令只更新对话人格 `conversation.persona_id`，而 AstrBot 面板「会话管理」里设置的会话级强制人格规则 `session_service_config.persona_id` 优先级更高，会持续盖过 `/persona` 切换。
- `_resolve_persona_name` 新增 `[persona-resolve]` 诊断日志：每次请求输出 override / session_cfg / conversation / default 全部候选来源与最终胜出者，一行即可定位归属来源。
- 当会话级强制人格规则与对话人格不一致时输出 WARNING，提示前往 AstrBot 面板 → 会话管理 清除该规则。
- 窗口人格归属由「出现次数最多」改为「最近一条 bot 消息」（recency）：跨人格切换的窗口不再被旧人格的消息票数压过，正确归属到窗口关闭时生效的人格。
- `_get_bot_persona` 移除永久缓存，全局人格变更无需重载插件即可生效。

#### 手动 LLM 操作进度弹窗

- 新增右下角常驻 TaskDock：重新抽取事件、重新生成摘要、重新分析印象、合并人格等手动 LLM 操作运行时显示不定长进度条 + 运行中 / 成功 / 失败状态 + 耗时。
- 成功状态 4 秒后自动消失，失败状态常驻并显示错误信息，便于判断操作结果。

#### 其他

- 修复 Event Stream 展开视图（EventThread）左侧 loom 轴占位过宽（208px → 132px）导致开启详情面板时事件卡片被横向裁切的问题。

## [v0.16.0] - 2026-05-21

### 多账号绑定 / 跨平台人格合并

#### 新功能

- 同一真人在多个平台的账号（如 QQ + Discord）或同平台多个账号，可手动绑定到同一用户名下，人格分析时合并看待；绑定可随时分离。
- 采用**软分组覆盖层**：每个平台账号永久保留自己的 `Persona`/`uid` 与全部原始数据，绑定只是把它们关联进一个命名分组，零数据迁移、完全可逆。
- 每次绑定 / 解绑 / 解散都会立即在后台触发一次强制人格重合成。
- WebUI 新增「账号绑定」页面（侧边栏入口）：选择账号建组、加入 / 移出成员、重命名、解散分组。
- 聊天指令：`/mrm bind` 取配对码、`/mrm bind <配对码>` 兑现绑定、`/mrm unbind` 分离当前账号。配对码 5 分钟有效，确保普通用户只能绑定自己实际操作过的账号。
- 关系图谱 / Library 中同一分组的账号折叠为单一节点（标签为统一用户名），印象边自动重映射到分组代表 uid。

#### 数据与机制

- 新增迁移 `015_persona_groups.sql`：`persona_groups` 表 + `personas.group_id` 列。
- 新增 `PersonaGroupRepository`（SQLite + 内存实现）与 `AccountLinkManager` 绑定服务。
- 人格合成全面 group 感知：`run_persona_synthesis` / `run_persona_synthesis_for_uid` / `PersonaSynthesisTrigger` / `run_consolidated_maintenance` 会把分组成员折叠为一次合成，聚合全部成员事件后把统一人格镜像写回每个成员。
- 新增配置 `relation.account_merge_synthesis_only`（默认关闭）：关闭时人格合成与记忆召回都跨账号合并；开启后仅人格合成合并，记忆召回仍按单账号独立处理。

## [v0.15.1] - 2026-05-21

### 移除 Narrative 日摘要事件 & 主题调色盘统一

#### 移除 Narrative 事件链路

- 删除 `_upsert_narrative_event`：`run_group_summary` 和 `regenerate_single_summary` 不再将日摘要写入 events 表，消除了 Library 页面中日摘要事件污染列表的问题。
- 根因说明：`TaskScheduler.last_run` 初始为 0，每次插件重启都会立即触发 summary 任务；跨天重启就会在 events 表中积累大量 narrative 条目。
- `RecallManager.recall()` 简化为纯 episode 单层检索，移除 macro/micro/both 粒度分类（`_classify_granularity`）和两层并发搜索逻辑，代码量减少约 60 行。
- `formatter.py` `format_events_for_prompt` 移除宏观背景 / 相关历史记忆双分区渲染，统一为单区。
- `domain/models.py` 移除 `EventType.NARRATIVE` 常量；`soul_state.py` 移除 `has_narrative` 类型多样性加权。
- `repository/base.py` 和 `sqlite.py` 移除 `list_by_group` 的 `exclude_type` 参数、`search_fts` / `search_vector` 的 `event_type` 参数。
- `hybrid.py` `search_raw` 移除 `event_type` 参数。
- 相关测试更新：删除 `_classify_granularity` 和 narrative 相关断言，594 个测试全部通过。

#### 前端主题调色盘统一

- 每个主题 CSS（moirai / augustus / folio / juno / nox / selune / venus）新增 `--color-palette-1` ~ `--color-palette-8`，颜色从各主题色系派生，自动跟随 light/dark 模式。
- `lib/colors.ts` 新增 `PALETTE_COLORS`、`getThreadColor(id)`、`getPaletteColor(index)`，统一三处取色逻辑：
  - `getTagColor`：tag badge 颜色（原 `CHART_COLORS` hash，改用 `PALETTE_COLORS`）
  - `getThreadColor`：Library 事件行左边框 / Landing 最近事件卡片左边框（原 Tailwind 硬编码类名，改为 `style={{ borderLeftColor }}`）
  - `getPaletteColor`：Graph cluster 填色（原硬编码 hex，改用 CSS 变量）

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
