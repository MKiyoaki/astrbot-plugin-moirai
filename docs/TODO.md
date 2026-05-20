# TODO

## TODO 规范（写入指南）

本文件记录 Moirai 插件的开发计划、进行中的任务和待处理事项。所有参与者（包括 AI Agent）在读写本文件时请遵守以下规范。

### 状态标记

| 标记 | 含义 |
|------|------|
| `[x]` | 已完成 |
| `[ ]` | 待实现 |
| `🚧` | 进行中（当前 session 正在执行） |
| `❌` | 明确不做（已决策 defer/放弃） |
| `✅` | 整体完成（用于小节标题） |
| `💬` | 待讨论（Backlog 中未确认优先级的条目，执行前需先讨论） |

### 版本号规范

- 每个计划 section 的标题格式：`## vX.Y.Z 计划名称 (状态)`，例如 `## v0.13.0 Raw message persistence plan (completed)`
- 状态用英文：`planning` / `in progress` / `completed`
- 版本号来自 `metadata.yaml`；计划完成后在标题末尾改为 `(completed)`

### 新建计划规范

1. 在 **未实现功能 Backlog** 中找到或新增对应条目
2. 在本文件顶部（Backlog 之后）新建版本 section
3. section 内按以下顺序组织：
   - `### User constraints / 约束`：用户明确要求的限制
   - `### Technical implementation path`：按 Phase 划分，每条加 `[ ]` / `[x]`
   - `### Verification`：验证命令和结果（格式：`命令` → `结果`）
4. 完成后：把 Backlog 中对应条目移除或标记 `[x]`；标题改为 `(completed)`

### Agent 专项提示

- **先更新 TODO，再动代码**：每轮工作开始前先在本文件勾 `[x]` 或追加子项，再修改源码
- **测试通过后再标完成**：`[x]` 代表代码已落地且相关测试已过，不是"我已经写完"
- **Deferred 项不删除**：推迟的条目保留在 Backlog，注明推迟版本和原因
- **语言约定**：验证命令和代码标识符用英文；设计讨论和中文注释保持原语言
- **不要改 Completed 计划的内部细节**：已完成的 Phase 技术实现记录用于历史查阅，除修正错误外不得改动

---

## 💬 待讨论 Backlog

> 以下所有条目均处于**待讨论**状态，尚未纳入任何版本计划。执行前须明确优先级、设计方案并获得确认，以防与未来改动产生冲突。

### Bug / 补丁

- [ ] **`reanalyze_impressions_llm` i18n prompt fix**（延迟自 v0.13.1）
  - 当前提示词为硬编码英文，未走插件 `cfg.language` 国际化，且缺少 `system_prompt`，鲁棒性低于其他 LLM 调用点
  - 修复方向：参照 synthesis / summary prompt 结构，用 `cfg.language` 选语言，加 `system_prompt` 常量
  - 需要新增专用 prompt 常量或 config 字段

### 架构 / 清理

- [ ] **Persona synthesis 脏 UID 队列评估**：v0.12.14 已将 `BigFiveBuffer` 改为 `BoundedKeysMixin(maxkeys=500)` 有界内存（`_on_evict` 清理全部平行 dict 并取消 in-flight task），内存无限增长问题已解决；残留问题是跨重启的 trigger state 是否需要持久化——v0.12.11 新增了基于事件计数的实时触发机制（`persona_synthesis_trigger_messages` / `persona_synthesis_min_events`），大幅降低了对重启后状态恢复的依赖，但仍需评估是否完全不需要持久化
- [ ] **重命名 `summary_trigger_rounds`**：改为事件窗口阈值语义名称，同时保留旧 key 向后兼容加载
- [ ] **拆分 `context_window_size`**：分为 extractor context size 和 VCM session window size；旧 key 作为兼容性输入保留
- [ ] **`memory_cleanup_interval_days` 独立生效**：使其不依赖 daily maintenance 单独运行，或从用户配置中移除
- [ ] **拆分 `daily_maintenance`**：拆为 salience decay、memory cleanup、Markdown projection fallback 三个更清晰的任务项
- [ ] **群组摘要改为日历日生成**：仅在当天有新事件时才重新生成，替代当前每小时任意重写
- [ ] **`periodic_flush` 降级为 idle-window 兜底**：不再是主要事件分段机制
- [ ] **低影响运营参数移至高级设置**：v0.12.13 已将 `markdown_projection_enabled` 移至 level `advanced`；剩余未移的包括 context cleanup batch sizes、embedding 微调参数等

### Persona 隔离遗留（Phase 3a defer）

- [ ] `core/adapters/identity.py`：创建 Persona 时填 `bot_persona_name`（当前 defer：persona 是共享实体，不必按 bot 隔离；视后续 UI 需求决定）
- [ ] `core/sync/parser.py` / `core/sync/syncer.py`：Impression 构造传 `bot_persona_name=None`（MD 同步是旁路，先不动）

### Memory Recall Phase 7 — 发布说明（Phase 6 已完成，待补充 CHANGELOG）

- [x] Memory Recall Phase 6 注入兼容适配器 — **已实现**（commit `8fd2f66`, 2026-05-18）
  - `core/utils/injection_compat.py`：`resolve_injection_position(model, configured)` 适配器，已知不兼容 pattern：o-series（o1/o3…）、Gemini
  - `core/managers/recall_manager.py`：在 `recall_and_inject` 中提取 `req.model` 并调用适配器，降级时记录 debug 日志
  - `tests/backend/test_injection_compat.py`：20 个单元测试，覆盖兼容 / 不兼容 / 无 metadata 三种分支
- [ ] **Phase 7**：在 `CHANGELOG.md` / `docs/CHANGELOG.md` 补充 injection compat 的发布说明（功能描述、已知兼容 provider 列表、token impact 声明）

### 待讨论 Feature

- [ ] **预设关系（Preset Impressions）**：管理员/用户预设 bot 对某人的先验态度（朋友/仇人/亲人），关闭 LLM 提取时也生效
  - 讨论中的分歧：枚举模板映射到 benevolence × power 双轴 vs 数据一致性问题
  - 倾向方案：方案 B（独立 `PresetRelation` 表）+ 仅可视化作为 MVP，后续再开 prompt 注入开关
  - 两个待决定子问题：① 是否注入 system prompt ② 数据存储位置
- [ ] **WebUI Library 页面 Impression 直接删除入口**：Library 当前主要管理事件/人格/群组；后续增加 impression 表视图再接入

### 待确认设计决策

- [ ] **Narrative Event `inherit_from` 下钻**：向 `inherit_from` 写入当天所有 episode event_id 的 payload 开销评估（每天数十个 ID），以及对"宏观→微观"上下文展开的实际价值
- [ ] **`IMPRESSIONS.md` 反向同步长期去向**：当前 FileWatcher（30s 轮询）+ 正则解析维护成本高；评估是否新增 WebUI 直接 impression 表单提交 API，将 FileWatcher 降级为"离线备份"入口
- [ ] **分层 RAG 查询分类器精度提升**：当前关键词计数投票；评估接入轻量 embedding 相似度或 LLM 分类，但需权衡延迟开销

---

## v0.13.2 Persona 数据归库固化 (completed)

### User constraints / 约束
- 所有改动限制在 `astrbot-plugin-enhanced-memory/` 内（CLAUDE.md）。
- `bot_persona_name` 永远来自 AstrBot 性格设置（SSOT），与平台账号显示名彻底解耦。
- 同一性格名跨平台（QQ/Discord）必须进同一 `bot_persona_name` 桶。
- 作为独立阶段：单独提交、单独验证、确认实机归桶正确后再做 v0.14.0。
- 绝不破坏旧数据：`bot_persona_name IS NULL` 仍是合法的「遗留/默认」桶语义。

### 问题根因（代码定位）
1. 事件 `bot_persona_name` 在 `core/extractor/extractor.py:298-309` 最终确定：优先取窗口内 bot 消息携带的 `bot_persona_name`，否则回退 `_get_bot_persona()`。
2. bot 消息 persona 由 `core/event_handler.py:_resolve_persona_name` 解析，三层回退（`sp` 的 `session_service_config.persona_id` → `conversation.persona_id` → `provider_settings.default_personality`），不同平台/会话可能产生不同结果或 `None`。
3. 回退函数 `core/extractor/persona_context.py:resolve_bot_persona_context` 用 `next(...)` 取第一个 `internal`-bound persona —— 表中存在多个内部 bot persona 时结果不确定。
4. `handle_llm_response` 用 `display_name = persona_name`、`physical_id = f"bot:{persona_name}"` 创建内部 persona —— 一旦某次解析意外返回账号名，错误名固化进 `personas` 表，污染后续回退。

### Technical implementation path

#### Phase 0 — 基线与诊断
- [x] 跑基线测试：`pytest tests/backend/test_extractor.py tests/backend/test_new_configs.py tests/backend/test_persona_merge.py -q` → 38 passed
- [x] 新建只读诊断脚本 `tools/diagnose_persona_buckets.py`：打印 events/impressions/personas 的 `bot_persona_name` 分桶计数 + 所有 `internal`-bound persona 行

#### Phase 1 — 单一 SSOT persona 解析器
- [x] `event_handler._resolve_persona_name`：入口短路 —— `cfg.bot_persona_name_override` 非空时直接返回 override，使 bot 回复 / 原始消息 / 窗口全部携带统一名
- [x] `handle_llm_response` 复用 `_pre_inject_persona_name` 缓存、`_resolve_persona_name` 解析失败返回 `None`：经核查既有实现已正确，无需改动

#### Phase 2 — `bot_persona_name_override` 显式锁定
- [x] `_conf_schema.json` `relation` 组新增 `bot_persona_name_override`（string，默认 ""，level advanced）
- [x] `core/config.py`：`ExtractorConfig` 加 `bot_persona_name_override: str = ""`；`get_extractor_config()` 填充；新增 `PluginConfig.bot_persona_name_override` property
- [x] `core/extractor/extractor.py`：构造读 `cfg.bot_persona_name_override`；在事件 `bot_persona_name` 最终确定处单点优先应用
- [x] i18n：三语写入 `.astrbot-plugin/i18n/{zh-CN,en-US}.json` + WebUI `i18n.ts`（zh/ja/en）；配置页 `relation` section 加入该 key

#### Phase 3 — 加固回退（去随机性）
- [x] `persona_context.py:resolve_bot_persona_context`：去掉「任取第一个 internal persona」，改 `last_active_at` 确定性选择 + 歧义 `logger.warning`；docstring 标明仅供 prompt 描述
- [x] override 在 extractor 事件归桶处单点决定，`_resolve_window_persona` / `_get_bot_persona` 不再影响归桶（无需额外改动）

#### Phase 4 — 验证与数据归并指引
- [x] 新增 3 个测试（`test_extractor.py`）：① override 后全部落该桶 ② 解析失败落 NULL ③ 同名 persona 跨平台进同一桶
- [x] `docs/CHANGELOG.md` 新增 v0.13.2 条目，写明诊断脚本 + 「Persona 归属管理」(`merge_bot_persona`) 修复路径

### Verification
- `python -m py_compile core/event_handler.py core/extractor/persona_context.py core/extractor/extractor.py core/config.py tools/diagnose_persona_buckets.py` → passed
- `python -m json.tool _conf_schema.json` → passed
- `pytest tests/backend/test_extractor.py tests/backend/test_new_configs.py tests/backend/test_persona_merge.py -q` → 41 passed（含 3 个新测试）
- `pytest tests/backend -q` → 592 passed, 1 failed（`test_recall_manager_injects_low_weight_social_impressions` —— 经 `git stash` 核实为改动前既有失败，与本计划无关，疑似 Windows 控制台编码问题，另行处理）
- 实机待用户执行：QQ + Discord 同一性格各发消息 → `python tools/diagnose_persona_buckets.py` 确认事件全部落同一 `bot_persona_name`

---

## v0.14.0 WebUI 配置体验重构 (completed)

### User constraints / 约束
- 在 v0.13.2 完成并验证后再做。
- 六大类对齐 WebUI「三轴记忆」心智模型（事件流/关系图/摘要 与现有页面同名）。
- 三档层级：新手 / 进阶 / 研究员。新手档极简 —— 只保留最关键开关，数值微调全部下沉，小白靠快速设置向导预设包，不手动调参。
- Soul 标记为实验性、默认关闭、不进新手档、不进任何默认开启的预设。
- 前端改动后必须 `npm run build` + `python tools/sync_frontend.py -f`（先 `conda activate plugin-dev`）。

### 配置热更新检查结论（用户第 4 点）
当前保存配置不会热更新：`_handle_update_config` 写 `plugin_config.json` 并同步 AstrBot live config 对象，但运行中引擎初始化时已捕获配置值、不重读。不做选择性「字段级热更新」（风险高、状态分散）。

**采用方案 —— 保存后自动重载插件**：AstrBot 已暴露 `context._star_manager.reload("astrbot_plugin_moirai")`（terminate → unbind → load 整体重启），且 AstrBot 原生 dashboard 保存插件配置时本就调用此 API（`dashboard/routes/config.py`）。在本插件 WebUI 保存路径复用同一机制 = 最干净的「热更新」。代价：WebUI（端口 2655）随之重启、短暂不可用约 1–3s（用户已接受）。

### Technical implementation path

#### Phase 0 — Schema 层级体系
- [x] `_conf_schema.json` 每字段 `level` 扩为 `basic|advanced|expert`，重打标 102 字段（basic 16 / advanced 45 / expert 41）
- [x] soul 组 7 字段加 `"experimental": true`；`soul_enabled` 描述 🟢→🧪
- [x] `web/frontend/lib/api.ts` `ConfSchemaField`：`level` 加 `'expert'`；新增 `experimental?: boolean`

#### Phase 1 — 六大类层级 + 三档过滤
- [x] `config/page.tsx` `CATEGORIES` 两级结构：6 父类（常规/信息流/事件流/关系图/摘要记忆/数据库维护）含原 12 section 作子分组卡片
- [x] 二元 `showAdvanced` 替换为三段 `ToggleGroup`（新手/进阶/研究员），过滤改「显示 level ≤ 当前档」；localStorage `em_config_level`（兼容旧 `em_show_advanced_config`）
- [x] `experimental` 字段加「实验性」徽章（含 🧪 marker 剥离）；`on-this-page.tsx` 改两级 TOC
- [x] `i18n.ts`：6 父类标签 + 3 档位标签 + 「实验性」三语

#### Phase 2 — 全局搜索框
- [x] sticky 工具栏加搜索 `Input`，按 key/label/hint 跨六大类过滤；命中平铺列表带「父类 / 子分组」面包屑

#### Phase 3 — 快速设置向导
- [x] 新建 `web/frontend/components/config/quick-setup-wizard.tsx`（Dialog 四步：打开 Sudo → 功能选择 → 预设参数包 → 应用并跳转 `/config`）
- [x] 常驻「快速设置」按钮（配置页头部）；`store.tsx` 加 `quickSetupDone`（`em_quick_setup_done`）；`app-shell.tsx` 首启在 `firstLaunchDone` 之后弹出
- [x] 预设三选一：「仅聊天+记忆优化」/「均衡社交记忆」(推荐)/「完整/研究」；向导文案三语

#### Phase 5 — 保存后自动重载（解决第 4 点）
- [x] 新增配置 `webui_auto_restart_on_save`（webui 组，bool，默认 true，advanced）+ `core/config.py` getter
- [x] `web/plugin_routes.py:_handle_update_config`：写完配置先返回 HTTP 200（响应体加 `restarting`），`_schedule_plugin_restart` 以延迟 1s 后台任务调用 `context._star_manager.reload("moirai")`，失败写日志
- [x] 前端：`api.pluginConfig.update` 返回 `restarting`；`handleSave` 触发后显示全屏「正在重启插件」遮罩，两阶段轮询 `/api/auth/status`（先看到掉线再看到恢复）后 `location.reload()`
- [x] 配置页横幅按 `webui_auto_restart_on_save` 取值切换 `restartAutoHint` / `restartManualHint` 文案

#### Phase 6 — 文案与收尾
- [x] `npm run build`（next build，TypeScript 通过，12 静态页生成）+ `python tools/sync_frontend.py -f` 同步 `pages/moirai`

### Verification
- `python -m py_compile web/plugin_routes.py core/config.py` → passed
- `python -m json.tool _conf_schema.json .astrbot-plugin/i18n/{zh-CN,en-US}.json` → passed
- `cd web/frontend && npm run build` → Compiled successfully, TypeScript passed, 12/12 静态页
- `python tools/sync_frontend.py -f` → synced
- `pytest tests/frontend -q` → 209 passed
- `pytest tests/backend -q` → 592 passed, 1 failed（`test_recall_manager_injects_low_weight_social_impressions` —— v0.13.2 已核实为既有失败、与本计划无关）
- 实机待用户验证：三档切换字段数递增 / 搜索跨类命中 / 首启弹向导走完四步 / 头部按钮重开 / Soul 实验性徽章 / 两级 TOC / 保存后插件自动重启且 WebUI 自动重连

---

## v0.13.1 Manual summary & relation fixes (completed)

### Changes
- [x] Remove unused `summary_word_limit` user config; hardcode 300-char default in `SummaryConfig`.
- [x] Fix `regenerate_single_summary`: pass `summary_config`, `llm_manager`, `encoder` from call site so manual re-generation respects user settings, goes through LLM concurrency control, and keeps the NARRATIVE event in DB in sync with the Markdown file.
- [x] Fix `_handle_reanalyze_impressions_guarded` (LLM branch): pass `persona_repo` so `reanalyze_impressions_llm` can resolve UIDs to display names in the prompt.
- [x] Fix `reanalyze_impressions_llm`: remove dead `extractor_config` parameter; add optional `persona_repo`; build `uid_to_name` map; use display names in prompt.

### Deferred to later patch
- [ ] `reanalyze_impressions_llm` uses a hardcoded English prompt with empty `system_prompt`, inconsistent with the plugin's i18n system and lower format robustness than other LLM call sites. Should be replaced with a localized prompt using `cfg.language` and a proper system prompt (analogous to synthesis / summary prompts). Requires dedicated config / prompt constant.

### Verification
- `python -m py_compile core/config.py core/tasks/summary.py core/tasks/reanalyze_llm.py web/plugin_routes.py web/server.py` → passed.
- `python -m json.tool _conf_schema.json` → passed.
- `pytest tests/backend/test_reanalyze_llm.py tests/backend/test_new_configs.py tests/backend/test_reextract.py tests/backend/test_web_reextract_raw.py -q` → 18 passed.
- `pytest tests/backend -q` → 580 passed, 1 external faiss/numpy deprecation warning.

---

## v0.12.14 缓存工具统一 & 无界 dict 修复 (completed)

- [x] 新增 `core/utils/cache.py`：`_LRUCache[V]`（泛型有界 LRU，`maxsize` 必填）+ `BoundedKeysMixin`（多平行 dict 统一驱逐框架）
- [x] `IdentityResolver._cache` 改为 `_LRUCache(maxsize=2000)`，防止大规模用户场景内存无限增长
- [x] `BigFiveBuffer` 继承 `BoundedKeysMixin(maxkeys=500)`；`add_message()` 调用 `_touch(uid)`；`_on_evict()` 清理 5 个平行 dict 并取消 in-flight scoring task
- [x] `encoder.py` 复用 `utils.cache._LRUCache`，不再自定义
- [x] 5 个新测试（总计 552 个通过）

## v0.12.13 Encoder 性能优化 & 默认配置调整 (completed)

- [x] `_normalise(text)`：折叠空白、截断至 200 字符，作为统一 LRU cache key 和推理输入
- [x] `SentenceTransformerEncoder` 使用独立 `ThreadPoolExecutor(max_workers=1)` 保持模型权重常驻同一线程 CPU cache
- [x] `ApiEncoder.encode()` 同步接入归一化逻辑
- [x] `markdown_projection_enabled` 默认值改为 `false`，level 升为 `advanced`（WebUI 已有完整管理界面，文件投影对大多数用户是冗余 I/O）
- [x] 6 个新测试（归一化、等价 query 同 key、专用 Executor 类型验证）

## v0.12.12 高优先级性能优化批次 (completed)

- [x] SQLite 新增 PRAGMA：`mmap_size=256MB`、`temp_store=MEMORY`、`wal_autocheckpoint=500`
- [x] 迁移 `012_perf_composite_index.sql`：`events` 表新增复合索引 `(status, event_type, group_id)`
- [x] `search_vector` 热路径改用 `_EVENT_SEARCH_COLS` 剥离 `interaction_flow` 大 JSON，降低单次向量检索 I/O
- [x] Embedding LRU 缓存（128 条）接入 `SentenceTransformerEncoder` 与 `ApiEncoder`
- [x] `HybridRetriever.search_raw()` 新增可选 `embedding` 参数；`RecallManager.recall()` 统一编码一次 query，同时传入 narrative 和 episode 两层，消除重复 CPU 推理
- [x] `RecallManager._soul_states` 新增 TTL 驱逐（`_evict_soul_states()`）；新增配置 `soul_states_ttl_hours`（默认 24h，范围 1–168h）
- [x] 13 个新测试（总计 542 个通过）

## v0.12.11 事件边界智能分割 & 关系重分析 LLM 模式 (completed)

- [x] **冗余实现清理**：人格合成抽出单人 helper，`run_persona_synthesis()` / `run_consolidated_maintenance()` 复用；`reindex_all` 保持手动任务语义（`interval <= 0` 跳过调度循环）；`file_watcher_poll_seconds` 接入 `FileWatcher`
- [x] **人格合成触发机制改造**：主路径改为基于事件计数触发（达到 `persona_synthesis_trigger_messages` 新增消息数后合成对应 UID）；新增配置 `persona_synthesis_trigger_messages` / `persona_synthesis_min_events` / `persona_synthesis_cooldown_hours`；`persona_synthesis_interval_hours` 降为兜底扫描间隔
- [x] **事件边界智能分割（Smart Split）**：窗口触达容量上限时，`EventBoundaryDetector.find_split_index()` 寻找最自然话题断点（优先 encoder 余弦距离，降级时间间隔）；`MessageRouter._flush_window_smart_split()` 无损分段，前段提交为事件、后段作为种子继续
- [x] **重新分析关系 LLM 深度模式**：新增 `core/tasks/reanalyze_llm.py`，Semaphore(3) 并发 LLM 调用，`{benevolence, power}` JSON 解析，α=0.4 混合旧印象；路由层读取 `body.method`（`"llm"` / `"heuristic"`）；前端新增 `ReanalyzeMethodDialog` 弹出模式选择
- [x] 新增配置 i18n（三语）；5 个边界检测测试 + 6 个 reanalyze_llm 测试

---

## v0.13.0 Raw message persistence plan (completed)

### User constraints
- [x] Planning completed; Phase 1-9 implementation approved and executed.
- [x] Keep all future code changes inside `astrbot-plugin-enhanced-memory/`.
- [x] Minimize new user-facing parameters. Prefer conservative constants for internal batching/queue behavior unless runtime tuning is clearly needed.
- [x] Keep `events` as the primary long-term memory layer; raw messages are an auxiliary evidence/detail layer with short retention.
- [x] Update this section after each completed phase with status and verification notes.

### Minimal parameter surface
- [x] Add only one required user-facing setting for MVP: `raw_message_retention_days`, default `14`, hard-clamped to `1..14`.
- [x] Prefer no exposed switch for raw storage in MVP. If a kill switch proves necessary during implementation, add `raw_message_storage_enabled`, default `true`.
- [x] Keep internal write tuning as code constants at first:
  - `RAW_MESSAGE_BATCH_SIZE = 32`
  - `RAW_MESSAGE_FLUSH_INTERVAL_MS = 1000`
  - `RAW_MESSAGE_QUEUE_MAX_SIZE = 2000`
  - `RAW_MESSAGE_MAX_TEXT_CHARS = 4000`
  - `RAW_MESSAGE_DETAIL_PER_EVENT = 8`
- [x] Do not add separate public knobs for batch size, queue size, flush interval, max text chars, or recall detail count unless tests or production behavior show a real need.
- [x] Existing parameters whose meaning must remain stable:
  - `context_max_history_messages`: still controls event-summary history pressure, not raw-message retention.
  - `context_cleanup_batch_size`: still applies to event-level pruning, not raw-message cleanup.
  - `retrieval_token_budget`: remains the final prompt budget guard if raw details are hydrated.

### Raw message storage metadata
- [x] Identity and stream metadata:
  - `message_id`: stable plugin-generated id, unique.
  - `session_id`: router stream key, e.g. group/channel/private session.
  - `group_id`: persisted memory scope, `NULL` for private chat.
  - `platform`: source platform for the sender identity.
  - `physical_id`: sender platform id.
  - `sender_uid`: resolved persona UID.
  - `display_name`: normalized visible name at ingest time.
- [x] Content metadata:
  - `role`: `user`, `assistant`, or future system/meta value.
  - `text`: normalized text used by memory logic.
  - `content_hash`: hash of normalized text plus identity/time salt as needed for dedupe/debug.
  - `message_chain_json`: serialized structured message segments; default `[]`.
  - `metadata_json`: small adapter-specific metadata; default `{}`.
- [x] Persona and lifecycle metadata:
  - `bot_persona_name`: active bot persona for bot replies, nullable.
  - `created_at`: platform/event timestamp.
  - `ingested_at`: plugin persistence timestamp.
- [x] Event-link metadata:
  - `event_messages.event_id`: linked long-term event.
  - `event_messages.message_id`: linked raw message.
  - `event_messages.ordinal`: message order inside that event.
- [x] Deliberately excluded from MVP:
  - Raw unnormalized text storage by default.
  - Per-message embedding table.
  - Full platform payload blobs beyond compact `message_chain_json` / `metadata_json`.

### Technical implementation path

#### Phase 0 - Baseline and tests
- [x] Review current tests before code changes:
  - `tests/backend/test_message_router.py`
  - `tests/backend/test_sqlite_repo.py`
  - `tests/backend/test_reextract.py`
  - `tests/backend/test_retrieval.py`
  - `tests/backend/test_memory_manager.py`
- [x] Run baseline targeted backend tests and record results here.
  - `pytest tests/backend/test_message_router.py tests/backend/test_sqlite_repo.py tests/backend/test_reextract.py tests/backend/test_retrieval.py tests/backend/test_memory_manager.py` → 100 passed.
- [x] Confirm no core framework code changes are needed.

#### Phase 1 - Schema and domain compatibility
- [x] Add migration `013_raw_messages.sql`.
- [x] Add `raw_messages` table, `event_messages` table, indexes, and optional `raw_messages_fts`.
- [x] Extend `MessageRef` with optional trailing `message_id: str = ""` to keep old positional construction compatible.
- [x] Verify migrations are idempotent on a fresh DB and an existing DB.
  - Covered by `tests/backend/test_sqlite_repo.py::test_migrations_are_idempotent`.

#### Phase 2 - Repository layer
- [x] Add `RawMessageRepository` abstraction in `core/repository/base.py`.
- [x] Implement `SQLiteRawMessageRepository`.
- [x] Implement `InMemoryRawMessageRepository` for tests.
- [x] Add tests for roundtrip, event linking, cleanup, and expired raw-message fallback behavior.
  - Added SQLite roundtrip/link/cleanup coverage in `tests/backend/test_sqlite_repo.py`.

#### Phase 3 - Optimized async write path
- [x] Add `RawMessageWriter` with an in-memory async queue.
- [x] `MessageRouter.process()` should enqueue raw-message writes without waiting for SQLite in the normal path.
- [x] Batch writer behavior:
  - Batch insert with short transactions.
  - Use `INSERT OR IGNORE` for idempotent retry safety.
  - Truncate text to internal max length before enqueue.
  - If the queue is full, wait only briefly; if still full, skip raw persistence and log a warning.
- [x] Add `ensure_flushed(message_ids)` so event extraction can wait for only the messages it needs.
- [x] Add shutdown drain in plugin teardown.

#### Phase 4 - Message router integration
- [x] Generate `message_id` per incoming user message and bot response.
- [x] Attach `message_id` and minimal metadata to `RawMessage` / `MessageWindow`.
- [x] Keep message processing functional if raw-message enqueue/write fails.
- [x] Cover user message, bot reply, Discord/channel session, group, and private paths.
  - Added router raw-message persistence coverage in `tests/backend/test_message_router.py`.

#### Phase 5 - Event extractor integration
- [x] Include `message_id` in `Event.interaction_flow` previews.
- [x] Before linking event messages, call `RawMessageWriter.ensure_flushed(...)`.
- [x] Write `event_messages` mapping with ordinal order.
- [x] Keep event upsert/vector indexing behavior unchanged.
- [x] If raw messages are missing, event persistence must still succeed with preview-only `interaction_flow`.
  - Added extractor event-link coverage in `tests/backend/test_extractor.py`.

#### Phase 6 - Read-path enhancement
- [x] Update `reextract_event()` to prefer raw messages linked through `event_messages`.
- [x] Fall back to existing `interaction_flow.content_preview` when raw details are expired or unavailable.
- [x] Extend recall formatting to hydrate only a small internal number of raw details per selected event.
- [x] Enforce `retrieval_token_budget` as the final guard; raw details must not cause uncontrolled prompt growth.
  - Added reextract raw-detail preference coverage in `tests/backend/test_reextract.py`.
  - Added recall hydration coverage in `tests/backend/test_recall_manager_extra.py`.

#### Phase 7 - Cleanup lifecycle
- [x] Add raw-message cleanup task using `raw_message_retention_days` with a 14-day default.
- [x] Delete expired raw messages without deleting long-term `events`.
- [x] Ensure `event_messages` is cleaned through foreign keys or explicit cleanup.
- [x] Wire cleanup into existing maintenance with no extra public interval parameter for MVP.
  - Raw cleanup runs independently of low-salience memory cleanup enablement to preserve the short raw-data lifecycle.
  - Added raw cleanup lifecycle coverage in `tests/backend/test_memory_cleanup.py`.

#### Phase 8 - Config and WebUI sync
- [x] Add `raw_message_retention_days` to `core/config.py` and clamp to `1..14`.
- [x] Add the setting to `_conf_schema.json`.
- [x] Only update WebUI code if schema-driven config rendering is insufficient.
  - No frontend source changes required; AstrBot config UI reads `_conf_schema.json`.

#### Phase 9 - Verification and release notes
- [x] Run targeted backend tests after each backend phase.
- [x] Run broader `pytest tests/backend` before handoff.
- [x] Update `CHANGELOG.md` / `docs/CHANGELOG.md` with schema, behavior, migration, and privacy notes after implementation.
- [x] Document residual risk: DB size growth, short-term privacy exposure, and raw-detail prompt token pressure.

### Verification
- `python -m py_compile core\domain\models.py core\boundary\window.py core\repository\base.py core\repository\sqlite.py core\repository\memory.py core\managers\raw_message_writer.py core\adapters\astrbot.py core\plugin_initializer.py` → passed.
- `pytest tests/backend/test_message_router.py tests/backend/test_sqlite_repo.py` → 58 passed.
- `pytest tests/backend/test_message_router.py tests/backend/test_sqlite_repo.py tests/backend/test_reextract.py tests/backend/test_retrieval.py tests/backend/test_memory_manager.py tests/backend/test_periodic_flush.py` → 111 passed.
- `python -m py_compile core\extractor\extractor.py core\tasks\reextract.py core\managers\recall_manager.py core\utils\formatter.py core\tasks\cleanup.py core\plugin_initializer.py tests\backend\test_extractor.py tests\backend\test_reextract.py tests\backend\test_recall_manager_extra.py tests\backend\test_memory_cleanup.py` → passed.
- `pytest tests/backend/test_memory_cleanup.py tests/backend/test_extractor.py tests/backend/test_reextract.py tests/backend/test_recall_manager_extra.py tests/backend/test_message_router.py tests/backend/test_sqlite_repo.py` → 104 passed.
- `pytest tests/backend` → 578 passed, 1 external faiss/numpy deprecation warning.
- `python -m json.tool _conf_schema.json` → passed.
- `pytest tests/backend/test_new_configs.py tests/backend/test_memory_cleanup.py tests/backend/test_extractor.py tests/backend/test_reextract.py tests/backend/test_recall_manager_extra.py tests/backend/test_message_router.py tests/backend/test_sqlite_repo.py` → 107 passed.
- `pytest tests/backend` → 579 passed, 1 external faiss/numpy deprecation warning.

---

## Memory recall scope + robustness plan (completed, 2026-05-18)

### Phase 0 - Baseline and planning
- [x] Read AGENTS.md and current tests before code changes.
- [x] Confirm current recall / injection data flow and the risk: `group_id=None` is overloaded as both global search and private-chat scope.
- [x] Baseline tests previously checked: `python -m pytest tests\test_retrieval.py tests\test_prompt_injection.py tests\test_tasks.py -q` passed.
- [x] Token impact for Phase 0/1: no added LLM calls, no prompt token increase.
- [x] Frontend impact for Phase 0/1: none.

### Phase 1 - Explicit recall scope semantics
- [x] Add regression tests for three modes: global search, group search, and private-chat search.
- [x] Add explicit `scope_mode` through repository, retriever, recall manager, tool, and command paths.
- [x] Keep global search efficient: `scope_mode="all"` emits no `group_id` SQL predicate or `OR` branch.
- [x] Make automatic LLM-request recall use the current conversation scope: group conversations use `scope_mode="group"`, private conversations use `scope_mode="private"`.
- [x] Run targeted retrieval/repository tests after implementation.
  - `python -m pytest tests\test_retrieval.py tests\test_sqlite_repo.py tests\test_memory_repo.py -q` → 106 passed.
  - `python -m pytest tests\test_retrieval.py tests\test_prompt_injection.py tests\test_session_progress.py tests\test_tasks.py -q` → 85 passed, 1 external faiss/numpy deprecation warning.
  - Final quick check after cleanup: `python -m py_compile main.py core\api.py core\event_handler.py core\managers\base.py core\managers\command_manager.py core\managers\recall_manager.py core\repository\base.py core\repository\memory.py core\repository\sqlite.py core\retrieval\hybrid.py` → passed.
  - Final quick check after cleanup: `python -m pytest tests\test_retrieval.py tests\test_sqlite_repo.py -q` → 66 passed.

### Phase 2 - Recall hot-path degradation
- [x] BM25 and vector search now degrade independently: if one side fails, recall continues with the other side.
- [x] Narrative and episode recall tiers use exception-tolerant gather so one tier cannot cancel the whole recall.
- [x] Prompt/fake-tool-call/command formatting now has a deterministic formatter fallback for malformed event payloads.
- [x] Token impact for Phase 2: no added LLM calls, no prompt token increase in the normal path. Fallback only emits already-recalled event text within the existing token budget.
- [x] Frontend impact for Phase 2: none.

### Phase 3 - Non-LLM fallback memory generation
- [x] Added partition-level rule fallback for distillation failures and missing providers.
- [x] Fallback memory generation now uses participant names, representative message excerpts, simple tags, salience scaling, and low confidence instead of a generic failure string.
- [x] Semantic pipeline noise filtering now reads `RawMessage.text`, preventing valid messages from being dropped before fallback generation.
- [x] Token impact for Phase 3: no added LLM calls. This reduces dependency on LLM success and writes fallback summaries locally.
- [x] Frontend impact for Phase 3: none.
- [x] Verification:
  - `python -m py_compile main.py core\utils\formatter.py core\retrieval\formatter.py core\retrieval\hybrid.py core\managers\recall_manager.py core\managers\command_manager.py core\extractor\extractor.py core\extractor\parser.py core\extractor\noise_filter.py` → passed.
  - `python -m pytest tests\test_retrieval.py tests\test_prompt_injection.py tests\test_extractor.py tests\test_llm_manager.py -q` → 73 passed.
  - `python -m pytest tests\test_retrieval.py tests\test_prompt_injection.py tests\test_extractor.py tests\test_sqlite_repo.py tests\test_memory_repo.py tests\test_tasks.py -q` → 186 passed.

### Phase 4 - Relationship / impression soft injection
- [x] Wire `ImpressionRepository` into `RecallManager` and plugin initialization.
- [x] During system-prompt injection, fetch only impressions connected to the active `sender_uid`, scoped by the current group/private scope and current `bot_persona_name`.
- [x] Inject at most `impression_injection_max_items` directed impressions, filtered by `impression_injection_min_confidence`, with explicit low-weight constraints:
  - Do not mention scores, sources, or the injected block.
  - Do not override current user intent, factual memory, safety rules, or higher-priority system instructions.
  - Ignore relation hints when they conflict with stronger context.
- [x] Keep fake-tool-call mode unchanged; relation hints are system-prompt-only for compatibility.
- [x] Add sanitized injection debug output for relation hints without exposing evidence event IDs.
- [x] Token impact for Phase 4: no added LLM calls. When relation data exists, default max 3 hints adds about 80-140 prompt tokens. When no matching impression exists, token increase is 0.
- [x] Frontend impact for Phase 4: config fields added in WebUI/Astr settings; no new page or interaction surface.

### Phase 5 - LLM success/failure observability
- [x] `LLMTaskManager` records recent LLM call details: task name, success/failure, duration, prompt/completion tokens, and truncated error text.
- [x] `get_stats()` remains compact by default; `recent_calls` is only returned when `show_llm_call_details` is enabled.
- [x] Add `show_llm_call_details` under the Astr/WebUI `debug_display` settings group.
- [x] WebUI stats panel now displays total/OK/failed LLM calls and, when enabled, recent success/failure rows.
- [x] Token impact for Phase 5: no added prompt tokens and no added LLM calls.
- [x] Frontend impact for Phase 5: modified WebUI config page, i18n labels, stats API types, stats token panel, and synchronized `pages/moirai` static assets.
- [x] Verification:
  - `python -m py_compile core\config.py core\managers\base.py core\managers\recall_manager.py core\managers\llm_manager.py core\api.py core\event_handler.py core\plugin_initializer.py web\server.py web\plugin_routes.py` → passed.
  - `python -m json.tool _conf_schema.json` → passed.
  - `python -m pytest tests\test_retrieval.py tests\test_prompt_injection.py tests\test_extractor.py tests\test_sqlite_repo.py tests\test_memory_repo.py tests\test_tasks.py tests\test_llm_manager.py tests\test_new_configs.py tests\test_debug_visibility.py tests\test_perf.py tests\test_session_progress.py -q` → 221 passed, 1 external faiss/numpy deprecation warning.
  - `npm.cmd run build` → passed after allowing network access for Google Fonts.
  - `python tools\sync_frontend.py -f` → passed.

### Phase 6 - Injection compatibility adapter (✅ 完成，commit `8fd2f66`, 2026-05-18)
- [x] `core/utils/injection_compat.py` — `resolve_injection_position(model, configured)` 适配器；已知不兼容 pattern：o-series（`^o\d`）、Gemini（`^gemini`），均降级为 `user_message_before`
- [x] `core/managers/recall_manager.py` — `recall_and_inject` 提取 `req.model`，调用适配器，降级时 debug 记录 reason；injection_debug 同步记录 `compat_reason`
- [x] `tests/backend/test_injection_compat.py` — 20 个单元测试：兼容 / 不兼容 / 无 metadata / 非 fake_tool_call 保持不变
- [x] Token impact: 无新增 LLM 调用；降级后 token 数与格式化文本近似不变
- [x] Frontend impact: 无需前端改动

### Phase 7 - Broader verification and release notes
- [x] Phase 6 实现和测试已完成
- [ ] 在 `CHANGELOG.md` / `docs/CHANGELOG.md` 补充 injection compat 发布说明（功能描述、已知兼容 provider 列表、token impact）

---

## 🚧 Persona 隔离 + 配置拆分 + WebUI 主架构升级 (completed)

### 📋 大计划：整体架构（交接必读）

**目标**：让 Moirai 支持多 Bot Persona（AstrBot 端可以配多个 bot 人格）下的**数据隔离**。每个 persona 在 WebUI 中看到独立的事件 / 印象 / 关系，但**设置全部共享**（plugin_config.json 还是同一份）。同时支持"All Personas"汇总视图把所有 persona 的数据放到一张图。**绝不破坏旧版本数据**。

**核心方案 — 行级隔离**（不是分库）：
- DB 表 `events` / `impressions` / `personas` 各加一列 `bot_persona_name TEXT`
- `NULL` 语义 = "遗留 / 默认 persona"（迁移前的所有数据自动是 NULL）
- 写入：事件归属由 `core/extractor/extractor.py:_get_bot_persona()` 推断当前 AstrBot 激活的 persona name（扫 `personas` 表中 `platform="internal"` 的 primary_name），然后透传到下游 Impression 写入
- 读取：repository 的 `list_*` 方法加 `bot_persona_name=` / `include_legacy=True` 参数；SQL 拼接为 `(bot_persona_name = ? OR bot_persona_name IS NULL)`，默认带遗留行，让选了 Alice 的人也能看到迁移前的数据
- API：所有 `/api/events` `/api/graph` `/api/archived_events` 等接受 `?persona=Alice` query；不带 = 汇总视图
- 新端点 `GET /api/personas/bots` 返回所有出现过的 bot_persona_name + 事件计数，给前端 selector 用

**核心方案 — Impression 表 unique key 修复**：
- 旧 `UNIQUE(observer_uid, subject_uid, scope)` 升级为 `UNIQUE(observer, subject, scope, ifnull(bot_persona_name, ''))`
- SQLite 的 inline UNIQUE 对 NULL 视为不同，所以**必须**用 `CREATE UNIQUE INDEX ... ifnull(...)` 表达式索引（migration 010 已经做了）
- `ON CONFLICT(observer, subject, scope, ifnull(bot_persona_name, ''))` 用同样的表达式匹配索引

**核心方案 — 数据流**：

```
AstrBot 消息 → MessageRouter → MessageWindow
                                    ↓ 关窗
                       Extractor 提取 Event
                                    ↓ event.bot_persona_name = _get_bot_persona()
                                Event 写入 DB
                                    ↓
            SocialOrientationAnalyzer.analyze(..., bot_persona_name=event.bot_persona_name)
                                    ↓
                       Impression 写入 DB（带 bot_persona_name）
                                    ↓
                       WebUI ?persona=Alice → repo.list_*(bot_persona_name='Alice')
                                    ↓
                       前端 store.currentPersonaName 决定查哪个 scope
```

**前端架构**：
- store 加 `currentPersonaName: string | null` + `scopeMode: 'single' | 'all'`，localStorage 持久化
- Sidebar 顶部 PersonaSelector 全局可切
- 首次启动弹 FirstLaunchPersonaPicker（受 `persona_default_view_mode` 配置控制）
- 每个 page 在 useEffect 依赖 store 的 persona 状态，变化时重新 fetch

**Persona 合并 (Phase 4)**：
- 后端 `POST /api/personas/merge` body `{src, target, mode}` — 事务内 DELETE 冲突 impressions + UPDATE events/impressions/personas (target wins 策略)
- 难点：impressions 的 unique index 可能在合并时冲突（如果 src 和 target 都有 (obs, subj, scope) 同 tuple 的行）。采用"target wins"策略：先 DELETE src 中和 target 冲突的行，再 UPDATE 剩余
- 审计日志（可关）：`data_dir/audit/persona_merge.jsonl`

**关键决策（用户已确认）**：
- 隔离键采用复用已有的 `bot_persona_name` 字符串（不引入新的 UID）
- 首次进入：localStorage 记上次 + 首次弹窗
- 登录 UI：仅 polish 保留布局

**主动 defer（明确不做）**：
- ❌ Partitioner 按 persona 拆窗（窗口本就单 persona）
- ❌ 每 persona 独立 sqlite db（与"汇总视图"冲突）
- ❌ Personas 表实际填 `bot_persona_name`（persona 是共享实体；只在 impressions/events 上做隔离即可）
- ❌ 多用户 / 协作 / 权限

**关键文件总览**：
- 配置：`_conf_schema.json`、`core/config.py`、`web/frontend/app/config/page.tsx`、`web/frontend/lib/i18n.ts`
- 后端 DB：`migrations/010_persona_isolation_scope.sql`、`core/domain/models.py`、`core/repository/{base,sqlite,memory}.py`
- 后端业务：`core/extractor/extractor.py`、`core/social/orientation_analyzer.py`
- 后端 API：`web/plugin_routes.py`（生产路径）、`web/server.py`（dev/tests 路径）
- 前端：`web/frontend/lib/{store,api,i18n}.ts`、`web/frontend/components/{layout,shared,library}/*.tsx`

---

### Phase 1 — 配置拆分 + 4 个新配置键 (✅ 完成)
- [x] `_conf_schema.json` 把 `relation`（19 字段）拆为 `relation` / `scheduled` / `debug_display` 三组
- [x] `relation` 组内新增 `persona_isolation_legacy_visible` / `persona_merge_audit_enabled` / `persona_default_view_mode` 三键，`persona_isolation_enabled` 默认改为 `true`
- [x] `core/config.py` 加 3 个新 getter property
- [x] `web/frontend/app/config/page.tsx` 同步拆 SECTIONS + 加 FIELD_DEPENDENCIES 联动禁用
- [x] `web/frontend/lib/i18n.ts` 三语 (zh/ja/en) 全部加 section / field 标签

### Phase 2 — 后端 Persona 隔离骨架（向前兼容）(✅ 完成)
- [x] `migrations/010_persona_isolation_scope.sql` — personas 加列；impressions 重建表 + `CREATE UNIQUE INDEX ... ifnull(bot_persona_name, '')`；events 加索引
- [x] `core/domain/models.py` — `Persona.bot_persona_name` / `Impression.bot_persona_name` 字段，默认 None
- [x] `core/repository/sqlite.py` — read/write 路径都处理 bot_persona_name；`ON CONFLICT(...,ifnull(bot_persona_name,''))` 配合新索引；`_safe_get` 兼容旧 row factory
- [x] Smoke test：全 10 migration 干净跑通；Upsert NULL→NULL 覆盖；NULL/Alice/Bob 三行并存；现有 455 tests 全过

### Phase 3 — WebUI Persona 上下文 + API 透传 + 写路径 wiring (✅ 完成)

**Phase 3a — 后端写路径 wiring**
- [x] `core/social/orientation_analyzer.py` — `analyze()` / `_upsert_impression()` 接受 `bot_persona_name`，传给 Impression
- [x] `core/extractor/extractor.py` — 调 analyzer 时透传 `event.bot_persona_name`
- [ ] `core/adapters/identity.py` — 创建 Persona 时填 `bot_persona_name`（**defer**：persona 是共享实体，不必按 bot 隔离；视后续 UI 需求再决定）
- [ ] `core/sync/parser.py` / `core/sync/syncer.py` — Impression 构造传 `bot_persona_name=None`（**defer**：MD 同步是旁路，先不动）

**Phase 3b — 后端 repository 过滤 + API 透传**
- [x] `core/repository/base.py` — `ImpressionRepository.get/list_by_observer/list_by_subject` + `EventRepository.list_all/list_by_group/list_by_status` 加 `bot_persona_name` / `include_legacy` 参数
- [x] `core/repository/sqlite.py` — SQL 用 `(bot_persona_name = ? OR bot_persona_name IS NULL)` 过滤；`_persona_where` helper；`get` 用 `ifnull(bot_persona_name, '') = ifnull(?, '')` 精确匹配
- [x] `core/repository/memory.py` — In-memory 实现 4-tuple key；`_persona_matches` helper
- [x] `web/plugin_routes.py` — `events_data` / `graph_data` 加 `bot_persona_name` kwarg；`_handle_events` / `_handle_graph_guarded` 读 `?persona=` 透传
- [x] `web/plugin_routes.py` — 新增 `_handle_bot_personas_list` + `GET /api/personas/bots` 路由
- [x] `web/server.py` — 同步上述改动（dev/tests 路径）
- [x] 测试：150 tests pass（含 test_webui, test_graph_scope, test_sqlite_repo 等）

**Phase 3 闭合补丁（G1 / G2 / G3 — ✅ 完成）**
- [x] G1: `web/frontend/app/recall/page.tsx` 串 persona — `api.recall.query` 加 4th 参数；前后端两处 `_handle_recall` 加 `?persona=` 读取 + 结果过滤（NULL 或匹配 persona 才保留）
- [x] G2a: `persona_isolation_legacy_visible` 接到后端 `include_legacy` 参数 — `plugin_routes.py` + `server.py` 的 `events_data` / `graph_data` 加 `_persona_iso_enabled` / `_persona_legacy_visible` 两个 property 从 `self._initial_config` 读
- [x] G2b: `persona_isolation_enabled` 主开关 — `store.tsx` 加 `personaConfig: { isolationEnabled, legacyVisible, defaultViewMode, loaded }`，在 auth resolved 后调一次 `/api/config`；`PersonaSelector` 关闭时返回 null；`FirstLaunchPersonaPicker` 关闭时强制 setCurrentPersona(null,'all') + setFirstLaunchDone(true)
- [x] G3: `FirstLaunchPersonaPicker` 按 `persona_default_view_mode` 区分行为 — `remember`(已 done 跳过) / `all`(静默置 'all' 并 done) / `force_pick`(每次弹，确认时不 latch done)
- [x] G2c: `persona_merge_audit_enabled` 已在 Phase 4 接入

**G1/G2/G3 验证**：backend 132 tests pass（webui/graph_scope/sqlite/memory/config_sync）；frontend 49 persona-selector 结构测试 pass。

**Phase 3c — 前端 store + API + UI 组件（✅ 完成 v0.11.2）**
- [x] `web/frontend/lib/store.tsx` — `currentPersonaName` / `scopeMode` / `firstLaunchDone`，localStorage 持久化，纳入 useMemo 依赖
- [x] `web/frontend/lib/api.ts` — `withPersona()` 工具、`BotPersonaItem`、`graph.listBots()`；`events.list` / `events.listArchived` / `graph.get` 接受 `persona?`
- [x] `web/frontend/components/shared/persona-selector.tsx` — 新建，Avatar + Popover 风格，置于 Sidebar 底部
- [x] `web/frontend/components/shared/first-launch-persona-picker.tsx` — 新建，首次进入多 persona 时弹出
- [x] `web/frontend/components/layout/app-shell.tsx` — 挂 FirstLaunchPersonaPicker
- [x] `web/frontend/components/layout/app-sidebar.tsx` — 底部嵌入 PersonaSelector
- [x] events/library/graph/stats 各 page — `personaFilter` 透传给 api，纳入 useCallback deps
- [x] `web/frontend/lib/i18n.ts` — `personaSelector` 分区，zh/en/ja 三语全部添加
- [x] 测试：`tests/frontend/test_persona_selector.py` 49 个结构验证测试全部通过

#### Phase 3c 技术实现（交接细节）

**1. Store 扩展** — [`web/frontend/lib/store.tsx`](web/frontend/lib/store.tsx)

```ts
// AppState 加：
currentPersonaName: string | null   // 选中的 bot persona；null 仅在 scopeMode='all' 时合法
scopeMode: 'single' | 'all'         // 区分 "选了具体 persona" vs "选了汇总"
firstLaunchDone: boolean             // 是否已经过过首次 picker

// AppActions 加：
setCurrentPersona: (name: string | null, mode: 'single' | 'all') => void
setFirstLaunchDone: (done: boolean) => void
```

localStorage keys（沿用 `getStored` / `setStored` 工具）：
- `em_current_persona_name` — string 或 ""（空 = null）
- `em_persona_scope_mode` — `'single'` / `'all'`
- `em_first_launch_done` — `'1'`

初始化：在 AppProvider 顶部 `useState(() => getStored(...))` 三个 state；setter 同步写 localStorage。
**重要**：把这三个 state 纳入 `ctx` 的 useMemo 依赖，否则切换时不会触发下游 useEffect。

**2. API 层** — [`web/frontend/lib/api.ts`](web/frontend/lib/api.ts)

```ts
// 工具：拼 persona query
function withPersona(url: string, persona: string | null | undefined): string {
  if (!persona) return url
  const sep = url.includes('?') ? '&' : '?'
  return `${url}${sep}persona=${encodeURIComponent(persona)}`
}

// 改造 events.list（保持向后兼容签名）：
events.list = (limit = 500, persona?: string | null) =>
  request<EventsResponse>(withPersona(`/api/events?limit=${limit}`, persona))

// 同样改：events.listArchived(persona?) / events.recycleBin(persona?) / graph.get(persona?)

// 新增：
personas.listBots = () =>
  request<{ items: { name: string | null; event_count: number }[] }>('/api/personas/bots')
```

**3. PersonaSelector** — `web/frontend/components/shared/persona-selector.tsx`（新建）

用 shadcn `Select`（不需要搜索）。Props 接受 `compact?: boolean` 控制 sidebar vs page header 样式。

```tsx
export function PersonaSelector({ compact = false }: { compact?: boolean }) {
  const { i18n, currentPersonaName, scopeMode, setCurrentPersona } = useApp()
  const [bots, setBots] = useState<{ name: string | null; event_count: number }[]>([])
  
  useEffect(() => {
    api.personas.listBots().then(r => setBots(r.items))
  }, [])
  
  const value = scopeMode === 'all' ? '__all__' : (currentPersonaName ?? '__legacy__')
  
  const handleChange = (v: string) => {
    if (v === '__all__') setCurrentPersona(null, 'all')
    else if (v === '__legacy__') setCurrentPersona(null, 'single')
    else setCurrentPersona(v, 'single')
  }
  
  return (
    <Select value={value} onValueChange={handleChange}>
      <SelectTrigger className={compact ? 'h-8 text-xs' : ''}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="__all__">{i18n.persona.allPersonas}</SelectItem>
        <SelectItem value="__legacy__">{i18n.persona.defaultLegacy}</SelectItem>
        {bots.filter(b => b.name).map(b => (
          <SelectItem key={b.name!} value={b.name!}>{b.name} ({b.event_count})</SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
```

**4. FirstLaunchPersonaPicker** — `web/frontend/components/shared/first-launch-persona-picker.tsx`（新建）

```tsx
export function FirstLaunchPersonaPicker({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { i18n, setCurrentPersona, setFirstLaunchDone } = useApp()
  const [bots, setBots] = useState<{ name: string | null; event_count: number }[]>([])
  useEffect(() => { if (open) api.personas.listBots().then(r => setBots(r.items)) }, [open])
  
  const pick = (name: string | null, mode: 'single' | 'all') => {
    setCurrentPersona(name, mode)
    setFirstLaunchDone(true)
    onClose()
  }
  
  return (
    <Dialog open={open} onOpenChange={() => {/* 不允许 esc 关闭 */}}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{i18n.persona.firstLaunchTitle}</DialogTitle>
          <DialogDescription>{i18n.persona.firstLaunchDesc}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          {bots.filter(b => b.name).map(b => (
            <Button key={b.name!} variant="outline" onClick={() => pick(b.name!, 'single')}>
              {b.name} <Badge variant="secondary">{b.event_count}</Badge>
            </Button>
          ))}
          <Separator />
          <Button variant="ghost" onClick={() => pick(null, 'all')}>{i18n.persona.viewAll}</Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
```

**5. AppShell 挂 modal** — [`web/frontend/components/layout/app-shell.tsx`](web/frontend/components/layout/app-shell.tsx)

```tsx
const { authenticated, firstLaunchDone } = useApp()
const [pickerOpen, setPickerOpen] = useState(false)

useEffect(() => {
  if (!authenticated) return
  if (firstLaunchDone) return
  const mode = pluginConfigValues.persona_default_view_mode || 'remember'
  if (mode === 'all') {
    setCurrentPersona(null, 'all')
    setFirstLaunchDone(true)
  } else if (mode === 'force_pick' || mode === 'remember') {
    setPickerOpen(true)
  }
}, [authenticated, firstLaunchDone])

// 渲染：
<FirstLaunchPersonaPicker open={pickerOpen} onClose={() => setPickerOpen(false)} />
```

注意 `force_pick` 模式下每次启动都弹（不 setFirstLaunchDone）。`remember` + 已有 currentPersonaName 时跳过弹窗。

**6. Sidebar 嵌入** — [`web/frontend/components/layout/app-sidebar.tsx`](web/frontend/components/layout/app-sidebar.tsx)

在品牌 logo 下方加 `<PersonaSelector compact />`，建议放在 sidebar header / `SidebarGroup` 顶部 padding 区域。

**7. Page 级 useEffect wiring**

每个 page 改造模式（以 events 为例）：

```tsx
const { currentPersonaName, scopeMode, ... } = useApp()
const personaParam = scopeMode === 'all' ? null : currentPersonaName

const loadEvents = useCallback(async () => {
  const data = await api.events.list(1000, personaParam)
  setRawEvents(data.items)
}, [setRawEvents, appToast, i18n.events.loadError, personaParam])

useEffect(() => { loadEvents() }, [loadEvents])
```

需要改的 page：
- [`web/frontend/app/events/page.tsx`](web/frontend/app/events/page.tsx) — events.list / listArchived / recycleBin
- [`web/frontend/app/library/page.tsx`](web/frontend/app/library/page.tsx) — events.list
- [`web/frontend/app/graph/page.tsx`](web/frontend/app/graph/page.tsx) — graph.get
- [`web/frontend/app/recall/page.tsx`](web/frontend/app/recall/page.tsx) — events.list（作为补充检索）
- [`web/frontend/app/stats/page.tsx`](web/frontend/app/stats/page.tsx) — stats 暂不带 persona（先确认 stats 是否需要隔离；本期 defer）

**8. i18n 文案** — [`web/frontend/lib/i18n.ts`](web/frontend/lib/i18n.ts) — 三个 locale 各加：

```ts
persona: {
  allPersonas: '全部 Persona' / 'All Personas' / 'すべてのペルソナ',
  defaultLegacy: '默认 (旧数据)' / 'Default (Legacy)' / 'デフォルト (旧データ)',
  firstLaunchTitle: '选择要查看的 Bot Persona',
  firstLaunchDesc: '不同的 Bot Persona 拥有独立的记忆视图。可随时在 Sidebar 顶部切换。',
  viewAll: '先看全部记忆',
  currentScope: '当前作用域',
}
```

**9. 陷阱 / 注意事项**

- **app context 引用稳定性**：因为 stats 轮询每次都会让 `ctx` object 引用变（参见 `commit af0c3e4`），page 里写 `useCallback(..., [app, ...])` 会导致每次轮询都重 fetch。**必须**解构出稳定回调和稳定值：`const { currentPersonaName, scopeMode, setRawEvents, toast: appToast } = useApp()`，依赖里只列这些原子值。
- **PersonaSelector 自身的 listBots 调用**：仅在 mount 时调一次；切换 persona 后不需要 refetch 列表（除非用户合并了 persona — 那是 Phase 4 的责任）。
- **API 层向后兼容**：persona 参数永远是可选第二个参数；旧调用点不传等同于 `null = 不过滤`。
- **首次 picker 显示时机**：必须等 `authenticated === true && !authLoading`，否则会闪一下登录 → picker → 内容。
- **"汇总视图"和"遗留视图"的区分**：
  - `scopeMode='all'` → 不带 `?persona=` → 后端返回所有数据（包括所有 bot persona 的 + NULL 的）
  - `scopeMode='single'` + `currentPersonaName=null` → 带 `?persona=`？这里有歧义。建议：`single + null` 表示"只看 legacy NULL 行"，对应"默认 (旧数据)"选项。前端在 query 里发 `?persona=` 不带值或专门拼一个特殊 token？**最安全做法**：API 层把 `null` 的 persona 翻译成不带 query（=后端返汇总），由前端 `scopeMode` 决定语义。Phase 4 加合并后这里要重看。

**10. 验证步骤**

1. `npm install && npm run build && python tools/sync_frontend.py -f`
2. 启动后端，打开 WebUI
3. 首次进入：弹 picker → 选一个 persona → 进入只显示该 persona 数据的视图
4. Sidebar 顶部切到"全部 Persona" → 数据汇总显示
5. devtools Network 面板：选了 persona 时 `/api/events` 带 `?persona=Alice`
6. 刷新页面：选项保持不变（localStorage 起效）
7. 配置页关闭 `persona_isolation_enabled`：刷新后**不**弹 picker，全部使用汇总视图

### Phase 4 — Persona 合并 / 转移 (✅ 完成)
- [x] 后端 `core/repository/sqlite.py` 加 `preview_bot_persona_merge` / `merge_bot_persona` 共享工具 — 事务内 DELETE 冲突 impressions + UPDATE events/impressions/personas (target wins 策略)
- [x] 后端 `POST /api/personas/merge` body `{src, target, mode}` — `plugin_routes.py` + `server.py` 双服务实现，包 `sudo` wrap
- [x] 后端 `GET /api/personas/merge/preview?src=&target=&mode=` — 返回 4 项 counts
- [x] 支持 `__legacy__` / NULL 作为 source 或 target；支持 `mode=all|impressions_only`
- [x] 接 `persona_merge_audit_enabled`：写 `data_dir/audit/persona_merge.jsonl`（每行 JSON）
- [x] `web/frontend/lib/api.ts` — `graph.mergePersonas(src, target, mode)` + `graph.mergePersonasPreview(src, target, mode)` + `PersonaMergePreview` 接口
- [x] `web/frontend/components/config/persona-ownership-manager.tsx` — 配置页归属管理入口（source/target 支持 legacy、自定义；preview + 二次确认 + sudo gate）
- [x] `PersonaSelector` 保持纯全局数据域切换，不再承载破坏性迁移操作
- [x] 合并后：如当前数据域等于 source，自动切到 target；刷新 bots 列表
- [x] `web/frontend/lib/i18n.ts` 三语 (zh/ja/en) 加归属管理文案 / 4 项 stat label / 二次确认提示
- [x] 测试 `tests/test_persona_merge.py` — 覆盖 happy path / target wins 冲突 / personas re-key / preview 一致性 / 空 src no-op / legacy→named / named→legacy / impressions-only

**修复的 Phase 2 遗漏**：`_EVENT_COLS` 漏了 `bot_persona_name` 列（SELECT 时不读但 `_row_to_event` 期望读，导致 list_all 返回的 events 永远是 `bot_persona_name=None`）— 在 Phase 4 测试中暴露并修复

**验证**：backend tests pass；frontend structure tests / lint / typecheck pass

#### Phase 4 技术实现（交接细节）

**1. URL 设计取舍**

合并的 src / target 是**字符串**（bot_persona_name），可能含中文、空格、特殊字符。`POST /api/personas/{src}/merge/{target}` 这种 path 参数对 URL-encode 友好但容易出问题。**推荐**：

```
POST /api/personas/merge        body: { src: "Alice", target: "Bob" }
GET  /api/personas/merge/preview?src=Alice&target=Bob
```

更易传非 ASCII，也更符合"动作"语义。

**2. 后端 — 关键 SQL** ([`web/plugin_routes.py`](web/plugin_routes.py))

合并 impressions 的难点：`UNIQUE(observer, subject, scope, ifnull(bot_persona_name, ''))` 索引会在 src→target 改名时和 target 已有的行冲突。

策略：**target wins**（保留 target 已有的行，丢弃 src 中冲突的行）

```sql
-- Step 1: 删除 src 中和 target 已有行冲突的 impressions
DELETE FROM impressions
WHERE bot_persona_name = :src
  AND EXISTS (
    SELECT 1 FROM impressions t
    WHERE t.observer_uid = impressions.observer_uid
      AND t.subject_uid = impressions.subject_uid
      AND t.scope = impressions.scope
      AND ifnull(t.bot_persona_name, '') = ifnull(:target, '')
  );

-- Step 2: 把剩余的 src 行改名为 target
UPDATE impressions SET bot_persona_name = :target WHERE bot_persona_name = :src;

-- Step 3: events 不存在冲突（PK 是 event_id），直接 update
UPDATE events SET bot_persona_name = :target WHERE bot_persona_name = :src;

-- Step 4: personas 同上（PK 是 uid）
UPDATE personas SET bot_persona_name = :target WHERE bot_persona_name = :src;
```

整个流程必须在**单个事务**内，用 `_txn(self._db, self._lock)` 包住。

**3. 路由注册**

```python
(f"/api/personas/merge",         self._handle_persona_merge_guarded,  ["POST"], "Merge persona A → B"),
(f"/api/personas/merge/preview", self._handle_persona_merge_preview,  ["GET"],  "Preview merge impact"),
```

合并要 sudo 模式，包 `self._wrap("sudo", ...)`。

**4. 陷阱 / 注意**

- **src / target 校验**：必须不相等、必须非空；允许不在 `/api/personas/bots` 返回列表里的自定义 `bot_persona_name`
- **legacy 语义**：前端用 `__legacy__`，后端转成 SQL `IS NULL`；不要用空字符串表示 legacy
- **AstrBot 端 personas 表的 `(platform="internal", physical_id="bot")` 绑定**：合并 personas 表中的 bot persona 后，相应的 identity_binding 也要 reattach 到 target uid。否则后续 `_get_bot_persona()` 可能找不到 bot
- **审计日志位置**：`data_dir/audit/`，确保 `parent.mkdir(parents=True, exist_ok=True)`
- **回滚**：当前方案无回滚（事务提交后不可逆）。如果担心，可以在事务前先备份 db 文件

### Phase 5 — 登录界面 polish (✅ 完成)
- [x] 右侧表单加 `radial-gradient` 背景光晕 — 用 `color-mix(in srgb, var(--color-primary) 7%, transparent)` 椭圆径向；input 失焦时 opacity 0.55，聚焦时 1.0，700ms 过渡
- [x] 密码 input 聚焦时丝线动画提速 1.5× — 加 `.thread-accent.silk-fast { animation-duration: 4.6s; stroke-width: 0.9 }`；React `passwordFocused` state 控制 className
- [x] 错误提示加 `slide-in-from-top-2 fade-in` + 红色脉冲 — `key={error}` 强制重挂载使动画每次重放；`AlertCircle` 图标 `animate-pulse`
- [x] 提交加载态加渐进文案 `login.verifying` 三语 — zh "验证中…" / en "Verifying…" / ja "認証中…"；按钮内 `Loader2` 旋转图标 + 文案；按钮加 `active:scale-[0.99]` + `disabled:opacity-60`
- [x] 品牌 logo 微悬浮（仅桌面）— h1 加 `transition-transform duration-500 hover:-translate-y-0.5`（位于 `hidden md:flex` 左面板内，仅桌面生效）
- [x] 验证：483 backend tests pass、49 frontend structure tests pass

### Phase 6 —"全 Persona 主界面"图谱 (✅ 完成)
- [x] graph 在 `scopeMode === 'all'` 时把每个 bot persona 渲染为超级节点（前端展示层聚合，不新增核心数据模型）
- [x] 点击超级节点下钻到该 persona 的子图（通过全局 persona store 切换到 `single` scope 后重新加载图谱）
- [x] 修复 legacy/default persona 查询歧义：前端用 `__legacy__` token，后端映射为仅查询 `bot_persona_name IS NULL`

### 主动 defer / 不在范围
- ❌ Partitioner 按 bot_persona 拆窗（实测窗口本就单 persona，价值低，不做）
- ❌ 每 persona 独立 sqlite db（与"汇总主界面"诉求冲突，本次走行级方案）
- ❌ 多用户 / 协作 / 权限模型

---

## 后端架构优化与演进（参考记录）

### ✅ [设计] 叙事轴摘要向量化与分层 RAG（已实现）
- `events.event_type` 列区分 `episode` / `narrative`
- 每日摘要生成后自动写入 narrative Event 并向量化
- `RecallManager` 按关键词分类器（macro/micro/both）分层检索，`formatter.py` 按类型分段输出

### ✅ [性能] 周期性维护任务合并（已实现）
- `run_consolidated_maintenance()` 合并两个任务，共享一次全量 Persona 扫描和事件预加载
- 当 `persona_synthesis_enabled` 和 `relation_enabled` 均为 true 时，自动注册合并任务

### ✅ [质量] 语义提取策略预筛选（已实现）
- `core/extractor/noise_filter.py`：规则过滤纯表情包、极短消息、复读消息
- 在 `semantic` 策略的 DBSCAN 分段后、LLM 蒸馏前应用

### ✅ [架构] SSOT 边界（部分，待持续维护）
- DB 是唯一事实源；MD 文件是只读投影
- 仅 `IMPRESSIONS.md` 允许反向同步，其他文件禁止反向同步

### ✅ [功能] 插件多语言支持（i18n）（已完成）
在 `.astrbot-plugin/i18n/` 下创建 `zh-CN.json` 和 `en-US.json`，覆盖 `metadata.yaml` 的 `display_name`、`desc`，以及 `_conf_schema.json` 所有字段的 `description`、`hint`、`labels`。

### ✅ [功能] 前端对于 archived 事件的相关管理显示和支持功能（基础能力完成）
- [x] `/api/archived_events` 列表
- [x] `/api/events/{event_id}/archive` 手动归档
- [x] `/api/events/{event_id}/unarchive` 恢复为活跃
- [x] Events / Library 页面归档事件弹窗与恢复入口

### ✅ [可选优化] `run_memory_cleanup` 同轮归档/硬删语义（已修复）
`core/tasks/cleanup.py` 现在先删除进入本轮前已经超过保留期的 archived 事件，再归档本轮新发现的低显著度 active 事件。新增回归测试覆盖该场景。
