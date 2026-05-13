# CHANGELOG

# CHANGELOG

## [v0.9.8] — 2026-05-13

### WebUI 双端口架构 + `/mrm webui on` 修复

**修复 "WebUI 模块未加载"**
- `core/plugin_initializer.py`：去掉 `WebuiServer` 构造的 `webui_standalone_debug` 门控——只要 `webui_enabled=True`（默认），始终构造 `WebuiServer` 实例；`webui_standalone_debug` 仅控制是否在插件启动时自动调用 `start()`。
- `/mrm webui on/off` 命令现在始终可用，不再返回"模块未加载"。

**修复独立服务器静态文件路径**
- `web/server.py`：将 `_STATIC_DIR` 从 `web/frontend/output/` 更新为 `pages/moirai/`，与 Phase 2 构建产物迁移保持一致。独立服务器和 AstrBot Plugin Pages 共用同一份构建产物。

**双端口架构说明**
- AstrBot Plugin Pages（`/api/plug/moirai/*`）：始终注册，由 AstrBot 管理端口和鉴权。
- 独立 aiohttp 服务器（`cfg.webui_port`，默认 2655）：由用户通过 `/mrm webui on/off` 手动控制，适合局域网直连访问，无额外鉴权。

## [v0.9.7] — 2026-05-12

### 配置层级化 (Config Schema Hierarchy)

- 重构 `_conf_schema.json`：将原有 64 个平铺字段按功能组织为 10 个嵌套 `object` 分组（`general` / `webui` / `embedding` / `retrieval` / `vcm` / `soul` / `cleanup` / `summaries` / `boundary` / `relation`），与 AstrBot 原生配置 UI 的分组渲染机制对齐，消除无层级的平铺列表。
- 修改 `core/config.py` `PluginConfig.__init__`：在构造时对 AstrBot 传入的原始 dict 执行单层展平，将嵌套 group dict 合并到统一命名空间，所有现有平铺键名访问器（`_get` / `_int` / `_bool` 等）无需改动，同时保持对旧版平铺配置的向后兼容。

## [v0.9.6] — 2026-05-13

### WebUI 阶段 2–4：前端构建适配、API 适配层、启动自动构建

**阶段 2 — 前端构建适配** (`web/frontend/next.config.mjs`)
- 将 `distDir` 从 `'output'`（`web/frontend/output/`）改为 `'../../pages/moirai'`，构建产物直接输出至仓库根目录 `pages/moirai/`，符合 AstrBot Plugin Pages 标准。
- `output: 'export'`、`trailingSlash: true` 及 dev 模式 rewrites 保持不变。Next.js App Router 静态导出为每个路由生成独立 `index.html`，AstrBot 无需做 SPA fallback。

**阶段 3 — API 适配层** (`web/frontend/lib/api.ts`)
- 新增 `Window.AstrBotPluginPage` 全局类型声明。
- 新增 `_resolveUrl(url)` 函数：检测 `'AstrBotPluginPage' in window`，若在 AstrBot iframe 中则将 `/api/X` 重写为 `/api/plug/moirai/X`；否则原路返回（本地调试双路径兼容）。
- `request()` 函数改为向 `_resolveUrl(url)` 发起请求，其余逻辑（credentials、headers、error handling）不变。

**阶段 4 — 启动自动构建** (`core/plugin_initializer.py`)
- 新增 `_ensure_pages_built()` 方法：检测 `pages/moirai/index.html` 是否存在，不存在时自动执行 `npm install && npm run build`（移植自 `web/server.py` 的同名逻辑）。
- 在 `initialize()` 中于 `plugin_routes.register(context)` 之前调用，确保面板文件就绪后再注册路由。

**文档更新**
- 更新 `web/README.md`、`CLAUDE.md` 中的构建产物路径引用（`web/frontend/output/` → `pages/moirai/`）。


## [v0.9.6] — 2026-05-13

### WebUI 阶段一：接入 AstrBot Plugin Pages 后端迁移

**后端路由迁移**
- 新增 `web/plugin_routes.py`：提取 `WebuiServer` 中所有 API handler 到独立的 `PluginRoutes` 类，通过 `context.register_web_api()` 批量注册到 AstrBot，路由挂载于 `/api/plug/moirai/`。
- 修改 `core/plugin_initializer.py`：默认使用 `PluginRoutes.register(context)` 代替启动独立 `aiohttp` server；保留 `WebuiServer` 作为本地调试入口（需设置 `webui_standalone_debug: true`）。
- 修改 `web/registry.py`：解耦 `RouteHandler` 类型对 `aiohttp` 的硬依赖，`PanelRegistry` 的注册接口保持不变，兼容未来系列插件挂载子面板的需求。
- 修改 `main.py`：`webui_registry` property 优先返回 `plugin_routes.registry`，回退到 `webui.registry`（调试模式）。

**前端 Auth 层移除**（鉴权交由 AstrBot 统一管理）
- 移除 `app-shell.tsx` 中的登录屏幕门控逻辑，应用直接渲染。
- 简化 `lib/store.tsx`：移除 auth 状态（`authEnabled`、`authenticated`、`passwordSet`、`sudoGuard*`）及相关 API 轮询；`sudo` 始终为 `true`。
- 重写 `app/settings/page.tsx`：移除「认证」和「Sudo」配置卡片，保留语言、主题、第三方面板三个区块。
- 重写 `components/layout/app-sidebar.tsx`：移除 sudo 切换按钮、密码对话框、退出登录按钮。
- 修改 `lib/api.ts`：移除 `auth` namespace（`login`、`logout`、`sudo`、`changePassword` 等接口）。

## [v0.9.5] — 2026-05-13

### 视觉样式优化 (Visual Style Optimization)

- **字体去衬线化**：移除了「插件配置」页面和「设置」页面中标题与卡片标题的 `font-serif` 衬线字体类，恢复为默认的非衬线字体，使界面整体视觉风格更加统一现代。
- **PageHeader 更新**：移除了全局 `PageHeader` 组件中的衬线字体设置。

## [v0.9.4] — 2026-05-13

### 设置页面优化 (Settings Page Optimization)

- **新增页面导览组件**：在「设置」页面引入了 `OnThisPage` 导览组件，支持随滚动自动高亮当前区域，提升长页面的导航体验。
- **布局重构**：将设置页面的卡片式布局调整为与「插件配置」页面一致的双栏结构，在宽屏下显示右侧导览栏。
- **Scroll Spy 集成**：为设置页面的各个主要配置卡片（语言、主题、认证、Sudo、第三方）添加了 ID 锚点，并集成了基于 Intersection Observer 的滚动监听逻辑。

## [v0.9.3] — 2026-05-13

### Library 页面组件重构与视觉优化

- **新增 `components/library/persona-row.tsx`**：将人格行+详情面板提取为独立组件，采用与 `event-row.tsx` 一致的设计语言（MetaItem 网格、大五人格进度条可视化、左边框颜色标记）。
- **新增 `components/library/group-row.tsx`**：将群组行+详情面板提取为独立组件，`GroupInfo` 类型从页面移入组件层，支持平台徽章、参与者列表展示。
- **重构 `app/library/page.tsx`**：移除所有内联子组件（`PaginationFooter`、`PersonaDetailRow`、`EventDetailRow`、`GroupDetailRow`），改为引用 `components/library/` 下的独立组件；统一表头样式变量 `tableHeadCls`；i18n 覆盖删除确认文案。

## [v0.9.2] — 2026-05-12

### 品牌与外观更新 (Branding & Visual Updates)

- **插件 Logo**：在插件根目录添加 `logo.png`，AstrBot 插件列表现在可显示插件图标。
- **英文显示名称更新**：en_US `display_name` 由 "Moirai Worldline" 改为 "Moirai Memory Plugin"，更直观地传达插件用途。
- **主题重命名**：
  - Aurora 主题（薰衣草紫 + 金色调色板）重命名为 **Moirai**，成为插件默认配色方案（CSS 选择器 `.theme-moirai`）。
  - 原 Moirai 主题（标准灰度）重命名为 **Nox**，新增 `nox.css`，占据原 Aurora 在主题选择器中的位置。
- **globals.css 更新**：新增 `@import "../styles/themes/nox.css"`。
- **前端landing page和stat page设计更新**: 组件重构，设计语言更新。
- **统计页面 UI 细节修复 (Stats Page UI Fixes)**：修复了在无性能数据时平均响应时间显示为 `—s` 的异常（现显示为 `—`），并为“近 30 日活跃趋势”卡片增加了 `h-full` 属性以确保对齐。

## [v0.9.1] — 2026-05-12

### /mrm 指令三语国际化 (/mrm Command i18n)

- **新增 `/mrm language <cn/en/ja>` 指令**：允许管理员在聊天框内一键切换所有 `/mrm` 指令响应的显示语言（简体中文 / English / 日本語）。
- **语言偏好持久化**：语言设置保存于 `data_dir/.cmd_lang` 文件，重启后自动恢复；首次启动默认继承插件全局 `language` 配置项。
- **全量三语翻译**：在 `core/utils/i18n.py` 中为所有 `/mrm` 命令响应新增 `cmd.*` 键组，覆盖 status、persona、soul、recall、flush、webui、run、reset 系列及 help 全文，三种语言均已完整翻译。
- **`_t()` 包装器**：`CommandManager` 使用统一的 `_t(key, **kwargs)` 方法替代所有硬编码字符串，便于后续语言扩展。
- **大五人格维度名称本地化**：persona 档案中的 O/C/E/A/N 维度标签随语言切换（开放性/Openness/開放性 等）。

## [v0.9.0] — 2026-05-12

### /mrm 指令集重构与扩展 (Command Set Refactor & Expansion)

- **新增信息查询指令**：
  - `/mrm persona <PlatID>`：查看指定用户的人格档案（description + BigFive 百分比 + evidence）；通过当前平台 + 平台 ID 定位用户。
  - `/mrm soul`：查看当前会话的四维情绪状态（recall_depth / impression_depth / expression_desire / creativity），各维度显示 +N/20 偏高/偏低/中立标注。
- **新增重置指令系列（均需二次确认）**：
  - `/mrm reset here`：删除当前群所有事件记录及 summaries 目录下的摘要文件。
  - `/mrm reset event <group_id>`：删除指定群组的事件记录与摘要文件。
  - `/mrm reset event all`：删除所有事件记录（保留人格数据）。
  - `/mrm reset persona <PlatID>`：删除指定用户的人格档案。
  - `/mrm reset persona all`：删除全部人格档案。
  - `/mrm reset all`：清空全部插件数据（事件、人格、所有投影文件）。
- **二次确认机制**：所有 reset 命令首次触发时返回警告，30 秒内再次发送相同命令才执行；超时自动失效。
- **Repository 新增批量删除接口**：`EventRepository` 新增 `delete_by_group(group_id)` 和 `delete_all()` 抽象方法，并在 SQLite 和 in-memory 两个实现中补全（同步清理 vec 表）。
- **指令帮助更新**：`/mrm help` 按信息查询 / 操作 / 重置 / 其他四组重新分类展示，重置组加 ⚠️ 标注。

## [v0.8.3] — 2026-05-12

### 性能瓶颈分析增强 (Performance Bottleneck Analysis)

- **环状图对比视图 (Unified Donut Chart)**：重构了统计页面的性能分析模块，引入环状图将所有核心任务与后台任务进行统一对比，帮助用户直观识别系统瓶颈。
- **全环节计时补全 (Full Task Timing)**：为“人格合成”、“叙事摘要”、“记忆清理”和“重索引”等所有异步后台任务增加了计时器，填补了性能监控的盲区。
- **计时单位标准化 (Seconds-based Timing)**：将界面上的性能耗时展示单位从毫秒 (ms) 统一调整为秒 (s)，更符合长时间任务的观测习惯。
- **UI 布局优化**：移除了选项卡切换，改为侧边栏明细列表与环状图联动的布局，并增加了“瓶颈环节”高亮提示。

## [v0.8.2] — 2026-05-12

### 统计可视化深度重构 (Deep Stats Visualization Redesign)

- **十项性能全指标覆盖**：重构了数据统计页面，将核心流水线（响应、召回、上下文注入）与异步后台任务（边界检测、情节提取、总结提炼）进行逻辑分组展示。
- **召回链路瀑布流分析**：在“核心流水线”卡片中集成了召回阶段的 Breakdown 可视化，通过进度条直观展示向量搜索、重排序、邻居扩展和注入准备的耗时比例。
- **叙事轴深度指标**：新增了“平均摘要长度”统计，通过后端实时计算 Markdown 文件的字符规模，量化叙事记忆的丰富程度。
- **UI 组件升级**：引入 `Tabs` 切换核心/后台任务视图，使用 `Badge` 高亮平均耗时，并通过 `Separator` 优化布局密度，提升数据洞察的直观性。
- **类型系统增强**：在 `PluginStats` 定义中补全了叙事轴相关字段，确保前后端数据交换的严格一致性。

## [v0.8.1] — 2026-05-12

### 统计与性能监控增强 (Enhanced Statistics & Performance Monitoring)

- **响应时长追踪 (Response Time Tracking)**：在 `EventHandler` 中增加了对 LLM 请求处理全周期的计时（`response` 阶段），填补了前端概览页长期显示为 0 的空白。
- **性能细节洞察 (Detailed Perf Breakdown)**：后端 API 现在提供 `avg_ms` 和 `last_hits` 等高精度数据。前端 Stats 页面新增了“召回细分阶段”显示，支持查看向量搜索、重排序、邻居扩展和注入准备的各自耗时。
- **叙事记忆统计 (Narrative Axis Stats)**：在统计面板顶层新增了“叙事摘要”总数统计，通过文件系统自动扫描已生成的每日总结文件，平衡了记忆三轴（情节、社交、叙事）的数据展示。
- **数据一致性重构 (Stats Logic Refactoring)**：将 WebUI 的统计逻辑从 `web/server.py` 迁移并整合至 `core/api.py`，统一了统计口径并支持跨组件复用。
- **TypeScript 类型补全 (Frontend Type Safety)**：更新了前端 API 类型定义及全局 Store，确保新增统计项在构建时的类型安全。

## [v0.8.0] — 2026-05-12

### 全局 LLM 任务队列与并发管理 (Global LLM Task Queue & Concurrency Management)

- **全局 LLM 任务调度 (Global LLM Task Manager)**：引入了 `LLMTaskManager` 作为全插件后台 LLM 任务的统一入口。通过集中式信号量（Semaphore）控制瞬时并发压力，防止在多群组并发事件关闭或大规模背景任务运行时击穿 LLM Provider。
- **并发配置项 (Configurable LLM Concurrency)**：新增 `llm_concurrency` 配置项（默认为 2），用户可根据 Provider 的频控限制灵活调整插件的后台负载。
- **多组件集成 (System-wide Integration)**：重构了 `EventExtractor`、`run_persona_synthesis`（人设合成）、`run_group_summary`（群组总结）以及 `BigFiveScorer`（社交分析），所有后台文本生成任务现在均通过全局队列调度。
- **可观测性增强 (Observability)**：`LLMTaskManager` 提供实时统计接口，支持追踪活动任务数、总调用次数及失败率，为后续 WebUI 监控看板奠定了基础。


## [v0.7.38] — 2026-05-12

### 关系图 UI 组件化与样式重构 (Graph UI Componentization & Styling Refactor)

- **UI 组件抽离 (Custom UI Components)**：将关系图中的节点和边提取为独立的 `GraphNode` 和 `GraphEdge` 组件，存放于 `components/ui/custom/` 下。符合 shadcn/ui 的设计哲学，提升了代码的可维护性和复用性。
- **CSS 驱动的视觉效果 (CSS-Driven Visuals)**：
    - 移除了硬编码的颜色值，全面改用 CSS 变量（如 `var(--primary)`）和 Tailwind 类进行样式控制。
    - **独立悬停反馈 (Distinct Hover Feedback)**：为节点和边实现了独立的悬停效果。节点在悬停时会平滑放大，边在悬停时会应用主色调（Primary Color）的高亮和发光效果，提供了更直观的交互体验。
    - **主题一致性 (Theme Consistency)**：高亮颜色现在会自动适配系统的 shadcn 主题色，确保关系图与 WebUI 整体视觉风格严丝合缝。
- **性能优化 (Performance)**：通过组件化减少了 `NetworkGraph` 的渲染复杂度，并优化了 SVG 元素的过渡动画性能。

## [v0.7.37] — 2026-05-12

### 关系图交互体验升级 (Relationship Graph Interaction Upgrade)

- **边对悬停与选中视觉增强 (Edge Hover & Selection Visuals)**：
    - 为关系图中的边（印象）增加了专用的悬停（Hover）状态。悬停或选中边时，边会变为明亮的琥珀色（Amber），并增加线宽，同时显示半透明的“发光”外廓，显著提升了交互反馈的清晰度。
    - **联动高亮 (Linked Highlighting)**：悬停某条边时，其连接的两个节点也会同步进入高亮状态，帮助用户快速识别关系双方。
    - **焦点逻辑优化 (Focus Logic)**：优化了 `NetworkGraph` 的焦点判定逻辑，使得通过边进行的交互能产生与节点交互一致的视觉深度效果。

## [v0.7.36] — 2026-05-12

### 统一总结优化与 i18n 增强 (Unified Summary & i18n Enhancement)

- **统一总结优化 (Unified Summary Optimization)**：在 `mood_source` 设置为 `llm` 时，将“话题总结”与“情感动态分析”合并为单次 LLM 调用。减少了 50% 的 LLM 请求次数，显著提升了群组总结任务的执行效率。
- **i18n 鲁棒性增强 (i18n Robustness)**：优化了 IPC 社交取向标签的国际化逻辑，增加了对自定义 LLM 输出的兼容性，并修复了 `ipc.unknown` 等键位的缺失问题。
- **测试框架完善 (Test Suite Fixes)**：修复了 `tests/test_summary_mood.py` 中的 Mock 逻辑与导入错误，确保其与新的统一提取策略完全兼容。

### 性能深度优化 (Deep Performance Optimization)

- **单任务内部并行化 (Intra-task Parallelization)**：在生成群组摘要时，现在并行执行“话题总结”与“情感动态分析”两个 LLM 请求。对于 local LLM (如 Gemma 26B)，单个群组的生成耗时理论上可缩短 50%。
- **路由器任务同步 (Router Task Synchronization)**：`MessageRouter.flush_all` 现在会等待所有后台 Embedding 任务完成后再关闭窗口。这确保了在 `run_realtime_dev.py` 等快速注入场景下，`EventExtractor` 能 100% 复用已有的向量，避免重复编码。
- **开发工具批处理优化 (Dev Tool Batching)**：`run_realtime_dev.py` 现在使用 `EmbeddingManager` 包裹 Encoder。配合 Router 的后台异步化，消息注入过程实现了真正的透明批处理，极大地提升了 CPU/GPU 利用率并降低了切分延迟。

## [v0.7.34] — 2026-05-12

### 任务系统并发优化 (Task System Concurrency Optimization)

- **人格合成并发化 (Parallel Persona Synthesis)**：`run_persona_synthesis` 现在使用 `asyncio.gather` 并发执行 LLM 请求，并引入 `Semaphore` 控制并发数。新增活动状态检查，跳过无新事件的人格，大幅缩短任务耗时。
- **群组摘要并发化 (Parallel Group Summary)**：`run_group_summary` 现在并发生成群组摘要，显著提升了每日总结任务的执行效率。

## [v0.7.33] — 2026-05-12

### 性能优化与架构重构 (Performance Optimization & Architecture Refactoring)

- **全链路向量复用 (Single-pass Encoding)**：彻底重写了话题漂移检测与事件切分的底层逻辑。消息现在仅在进入系统时编码一次，结果挂载于 `RawMessage` 并全链路复用，计算负载降低 50% 以上。
- **异步质心偏移检测 (Async Centroid Drift Detection)**：
    - 引入了 **滚动质心 (Rolling Centroid)** 算法，以 O(1) 复杂度实时维护对话重心，比对精度更高。
    - 将 Embedding 计算与漂移判定移至异步后台任务，确保对话主流程（Router）毫秒级响应，彻底消除延迟感。
- **步进采样检测 (Sampled Detection)**：新增 `boundary_topic_drift_interval` 配置（默认 5），每隔 N 条消息进行一次语义边界检查，进一步节省算力。
- **配置与 i18n 同步**：同步更新了 `_conf_schema.json` 及全站 i18n（中、英、日三语），并为开发者工具 `run_realtime_dev.py` 重新启用了该功能。

## [v0.7.32] — 2026-05-12

### 统一版本管理工作流 (Unified Version Management)

- **单一事实源 (SSOT)**：确立 `metadata.yaml` 为插件版本的单一事实源。
- **自动化版本工具**：新增 `bump_version.py` 脚本，支持一键更新 `metadata.yaml` 并自动在 `CHANGELOG.md` 中创建新版本占位符。
- **全栈同步**：
    - 后端：通过 `core/utils/version.py` 动态读取版本，确保 `main.py` 和 API 统计接口版本始终一致。
    - 前端：WebUI 侧边栏及 Landing Page 现在自动同步显示来自后端的真实版本号，告别硬编码。
    - 开发工具：`run_webui_dev.py` 和 `run_realtime_dev.py` 同步接入真实版本号。


## [v0.7.31] — 2026-05-12

### Mock 数据结构化 / 指令集 Mixin 重构

- **Mock 数据 JSON 化**：将 `Mock_Realtime_Data.md` 转换为 `mock_realtime.json`。现在数据集包含预计算的时间戳、用户 ID 和统一的字段结构，显著提升了开发脚本（`run_realtime_dev.py` / `run_dataflow_dev.py`）的加载效率。
- **指令集 Mixin 化**：重构了 `main.py` 中的指令管理。新增 `core/mixins/commands_mixin.py`，将复杂的指令注册逻辑从 Star 插件主类中剥离，保持了主类的整洁。
- **指令功能补全**：
    - 新增 `/mrm help` 指令，展示完整的指令集说明。
    - 统一了各指令的错误处理与初始化检查。


## [v0.7.30] — 2026-05-12

### 邻居扩展 (Neighbor Expansion) / 检索叙事连贯性优化

- **首选线程填充 (Primary Thread Filling)**：重构了 `RecallManager` 的召回算法。现在系统在检索到最相关的锚点事件（Top-1 Anchor）后，会自动查询并拉取其直接关联的父事件和子事件。
- **叙事连贯性**：被拉取的邻居事件将在 Token 预算内获得优先注入权重，确保 Bot 看到的记忆是“成串”的逻辑线程，而非碎片化的孤立片段，显著提升了复杂话题下的对话上下文理解能力。
- **性能保持**：邻居扩展仅针对 Top-1 锚点触发，确保在不增加显著检索延迟的前提下，最大限度地提升召回质量。

## [v0.7.29] — 2026-05-12

### 话题漂移检测 / Bot Persona 缓存 / 批量标签对齐 / 细粒度性能监控

- **话题漂移检测 (Topic Drift)**：在 `EventBoundaryDetector` 中实现基于 Embedding 余弦距离的漂移检测。当窗口消息达到阈值且主题偏移量超过 `drift_threshold`（默认 0.6）时，自动触发事件关闭。
- **VCM 状态机反馈**：`ContextManager` 现在接受 `recall_hit` 和 `drift_detected` 信号。若召回命中，状态切换至 `RECALL`；若检测到漂移，状态切换至 `DRIFT`，从而动态优化上下文窗口。
- **Bot Persona 缓存**：在 `EventExtractor` 中新增 `_bot_persona_cache`，避免在每次事件提取时重复查询数据库，显著减少提取延迟。
- **批量化标签对齐 (Batch Tag Normalization)**：重构了 `EventExtractor` 的标签 normalization 流程。现在将一个批次中所有事件生成的 raw tags 统一收集，通过单次 `encode_batch` 进行编码和对齐，大幅减少了对 Embedding 模型的调用次数。
- **细粒度性能监控**：
    - `PerfTracker` 升级：支持记录每个相位的最近一次执行耗时（Last Duration）和命中计数（Hit Count）。
    - 召回流程埋点：细化为 `recall_search`（搜索）、`recall_rerank`（重排序）和 `recall_inject`（注入）三个子相位。
    - API 增强：`get_stats` 返回详细的嵌套性能指标，方便 WebUI 实时展示各环节瓶颈。

## [v0.7.28] — 2026-05-12

### 加权检索曝光 / LLM 工具调用 / Sleep Consolidation / 指令集 / AstrBot i18n

- **加权随机检索前端曝光**：`retrieval_weighted_random` 和 `retrieval_sampling_temperature` 出现在配置页"检索"段，启用后采样温度字段自动激活
- **LLM 主动记忆工具**：新增 `@filter.llm_tool` 工具 `core_memory_remember(content, strength)` 和 `core_memory_recall(query)`，让模型自主决定何时存储与检索记忆
- **Sleep Consolidation 强化**：`run_memory_cleanup` 改为两阶段——先将低显著性事件归档（`status=archived`），超过 `retention_days`（默认 30 天）后才永久删除；`EventRepository` 新增 `archive_low_salience_events` 和 `delete_old_archived_events` 接口
- **指令集**：新增 `/mrm` 指令组（`status` / `run <task>` / `flush` / `recall <query>` / `webui on|off`）；`CommandManager` 从空 stub 实现为完整的逻辑层
- **AstrBot 插件 i18n**：新建 `.astrbot-plugin/i18n/zh_CN/plugin.json` 和 `en_US/plugin.json`，覆盖插件管理界面的显示名、描述及主要配置字段翻译

## [v0.7.27] — 2026-05-11

### IPC Alpha / Persona 置信度 / OCEAN 注入 / Soul Layer / 三语修复

- **IPC EMA Alpha 配置化**：印象更新 alpha 从硬编码 0.3 改为配置项 `impression_update_alpha`（默认 0.4）
- **Persona 置信度动态化**：`run_persona_synthesis` 以 BigFive 维度覆盖率为质量指标，通过 EMA 更新 `persona.confidence`，不再固定为 0.5
- **OCEAN 人格注入**：新增 `format_persona_for_prompt()`，将大五人格向量格式化为软风格启发式段注入 system prompt（不要求模型在回复中提及）
- **Soul Layer**（新系统）：新建 `core/social/soul_state.py`，实现四维情绪状态（RecallDepth / ImpressionDepth / ExpressionDesire / Creativity）；tanh 软天花板更新 + 每轮衰减；`RecallManager` 负责状态管理与 system prompt 注入；首页新增 Soul Layer 实时监看看板
- **配置页扩展**：在"VCM"与"记忆清理"之间新增"情绪系统"配置段（6 个字段，支持三语 Tooltip）
- **日文 i18n 修复**：清除混入日文字串的中文字符，涉及 `イベントゴミ箱`、`実行ステータス`、`軸スケール`、`重要度減衰`、`要約`、`編集`、`自動的` 等 13 处

## [v0.7.26] — 2026-05-11

### 大五人格每维度 evidence 句 + EMA 历史合并 + 百分比显示

#### 后端
- **`core/config.py`** — `_DEFAULT_PERSONA_SYSTEM_PROMPT`：`big_five_evidence` 从单字符串升级为每维度 dict；句子模板要求量化结果用 0%–100% 百分比（转换公式 `round((score+1)/2×100)%`，≥65%=高/35%–64%=中等/≤34%=低）；新增对历史评分的处理说明。`SynthesisConfig` 新增 `ema_alpha: float = 0.35` 字段。
- **`core/tasks/synthesis.py`** — `run_persona_synthesis()`：
  - BigFive 分数写入前先做 EMA 合并（有历史则 `α×new + (1−α)×old`，无历史直接写入，α 默认 0.35）
  - `big_five_evidence` 接受 dict 或旧字符串（向后兼容）

#### 前端
- **`lib/api.ts`**：`big_five_evidence` 类型改为 `string | Record<string, string>`
- **三处「性格」板块**（`node-detail.tsx`、`persona-dialogs.tsx` PersonaDetailCard、`library/page.tsx` PersonaDetailRow）：
  - 分数展示改为 `XX%`（百分比）
  - 每条维度行下方嵌入该维度的斜体证据句（dict 格式）；旧字符串格式 fallback 至块底部单行
- **Library 表格紧凑列**：格式从 `O75` 改为 `O75%`

#### 测试
- **`tests/test_tasks.py`**：移除旧 evidence 测试，新增：dict evidence 存储验证、向后兼容字符串验证、dict 截断验证、EMA 混合逻辑验证（共 4 个新断言），30 tests 全通过

## [v0.7.25] — 2026-05-11

### 大五人格 UI 优化：0~100 分 + 完整词组 + 三语

- **三处"性格"板块**（`node-detail.tsx`、`persona-dialogs.tsx` `PersonaDetailCard`、`library/page.tsx` `PersonaDetailRow`）：
  - 分数从 -1~1 转换为 0~100（`Math.round((val + 1) / 2 * 100)`），50 = 平均
  - 维度标签改用 i18n 完整词（开放性/尽责性/外向性/宜人性/神经质），随语言切换；移除硬编码单字缩写 `DIM_LABEL`
  - 布局从 `grid-cols-5` 改为垂直列表（label 左对齐 + 分数右对齐），防止文字溢出
  - 颜色阈值调整：≥65 绿色（高），≤35 红色（低），中间段 muted
- **Library 表格紧凑列**：格式从 `O↑ E↑ N·` 改为 `O75 E60 N45`
- 前端已重新 build

## [v0.7.24] — 2026-05-11

### 大五人格嵌套格式实装 + `big_five_evidence` 持久化展示

#### 后端
- **`core/config.py`**：三处 system prompt（`DEFAULT_EXTRACTOR_SYSTEM_PROMPT`、`DEFAULT_DISTILLATION_SYSTEM_PROMPT`、`_DEFAULT_PERSONA_SYSTEM_PROMPT`）更新 `participants_personality` 示例为嵌套格式 `{"Alice": {"scores": {"O": 0.6}, "evidence": "..."}}` ；合成 prompt 新增 `big_five_evidence` 字段要求（≤120 字符综合依据）。
- **`core/extractor/parser.py`**：`_parse_personality()` 重写，支持嵌套格式 `{"scores":{...}, "evidence":"..."}` 并保持旧平铺格式兼容；返回类型变为 `dict[str, dict]`，每个值含 `scores` 和可选 `evidence`。
- **`core/extractor/extractor.py`**：`_run_ipc_analysis()` 从 `traits.get("scores", traits)` 取分数，将 `traits.get("evidence")` 写入 `BigFiveBuffer._evidence[uid]`。
- **`core/social/big_five_scorer.py`**：`BigFiveBuffer` 新增 `_evidence: dict[str, str]` 字段和 `get_evidence(uid)` 方法；`evict()` 同步清除 evidence 缓存。
- **`core/tasks/synthesis.py`**：周期合成解析 LLM 返回的 `big_five_evidence` 并写入 `persona_attrs["big_five_evidence"]`（≤120 字符 clamp）。
- **`run_realtime_dev.py`**：Phase 2（LLM 提取）完成后新增 Phase 3 调用 `run_persona_synthesis`，将 BigFive 与 evidence 写入 persona_attrs，使 WebUI 可立即展示。原 Phase 3（group summary）顺延为 Phase 4，WebUI 顺延为 Phase 5。

#### 前端
- **`lib/api.ts`**：`PersonaNode.attrs` 新增 `big_five_evidence?: string`。
- **三处「性格」板块**（`node-detail.tsx`、`persona-dialogs.tsx` `PersonaDetailCard`、`library/page.tsx` `PersonaDetailRow`）：BigFive 评分格下方增加 `big_five_evidence` 斜体次要色文字，仅在字段存在时显示。

#### 测试
- **`tests/test_tasks.py`**：新增 `test_persona_synthesis_stores_big_five_evidence` 和 `test_persona_synthesis_truncates_evidence` 两个断言。

## [v0.7.23] — 2026-05-11

### 前端「性格」板块重构

- **`lib/i18n.ts`**：新增 `personalityBlock` 键（zh: '性格' / en: 'Personality' / ja: '性格'），区别于表格列标题"推演人格"。
- **`components/graph/node-detail.tsx`**：将原本分离的 description 和 BigFive 两个独立 `<div>` 合并为单一"性格"卡片块（有边框背景），任一字段存在时显示；BigFive 格维度标签改用单字缩写（开/尽/外/宜/神），tooltip 保留完整名称。
- **`components/graph/persona-dialogs.tsx`**：
  - `EditPersonaDialog`：移除 BigFive 只读块，编辑面板只保留可编辑字段（name/description/tags/bindings）；
  - `PersonaDetailCard`：description 从 grid 移出，与 BigFive 合并为"性格"卡片块，统一样式。
- **`app/library/page.tsx` `PersonaDetailRow`**：展开行移除单独的 description 展示，改为在 bindings 和操作按钮之间插入"性格"卡片块（含简述文字 + 大五评分格，宽度限定 `max-w-xs`）。

## [v0.7.22] — 2026-05-11

### Demo 数据补充 big_five 使推演人格可视化即时生效

- **`web/server.py`**：两处 Demo 注入数据（全量 Demo + Recall 小型 Demo）为 Alice/Bob/Charlie/Diana 补充 `big_five` 字段，取值与各人格 description 语义一致。注入 Demo 后，关系图节点面板和信息库人格表格的"推演人格"可视化可立即展示，无需等待周期任务运行。

## [v0.7.21] — 2026-05-11

### 推演人格：以大五人格替换情感类型 (Method B 全站移除 affect_type)

#### 后端 (`core/`, `web/server.py`)
- **`core/config.py`**：`_DEFAULT_PERSONA_SYSTEM_PROMPT` 不再要求 `affect_type`，改为要求 `description` + `big_five`（O/C/E/A/N，范围 -1.0~1.0）；提取与蒸馏 prompt 新增 OCEAN 维度语义说明。
- **`core/tasks/synthesis.py`**：周期合成任务移除 `affect_type` 写入，改为将 LLM 返回的 `big_five` 写入 `persona_attrs`，并对各维度做 `clamp(-1, 1)` 验证。
- **`web/server.py`**：POST/PUT 人格 API 移除 `affect_type` 字段；PUT 改为透传现有 `big_five`（保留周期任务写入的值）；demo 数据移除全部 `affect_type` 字段。

#### 前端 (`web/frontend/`)
- **`lib/api.ts`**：`PersonaNode.attrs` 类型新增 `big_five?: {O,C,E,A,N}?`，移除 `affect_type`。
- **`lib/i18n.ts`**：新增 `inferredPersonality` / `bigFive.{label,O,C,E,A,N}` 键（zh/en/ja 三语），移除 `affectType` / `affectTypes` 键及 `getLocalizedAffectType()` 函数。
- **`components/graph/persona-dialogs.tsx`**：移除情感类型 Select 控件及相关状态；`EditPersonaDialog` 新增只读大五评分面板（有值时显示）；`PersonaDetailCard` 改为展示大五评分。
- **`components/graph/node-detail.tsx`**：移除情感类型展示，改为大五评分只读网格（颜色编码：+↑绿/-↓红/中性灰）。
- **`app/library/page.tsx`**：人格表格"情感类型"列改为"推演人格"，显示 `O↑ E↑ N↓` 紧凑格式。

#### 测试
- 更新 `test_domain.py`、`test_projector.py`、`test_sqlite_repo.py`、`test_tasks.py`、`test_webui.py` 中的 `affect_type` fixture 数据，改用 `description` / `big_five`；`test_tasks.py` 新增 big_five 字段断言。

## [v0.7.20] — 2026-05-11

### Header 架构升级：基于插槽的全局操作隔离

#### 前端 (`web/frontend/`)
- **`PageHeader` 组件重构**：
  - **插槽化设计**：扩展了 `PageHeader` 组件，新增 `globalActions` 属性。现在的 Header 操作区被明确划分为“页面专属功能 (Actions)”与“系统全局功能 (Global Actions)”。
  - **视觉隔离**：在两个操作区域同时存在时，自动在中间插入一条垂直的分隔符 (`Separator`)。这符合菲茨定律，使用户能直观地区分当前上下文操作（如编辑、删选）与系统级状态操作（如全局刷新）。
- **全站应用适配**：
  - **解耦刷新逻辑**：遍历重构了全站 7 个主页面（Events, Library, Recall, Stats, Graph, Summary, Config）。将原先混杂在各页面的“刷新”按钮统一剥离至 `globalActions` 插槽。
  - **逻辑强化一致性**：确立了 `[ 专属操作 ] | [ 全局刷新 ]` 的界面范式，极大降低了用户跨页面浏览时的心智负担。

#### 后端加权随机检索
- 在 `HybridRetriever` 的 RRF 融合结果上加一层 softmax 采样，替代确定性 top-K 截断。用分数作为权重做带放回采样，让 bot 的记忆表现更接近人类的"有时想起、有时忘记"，避免永远只检索到同几条高分事件。改动范围：`core/retrieval/hybrid.py` 一个函数，可配置开关。


## [v0.7.19] — 2026-05-11

### 全站 UI 标准化：Header 操作栏一致性与 UX 深度优化

#### 前端 (`web/frontend/`)
- **全站 Header 标准化 (`PageHeader`)**：
  - **组件化动作栏**：对全站 7 个主要页面（Events, Library, Recall, Stats, Graph, Summary, Config）的 Header Actions 进行了重构。所有页面的操作按钮现在统一遵循 `h-8` 规格。
  - **响应式交互**：所有操作按钮采用“图标+文字”模式，并在移动端自动隐藏文本标签，仅保留核心图标，极大提升了小屏下的操作体验。
  - **搜索框规范化**：搜索框统一应用了 `hidden md:block` 逻辑，在移动端折叠以节省空间，桌面端则保持 `lg:w-64` 的舒适宽度。
  - **全局刷新语义**：为所有页面补齐了带有旋转动画的 `RefreshCw` 刷新按钮，确保用户在任何界面都能获得一致的数据同步反馈。
- **Events 页面体验修复**：
  - **详情页易用性**：在事件详情 `Sheet` 的 Sticky 头部增加了显式的关闭按钮（`X`），解决了在窄屏或高缩放比例下默认关闭按钮被覆盖而无法退出的 Bug。
- **构建与质量保障**：
  - 修复了重构过程中漏掉的 `lucide-react` 图标与 `Button` 组件的导入错误。
  - 通过全量 `npm run build` 验证，确保所有页面的静态导出逻辑完全兼容。

## [v0.7.18] — 2026-05-11

### 事件流 UI 响应式重构：从常驻边栏转向浮动抽屉

#### 前端 (`web/frontend/`)
- **布局重构 (`events/page.tsx`)**：
  - **全宽时间轴**：移除了常驻的右侧边栏，使时间轴在默认状态下占据 100% 屏宽，解决了高缩放倍率下内容拥挤的问题。
  - **详情抽屉化 (Sheet)**：引入 `shadcn/ui` 的 `Sheet` 组件，点击事件后详情面板从右侧平滑滑出。在 PC 端保持专业宽度（35vw），在移动端自动适配全屏，并带有背景遮罩以增强视觉聚焦。
  - **控制栏整合**：
    - **Popover 缩放控制**：将时间轴缩放滑块收纳至顶栏的 `Popover` 中，通过 `SlidersHorizontal` 图标触发。
    - **操作栏优化**：回收站按钮移至顶栏操作区，并为搜索框增加了移动端自动隐藏逻辑，提升了窄屏下的空间利用率。
- **构建验证**：完成 `npm run build` 验证，确保新的组件层级与状态控制逻辑在静态导出模式下运行正常。

## [v0.7.17] — 2026-05-11

### 前端 UI 修复：移除冗余文本伪影

#### 前端 (`web/frontend/`)
- **组件库 (`components/events/event-dialogs.tsx`)**：
  - **移除伪影**：删除了 `RecycleBinDialog` 组件中由于编辑残留导致的字面量 `...` 文本节点。该错误曾导致“事件流”和“信息库”页面在某些布局下于左下角显示多余的 `\n...`。
- **构建验证**：完成 `npm run build` 验证，确认静态导出结果已包含此修复，且界面无样式回归。

## [v0.7.16] — 2026-05-11

### 侧边栏 UI 精简：移除冗余统计与状态可见性优化

#### 前端 (`web/frontend/`)
- **侧边栏 (`app-sidebar.tsx`)**：
  - **极简设计**：移除了侧边栏底部的“人格、总事件、印象”统计磁贴及多余的分隔线，进一步减少视觉噪音。
  - **响应式状态灯**：优化了“引擎活跃中”指示灯的显示逻辑。现在当侧边栏处于最小化（Icon 模式）时，绿色的脉冲状态灯依然保持可见，仅隐藏文本标签，增强了系统运行状态的实时感知。

---

## [v0.7.15] — 2026-05-11

### 记忆召回增强：混合检索链路修复与摘要索引补全

#### 核心检索逻辑 (`core/`)
- **FTS5 索引扩展 (`migrations/008_fix_fts_summary.sql`)**：
  - 修复了 `events_fts` 表缺失 `summary` 字段的问题。
  - 更新了数据库触发器，确保后续插入或更新事件摘要时，关键词搜索能实时命中。
- **向量索引补全 (`HybridRetriever`, `EventExtractor`)**：
  - 修正了向量嵌入 (Embedding) 的计算逻辑，将 `summary` 纳入文本序列，使语义搜索能更好地理解事件核心内容。
- **混合检索上线 (`RecallManager`)**：
  - 修复了 WebUI 召回接口此前仅使用 FTS5 关键词匹配的局限。
  - 现在 WebUI 召回功能已正式接入 `RecallManager` 的混合检索链路（FTS5 + Vector + RRF 重排序），检索效果与 RAG 插件内部逻辑完全一致。

#### 后台任务与管理 (`core/tasks/`, `web/`)
- **新增重索任务 (`reindex_all`)**：
  - 开发了 `run_reindex_all` 任务，支持一键为所有历史事件重新计算向量嵌入并刷新关键词索引。
- **WebUI 交互优化**：
  - **设置页面**：新增“记忆重索 (Re-index)” 按钮，允许用户在插件升级后手动修复历史数据的检索索引。

---

## [v0.7.14] — 2026-05-11

### 前端 UI 优化：界面统一性与记忆召回布局调整

#### 前端 (`web/frontend/`)
- **记忆召回页面 (`recall/page.tsx`)**：
  - **刷新按钮统一**：将 Header 中的刷新按钮调整为与事件流页面一致的图标按钮样式（`RefreshCw`），并支持旋转动画。
  - **召回按钮布局**：将“召回”按钮从 Header 移至查询配置行（结果数、会话 ID）的右侧，使参数配置与执行操作在视觉上更连贯。
  - **组件精简**：移除冗余的 `CardFooter`，通过 `flex-wrap` 优化了查询配置栏的响应式布局。

---

## [v0.7.13] — 2026-05-11

### 前端 UI 结构优化：状态与统计向侧边栏整合

#### 前端 (`web/frontend/`)
- **侧边栏 (`app-sidebar.tsx`)**：
  - **状态整合**：将原本位于首页 Header 的“引擎活跃中” (Engine Active) 指示灯及其脉冲动画移至侧边栏底部。
  - **统计重构**：删除了侧边栏底部原有的三个独立 Badge，替换为更具视觉整体感的**仪表盘磁贴 (Stats Tiles)**。
  - **布局优化**：新增 3 列网格布局展示人格、总事件、印象数，采用半透明背景与高对比度数值显示，提升了侧边栏在收起/展开状态下的信息密度。
- **首页 (`app/page.tsx`)**：
  - **头部精简**：移除 `PageHeader` 中的 `actions` 区域，将核心状态感知权交给侧边栏，减少首页视觉干扰。

#### 构建与验证
- 完成 `npm run build` 验证，确保静态导出逻辑与新的组件布局完全兼容。

---

## [v0.7.12] — 2026-05-11

### 数据流优化：周期任务精简与 Pipeline 效率提升

#### 周期任务重构

- **`core/tasks/synthesis.py`**：删除 LLM 版 `run_impression_aggregation`（因 `evidence_event_ids` 始终为空而形同死代码），替换为纯算法版 `run_impression_recalculation`：
  - 通过 `ipc_model.derive_fields(B, P)` 重算 `ipc_orientation` / `affect_intensity` / `r_squared` / `confidence`，保持衍生字段与公式常数同步。
  - 批量预加载所有涉及 uid 的事件集合（每 uid 一次 DB 查询），在内存中做集合求交重建 `evidence_event_ids`，将原 O(impressions) 次 DB 查询降至 O(unique_uids) 次。
  - `run_persona_synthesis`：`content_tags` 改为从事件 `chat_content_tags` 频率统计（`collections.Counter`）得出，不再请求 LLM；LLM 仅负责 `description` 和 `affect_type`。
- **`core/plugin_initializer.py`**：合并 `salience_decay` + `memory_cleanup` + `projection` 三个独立定时任务为单一 `daily_maintenance`；`impression_aggregation` → `impression_recalculation`（无 `provider_getter`）。

#### 数据流 Bug 修复

- **`core/social/orientation_analyzer.py`**：`analyze()` 和 `_upsert_impression()` 新增 `event_id` 参数，修复原来 `evidence_event_ids` 始终写入空列表的 Bug，上限 100 条。

#### 性能小优化

- **`core/managers/memory_manager.py`**：`stats()` 改为并发 SQL `COUNT(*)` 查询，不再全表扫描。新增 `count_by_status()` 抽象方法及实现（`base.py` / `sqlite.py` / `memory.py`）。
- **`core/extractor/extractor.py`**：`_init_tag_seeds()` 改用 `encode_batch()` 单次批量编码所有种子标签。
- **`core/social/big_five_scorer.py`**：`BigFiveBuffer._texts` 新增 `_max_texts = x_messages × 2` 上限，防止长会话内存无限增长。

#### 测试

- **`tests/test_tasks.py`**：删除旧 `run_impression_aggregation` 测试，新增 `run_impression_recalculation` 测试四个。
- **`tests/test_memory_repo.py`**：新增 `count_by_status` 两个测试。
- **`tests/test_extractor.py`**：新增 `BigFiveBuffer` maxlen 两个测试。

---

## [v0.7.11] — 2026-05-11

### Unified Extraction：人格评分与事件提取合并为单次 LLM 调用

- **`core/config.py`**：`DEFAULT_EXTRACTOR_SYSTEM_PROMPT` 和 `DEFAULT_DISTILLATION_SYSTEM_PROMPT` 均新增 `participants_personality` 字段定义（inline JSON schema + 字段说明）。LLM 在提取事件信息的同时输出参与者五大人格评分（O/C/E/A/N，-1.0~1.0），字段可选，不确定时省略。
- **`core/extractor/prompts.py`**：`build_distillation_prompt` 末尾 inline 示例中补充 `participants_personality` 字段，与 system prompt 保持一致。
- **效果**：IPC 启用时，`participants_personality` 返回值直接写入 `BigFiveBuffer._cache`，`maybe_score()` 在计数未达阈值时跳过独立的 Big Five LLM 调用，每次 event close 节省约 1 次 LLM 调用。两条路径（`llm` 策略走 extractor、`semantic` 策略走 distillation）输出格式现已统一。
- 前端页面 **event timeline** 视觉效果增强。

## [v0.7.10] — 2026-05-11

### 数据流 Bug 修复与性能优化 (Dataflow Bugfixes & Performance)

#### P0 Bug 修复

- **`core/managers/context_manager.py`**：`ContextManager` 新增可选 `evict_callback` 参数。LRU 驱逐时会通过 `asyncio.create_task` 调用该回调，确保被驱逐的 window 不再静默丢失，而是触发 `EventExtractor` 正常提取。
- **`core/plugin_initializer.py`**：初始化时将 `on_event_close` 同时注入 `ContextManager.evict_callback`，完成回调的端到端接线。
- **`core/adapters/astrbot.py`**：移除 `drift_detected = (reason == "topic_drift")` 死代码——`EventBoundaryDetector` v1 从不返回 `"topic_drift"` reason，此表达式永远为 `False`，改为直接传递默认值 `False`，避免误导性代码。

#### P1 性能优化

- **`core/adapters/identity.py`**：`IdentityResolver` 新增 `(platform, physical_id) → uid` 内存缓存，同一用户的后续消息不再重复打 DB，热路径 DB 调用降至每用户首次出现一次。
- **`core/extractor/extractor.py`**：合并 `_get_bot_persona_desc()` 和 `_get_bot_persona_name()` 为单一 `_get_bot_persona() -> (name, desc)`，并在 `__call__` 顶部调用一次后共享给所有 partition 和 result 循环，每次 event close 的 `persona_repo.list_all()` 调用从 N 次降至 1 次。

#### P2 性能 & 稳定性优化

- **`core/extractor/extractor.py`**：`_align_tags()` 改用 `encode_batch(all_tags)` 一次性编码所有标签，再通过 `asyncio.gather` 并发执行 `search_canonical_tag`，消除原有的 N 次串行 encode + N 次串行 DB 查询模式。
- **`core/extractor/extractor.py`**：将 `asyncio.create_task(self._init_tag_seeds())` 从 `__init__` 移除，改为在首次 `__call__` 时懒初始化（通过 `_seeds_initialized` 标志位）。修复在无事件循环的同步上下文中构造 `EventExtractor` 时抛出 `RuntimeError: no running event loop` 的问题。

#### 测试

- **`tests/test_context_manager.py`**：新增 `test_lru_eviction_triggers_evict_callback`、`test_lru_eviction_without_callback_does_not_raise`。
- **`tests/test_message_router.py`**：新增 `test_router_drift_detected_is_false_for_time_gap_close`，验证 v1 的 drift_detected 始终为 False。
- **`tests/test_identity_resolver.py`**（新文件）：覆盖 uid 稳定性、平台隔离、缓存命中跳过 DB 等场景。
- **`tests/test_extractor.py`**：新增 `test_bot_persona_list_all_called_once_per_extractor_call`。
- **`tests/test_tag_normalization.py`**：新增 `test_align_tags_uses_batch_encode_not_per_tag_encode`、`test_align_tags_empty_list_no_encode`、`test_extractor_construction_outside_event_loop_does_not_raise`、`test_tag_seeds_initialized_on_first_call_not_at_construction`。

---

## [v0.7.9] — 2026-05-11

### 统一提取策略与 IPC 鲁棒性优化 (Unified Extraction & IPC Robustness)

#### 后端 (`core/`)
- **`core/extractor/parser.py`**：重构解析器，新增对统一LLM调用prompt中 JSON 字段的解析与数值校验逻辑。
- **`core/extractor/extractor.py`**：重构提取流程。现在优先使用 LLM 随事件返回的性格数据来预热缓存，并同步等待所有 IPC 分析任务完成，彻底解决了数据更新的竞态条件。
- **`core/social/ipc_model.py`**：修复置信度归零 Bug。重构 `r_squared` 计算公式，从“距离占比”改为“角度拟合度”，并为中立原点（B=0, P=0）提供 0.5 的默认置信度。
- **`core/social/orientation_analyzer.py`**：
    - **EMA 逻辑修复**：确保现有记录的 `confidence` 会随新数据滚动更新。
    - **管道整合**：将原本独立的基于交互频率的启发式规则整合为分析器的 **Fallback 路径**。现在系统优先采用 LLM 的科学评分，仅在数据缺失时触发规则兜底，消除了多源写入冲突。
- **`core/plugin_initializer.py`**：移除了废弃的 `_maybe_trigger_impression` 后台任务，简化了组件初始化依赖。

#### 测试
- **`tests/test_extractor.py`**：新增 `test_extractor_unified_personality_priming` 集成测试，验证统一提取路径下的性格数据流转与印象更新。

---

## [v0.7.8] — 2026-05-11

### 数据驱动的情感动态分析 (Data-Driven Mood Analysis)

#### 后端 (`core/`)
- **`core/tasks/summary.py`**：实现 **选项 A (Impression DB)** 路径。系统现在可以从数据库中聚合真实的 IPC 社交坐标来计算群体的“情感质心”，并自动 fallback 到 LLM 模式。
- **`core/config.py`** & **`_conf_schema.json`**：新增 `summary_mood_source` 配置项，允许用户在“LLM 推断 (感性)”与“印象数据库 (理性)”之间切换。
- **`core/plugin_initializer.py`** & **`web/server.py`**：完善依赖注入，将 `impression_repo` 正确传递给摘要生成任务。

#### 测试
- **`tests/test_summary_mood.py`**：新增针对选项 A、选项 B 以及自动回退机制的单元测试。
- **`tests/test_tasks.py`**：修复了原有测试中不符合 IPC 模型定义的标签导致的断言失败。

---

## [v0.7.7] — 2026-05-11

### 标签抽象与归一化治理 (Tag Abstraction & Normalization)

#### 后端 (`core/`)
- **`migrations/007_canonical_tags.sql`**：新增 `canonical_tags` 存储规范化标签，以及配套的 `tags_vec` (vec0) 向量虚拟表。
- **`core/repository/base.py`**：`EventRepository` 接口新增 `list_frequent_tags()`、`search_canonical_tag()` 及 `upsert_canonical_tag()`。
- **`core/repository/sqlite.py`**：实现基于 `json_each` 的高频标签统计与基于 `sqlite-vec` 的标签向量对齐逻辑。
- **`core/extractor/prompts.py`**：修改 `build_user_prompt` 和 `build_distillation_prompt`，支持注入 `existing_tags` 实现 Few-shot 引导，促使 LLM 优先使用已有宏观标签。
- **`core/extractor/extractor.py`**：
    - **Step 0**：提取前获取常用标签注入提示词。
    - **Silent Alignment**：事件持久化前对 LLM 生成的标签进行本地向量对齐。
    - **自动聚类**：相似度 > 阈值（默认 0.85）的标签自动归并；新话题则自动沉淀为新规范标签。
- **`core/config.py`** & **`_conf_schema.json`**：新增 `tag_normalization_threshold` 配置项，允许用户微调标签合并的敏感度。

#### 测试
- **`tests/test_tag_normalization.py`**：新增针对标签向量对齐、Few-shot 注入和去重逻辑的单元测试。

---

## [v0.7.6] — 2026-05-10

### 人格列显示修复 + 摘要编辑结构化隔离 (Persona Name Display & Structured Summary Editor)

#### 后端 (`core/`)
- **`core/domain/models.py`**：`Event` dataclass 末尾新增可选字段 `bot_persona_name: str | None = None`。
- **`migrations/006_event_bot_persona_name.sql`**：新增迁移，对 `events` 表执行 `ALTER TABLE ADD COLUMN bot_persona_name TEXT DEFAULT NULL`。
- **`core/repository/sqlite.py`**：`_row_to_event()` 读取 `bot_persona_name` 列；`upsert()` INSERT/UPDATE 语句同步写入该列。
- **`core/extractor/extractor.py`**：新增 `_get_bot_persona_name()` 方法（复用 `internal` 平台查找逻辑，返回 `primary_name`）；在事件持久化前，若 `persona_influenced_summary` 为 True 则将 bot 名称写入 `event.bot_persona_name`。
- **`web/server.py`**：`event_to_dict()` 新增 `bot_persona_name` 字段输出。

#### 开发工具
- **`run_realtime_dev.py`**：模拟 persona 的 `primary_name` 改为从 `mock_persona.md` 标题行 `# Mock Persona: <name>` 动态解析，不再硬编码。

#### 前端 (`web/frontend/`)
- **`lib/api.ts`**：`ApiEvent` 接口新增 `bot_persona_name?: string | null`。
- **`lib/i18n.ts`**：新增 `summaryEvalNone`（zh: 无 / ja: なし / en: None）、`summaryAddTopic`（zh: 添加话题 / ja: トピック追加 / en: Add Topic）三语 key。
- **`components/events/event-dialogs.tsx`**：
  - `EventDetailCard` 人格列改为读取 `event.bot_persona_name ?? i18n.events.personaDefault`，修复始终显示"全局"的问题。
  - `[Eval]` 行改为始终显示，无评价时展示 `i18n.events.summaryEvalNone`。
  - 新增 `StructuredSummaryEditor` 组件：当摘要可解析为结构化格式时，将编辑区替换为按 What/Who/How/Eval 分字段的独立 `<Input>` 组，用户不直接接触 `[What]` 等系统词；保存时自动重建结构化字符串。旧格式（无法解析）自动退化为 `<Textarea>` 自由文本模式。全部四个字段标签（发生了什么/参与者/如何发展/'我'的评价）均通过现有 i18n key 实现三语适配（zh/ja/en）。
  - `EventForm` 的 summary 字段改用 `StructuredSummaryEditor`。

---

## [v0.7.5] — 2026-05-10

### 事件摘要结构化格式与人格评价 (Structured Summary Format & Persona Eval)

#### 后端 (`core/`)
- **`core/config.py`**：`DEFAULT_EXTRACTOR_SYSTEM_PROMPT` 与 `DEFAULT_DISTILLATION_SYSTEM_PROMPT` 的 `summary` 字段说明更新为 `[What]/[Who]/[How]` 三元组格式，多个小话题以 ` | ` 分隔，数量与 `chat_content_tags` 对应（1-5个）；当提示词中包含 `[Bot 视角人格]` 时，要求每个三元组末尾附加 `[Eval]` 字段。
- **`core/extractor/prompts.py`**：`build_user_prompt` 与 `build_distillation_prompt` 在注入 `bot_persona_desc` 时，额外输出一行明确指令，要求 LLM 在每个小话题三元组末尾加上以该人格视角的 `[Eval]` 一句话评价。

#### 前端 (`web/frontend/`)
- **`lib/i18n.ts`**：新增 `summaryWhat` / `summaryWho` / `summaryHow` / `summaryEval` 四个 key（zh: 发生了什么 / 参与者 / 如何发展 / '我'的评价；ja: 何が起きたか / 参加者 / どのように展開 / '私'の評価；en: What / Who / How / 'My' Comment）。
- **`components/events/event-dialogs.tsx`**：
  - 新增 `parseSummaryTopics()` 辅助函数，按 `|` 分割小话题，解析 `[What]`/`[Who]`/`[How]`（必填）及 `[Eval]`（可选）；匹配不足3个字段时 fallback 到纯文本渲染，向后兼容旧数据。
  - `EventDetailCard` summary 块改为行列式三元组展示；`[Eval]` 字段仅在存在时渲染为第四行。
  - 人格列改为始终显示 `i18n.events.personaDefault`（"全局"），移除对 `event.group` 的错误引用。

---

## [v0.7.4] — 2026-05-10

### 事件摘要质量与配置扩展 (Event Summary Quality & Config Overhaul)

#### 后端 (`core/`)
- **`core/extractor/parser.py`**：移除 `parse_llm_output` 与 `parse_single_item` 中对 `Event.summary` 的 200 字硬限制，摘要长度现由 LLM 自行决定。
- **`core/extractor/prompts.py`**：`build_user_prompt` 与 `build_distillation_prompt` 新增可选参数 `bot_persona_desc: str | None`；若提供则在提示词开头注入 `[Bot 视角人格] <描述>` 行，使摘要带有 Bot 当前性格的视角。
- **`core/extractor/extractor.py`**：`EventExtractor.__init__` 新增 `persona_repo` 可选参数；新增内部方法 `_get_bot_persona_desc()` 通过 `platform="internal"` 查找 Bot 人格并返回其 `description`；提取时将描述传给提示词构建器。
- **`core/config.py`**：`ExtractorConfig` 新增字段 `persona_influenced_summary: bool = False`；`PluginConfig.get_extractor_config()` 读取同名配置键。
- **`_conf_schema.json`**：在 `boundary_topic_drift_threshold` 之后新增 `persona_influenced_summary`（bool，默认 false）。
- **`core/plugin_initializer.py`** 与 **`run_realtime_dev.py`**：`EventExtractor` 实例化时传入 `persona_repo=persona_repo`。

#### 前端 (`web/frontend/`)
- **`lib/i18n.ts`**：
  - `config.sections.boundary` 三语言均重命名为 `'事件流'` / `'イベントフロー'` / `'Event Flow'`。
  - 新增 `config.fields.persona_influenced_summary` 标签与提示（zh/ja/en）。
  - 新增 `events.personaLabel` / `events.personaDefault`（zh/ja/en）。
- **`components/events/event-dialogs.tsx`**：`EventDetailCard` 元信息网格列数从 `sm:grid-cols-4` 扩展为 `sm:grid-cols-5`，在参与者之后新增人格列，显示 `event.group`，无群组时显示 `i18n.events.personaDefault`（全局/グローバル/Global）。

---

## [v0.7.3] — 2026-05-10

### 摘要系统重构：三段分离式生成与 WebUI 编辑隔离 (Summary System Overhaul)

#### 后端 (`core/`)
- **`_DEFAULT_SUMMARY_SYSTEM_PROMPT`** 重构：保留原有引导语，仅生成 `[主要话题]` 正文（≤300 字），删除原有四段式格式指令（`[关键时间]`、`[关系变化]` 已废除）。
- **新增 `_DEFAULT_SUMMARY_MOOD_PROMPT`**：用于 `[情感动态]` 的 LLM 推断，输出单行 JSON（`orientation`、`benevolence`、`power`、`positions`）。
- **`SummaryConfig`** 新增字段：`word_limit`（字数上限）、`mood_source`（`"llm"` | `"impression_db"`，默认 `"llm"`）、`mood_prompt`。
- **`core/tasks/summary.py`** 完整重构：
  - `[事件列表]` 改为**确定性生成**（无 LLM 调用），使用 `interaction_flow[-1].content_preview`（≤20 字）、`sender_uid`（可选通过 `persona_repo` 解析为显示名）、`event_id`、`topic` 拼接链式格式：`[话题名] - [事件ID] | *在[用户x]发出了[xxx内容]结束了话题后话题转向了 | [话题名] - [事件ID]`。
  - `[情感动态]` 当前使用 **Option B（LLM 推断）**，第二次 LLM 调用。
  - 新增 `regenerate_single_summary()` 函数：供 WebUI 按需重新生成指定群组 + 日期的摘要。
  - `run_group_summary()` 新增可选参数 `persona_repo`（用于 uid→显示名映射）。
- **`web/server.py`**：
  - `WebuiServer.__init__` 新增可选参数 `provider_getter`，供摘要重新生成使用。
  - 新增 `POST /api/summary/regenerate`（sudo 权限）路由，调用 `regenerate_single_summary`。
- **Option A/B 实现细节**已记录至 `TODO.md`，方便后续切换至印象 DB 数据源。

#### 前端 (`web/frontend/`)
- **`lib/api.ts`**：`summaries` API 新增 `regenerate(groupId, date)` 方法。
- **`lib/i18n.ts`**：新增摘要相关 i18n key（`regenerate`、`regenerateConfirmTitle`、`regenerateConfirmDesc`、`regenerateSuccess`、`regenerateError`、`sectionTopic`、`sectionEvents`、`sectionMood`、`readOnly`），覆盖 zh/ja/en 三语言。
- **`app/summary/page.tsx`** 完整重构：
  - 内容解析：`parseSections()` 将 Markdown 文件按 `[主要话题]`/`[事件列表]`/`[情感动态]` 标题拆分为三段独立状态。
  - **三段分离展示**：各段独立显示框，位置不变，顺序为 主要话题 → 事件列表 → 情感动态。
  - **编辑隔离**：仅 `[主要话题]` 提供 `<Textarea>` 编辑；`[事件列表]` 和 `[情感动态]` 显示只读 Badge，不可编辑。
  - 保存时以 `assembleSections()` 重组完整 Markdown，`[事件列表]` 和 `[情感动态]` 原样保留。
  - **[调用LLM重新总结] 按钮**：位于页面顶部操作栏，点击弹出 `<AlertDialog>` 确认框，确认后调用 `/api/summary/regenerate`，三段全部更新；需要 Sudo 模式。

---

## [v0.7.2] — 2026-05-10

### 前端构建产物同步修复 (Frontend Build Sync Fix)

- **根因**：`e6cba06` ([chores] Event Flow UI & Visualization Overhaul) 提交了 v0.7.1 的源码变更（`event-timeline.tsx`、`events/page.tsx`、`event-dialogs.tsx`），但未同步重新编译并提交 `web/frontend/output/`。导致用户 `git checkout` 后得到的是旧版 build（hash: `sMXf4ujWTjNDiZwnUWyd7`），该 build 引用的 JS chunks（`d4b3d3e494e64a1e.js`、`7e0385642e133874.js`、`348156fcd50077db.js`）在当前工作区已不存在，浏览器客户端路由尝试动态加载这些 chunk 时收到 404，导航静默失败，用户停留在旧界面无法进入新 events 页面。
- **修复**：在当前代码状态下重新执行 `npm run build`（Node.js v24，Next.js 16 Turbopack），生成新 build（hash: `g9kRJCgvYdsUFxpsxbVFd`），并将完整 `web/frontend/output/` 目录提交入库，确保源码与构建产物保持一致。
- **影响**：`run_realtime_dev.py` 与 `run_webui_dev.py` 等开发脚本现在可直接使用最新 events 界面（Axis Context View、交互式侧边栏展开至 1/3 屏宽、水平散列布局、自动居中等全部 v0.7.1 新特性）。

---

## [v0.7.1] — 2026-05-10

### 事件流显示性能与视觉深度优化 (Event Flow UI & Visualization Overhaul)

- **动态多事件轴视图 (Axis Context View)**：
  - **交互式侧边栏**：点击时间轴事件后，右侧详情面板现在会动态展开至屏幕宽度的 **1/3**，提供更广阔的阅读空间。
  - **轴向事件聚合**：侧边栏不再仅显示单个事件，而是自动加载并显示该事件所属“轴”（同群组/私聊）下的所有相关事件序列，支持按时序（旧→新）滚动浏览。
  - **权限分级隔离**：仅允许对当前选中的“焦点事件”进行编辑和删除操作；轴上的其他事件仅提供详情查看与快速锁定/解锁功能。
- **视觉渲染引擎升级 (Advanced Rendering)**：
  - **比例全量放大**：整体 UI 元素（节点半径、行高、轴间距、字体）等比例放大约 **20%**，大幅提升高分辨率显示器下的可操作性。
  - **高对比度增强**：提升了主轴、时间刻度及事件节点的描边与填充不透明度，日期标注加粗并增大字号，确保关键时序信息清晰可见。
  - **水平散列布局 (Horizontal Spread)**：当多个事件因缩放挤压在同一行时，自动从垂直堆叠切换为**水平交叠排列**；悬停时节点平滑展开，确保密集节点的精准选中。
  - **轴向视觉延伸**：在时间轴顶部新增虚线引导线，建立从顶部控制栏到数据区的视觉连续性。
- **UX 与滚动隔离 (UX & Scroll Isolation)**：
  - **自动居中对齐 (Auto-Centering)**：选中事件后，时间轴将自动执行平滑滚动，将目标节点精准定位至视口正中央，并适配了侧边栏展开的布局动画延迟。
  - **局部滚动锁定**：实现了事件详情区域的滚动隔离，防止侧边栏滚动触发全页背景偏移，确保沉浸式交互。

---

## [v0.7.0] — 2026-05-10

### 交互优化与回收站功能修复 (UX Optimization & Recycle Bin Fixes)

- **回收站更名**：全语言适配将“回收站” (Recycle Bin) 更名为 **“事件回收站” (Event Recycle Bin / 事件回收箱)**，提升功能指向性。
- **信息库快捷访问**：在“信息库” (Library) 页面的时间范围调整栏右侧新增回收站图标按钮，方便用户快速查看并还原已删除的事件。
- **功能修复与架构加固 (Restore Fix & Robustness)**：
  - **强制关键字参数**：修改 `Event` 领域模型为 `kw_only=True`，强制所有实例化过程显式使用关键字参数（如 `topic="..."`），从根本上解决了因字段顺序或缺失导致的 `Event.__init__` 参数错误。
  - **全局代码重构**：对整个代码库（包括 WebUI 后端、数据库存储层、提取器及所有测试用例）中的 `Event` 实例化点进行了全局扫描与重构，确保完全兼容新模型定义。
  - **模型字段补全**：为 `Event` 所有非 ID 字段（如 `summary`, `chat_content_tags`, `salience` 等）增加了默认值，大幅提升了在还原已删除事件及读取旧版本数据时的稳定性。
  - **逻辑重构**：优化 `_handle_recycle_bin_restore` 逻辑，确保恢复事件时摘要、状态及锁定标志位的完整性。
- **锁定保护 (Lock Protection)**：在事件详情与列表页同步实现了“锁定禁止删除”的逻辑，并增加了对应的三语 UX 提示。
- **国际化 (i18n)**：为新增按钮与文案补全了中、英、日三语翻译，并移除了部分组件中的硬编码中文。

---

## [v0.6.9] — 2026-05-09

### 测试数据集整理 (Test Dataset Reorganization)

- **文件重命名**：`Mock_Data.md` → `Mock_Realtime_Data.md`，明确区分实时测试数据集与其他 mock 数据。
- **路径统一**：将数据集以 JSON 格式存入 `tests/mock_data/mock_realtime.json`，与 `mock_chat.json` 同目录管理，`run_realtime_dev.py` 引用路径同步更新。
- **LLM 超时调整**：`extractor_llm_timeout_seconds` 及 `SummaryConfig.llm_timeout` 由 150 s 上调至 **300 s**，`_RealtimeProviderBridge` 的 httpx 层由 180 s 上调至 **330 s**，为 Gemma 26B 在高负载下提供更充足的响应窗口。

---

## [v0.6.8] — 2026-05-09

### 测试工具链完整性修复 (Dev Toolchain Completeness Fixes)

#### `reset_realtime_dev.py` — 新增摘要目录还原逻辑
- **根因**：`run_realtime_dev._archive_step()` 启动时会将 `.dev_data/groups/`（由 `run_webui_dev.py` 写入的演示摘要文件）通过 `shutil.move` 移入 `archive/groups_<ts>/`；而原 `reset_realtime_dev.py` 完全未处理该目录，导致异常结束后摘要文件无法恢复。
- **新增 Step 3**：删除本次实时测试生成的 `.dev_data/groups/` 目录。
- **新增 Step 4**：按修改时间定位 `archive/groups_<ts>/` 中最新的备份，通过 `shutil.move` 还原至 `.dev_data/groups/`，恢复 `run_webui_dev.py` 的演示摘要状态。
- **修复后覆盖范围**：`reset_realtime_dev.py` 现在完整镜像 `_archive_step()` 的所有三项状态变更（`realtime_test.db` / `dataflow_test.db` / `groups/`），可在任意异常退出后将环境恢复至测试前状态。

#### `run_realtime_dev.py` — 摘要目录归档方式修正
- 将对 `.dev_data/groups/` 的 `shutil.rmtree`（不可恢复）改为 `shutil.move` 到 `archive/groups_<ts>/`，并通过模块级变量 `_archived_groups` 记录归档路径，供正常退出时的 `_cleanup()` 还原使用。

---

## [v0.6.7] — 2026-05-09

### 实时测试脚本运行时修复 (run_realtime_dev.py Runtime Fixes)

#### 1. LLM 提取超时修复
- **根因**：`ExtractorConfig.llm_timeout` 默认 30 s，`asyncio.wait_for` 对 Gemma 26B（thinking 模式下单次调用 60-90 s）必然超时；`asyncio.TimeoutError.__str__()` 为空字符串，导致日志显示 `LLM distillation failed:` 但无报错内容。
- **修复**：`_build_config()` 中新增 `extractor_llm_timeout_seconds`（初始值 150 s，后于 v0.6.9 调整为 300 s），使 asyncio 层超时晚于模型响应。
- **新增 `_RealtimeProviderBridge`**：替代 `MockProviderBridge`，将 httpx 超时扩展至 330 s（初始 180 s，v0.6.9 上调），并在返回前用正则剥离 Gemma/Qwen3 thinking 模式产生的 `<think>…</think>` 标签，防止 JSON 解析器在推理文本中误匹配括号边界。

#### 2. 摘要记忆残留修复
- **根因**：`run_webui_dev.py` 会在 `.dev_data/groups/demo_group_001/summaries/` 写入演示 Markdown 文件，`run_realtime_dev.py` 启动时未清除，导致 WebUI 摘要面板仍显示旧的 demo 内容。
- **修复**：`_archive_step()` 中将 `.dev_data/groups/` 移出（初版用 `shutil.rmtree`，v0.6.8 修正为 `shutil.move` 以支持退出还原），确保每次实时测试启动后摘要面板只显示本次注入生成的内容。

---

## [v0.6.6] — 2026-05-09

### 实时聊天模拟测试工具链 (Realtime Chat Simulation Dev Tools)

#### 1. `run_realtime_dev.py` — 实时数据注入测试脚本
- **数据来源**：解析 `tests/mock_data/mock_realtime.json`（原 `Mock_Realtime_Data.md` 转换而来，包含多个群组），将所有消息通过完整管道（`MessageRouter` → `EventBoundaryDetector` → `EventExtractor` + LLM → 三张数据库表）注入全新的 SQLite 实例（`.dev_data/realtime_test.db`）。
- **归档机制**：启动时自动将已有的 `dataflow_test.db` 复制到 `.dev_data/archive/dataflow_test_<时间戳>.db`；若存在上次崩溃遗留的 `realtime_test.db`，也会被移入归档目录，确保数据不丢失。
- **双阶段进度条**：阶段一显示消息注入进度（单位：msg），阶段二显示 LLM 提取任务进度（单位：task），均支持 `tqdm`；若未安装则回退至内置最小化进度 shim。
- **WebUI 集成**：所有数据注入完成后，在 **2656 端口**启动 `WebuiServer`（`auth_enabled=False`，使用 SQLite 实体库），开发者可直接访问事件流、关系图、摘要记忆三个 UI 界面查看真实数据渲染效果。
- **热键退出**：后台线程监听 Ctrl+Q（Windows `msvcrt`，ASCII 17）；非 Windows 或非 TTY 环境下回退为 `q` + Enter 输入模式。退出时自动停止 WebUI 服务器并删除 `realtime_test.db`，恢复干净状态。
- **LLM 配置**：与 `run_dataflow_dev.py` 完全一致，支持 LMStudio 本地模型（默认）或 DeepSeek 云端模型，`MODE` 变量控制 `encoder` / `llm` 提取策略。
- **零侵入性**：脚本仅调用已有公开 API，不修改 `core/`、`web/` 或 `tests/` 中的任何文件，不影响插件正常功能。

#### 2. `reset_realtime_dev.py` — 紧急状态恢复脚本
- **强制清理**：同步删除残留的 `realtime_test.db`（适用于 `run_realtime_dev.py` 异常崩溃的场景）。
- **自动还原**：按修改时间定位 `archive/` 目录中最新的 `dataflow_test_*.db` 备份，并还原至 `.dev_data/dataflow_test.db`。
- **幂等安全**：使用 `shutil.copy2`（非移动），归档文件始终保留；可多次安全执行。

#### 3. `TODOPLAN.MD` — 实现规划文档
- 在根目录新增实现设计文档，记录两个脚本的架构决策、解析器正则、异步模式与验证步骤，供后续参考。

---

## [v0.6.5] — 2026-05-09

### 摘要架构升级与全量本地化适配 (Summary & Global Localization)

#### 1. 摘要记忆深度增强 (Summary Memory Enhancements)
- **时间范围可视化**：Markdown 摘要标题现在会自动显示所涵盖事件的精确时间段（格式：`YYYY-MM-DD HH:MM - HH:MM`），便于追溯记忆切片。
- **生成频率精细化**：在原有的基础上新增了 2 小时与 3 小时的生成频率选项，支持更密集的记忆固化节奏。
- **自定义字数约束**：新增「摘要字数限制」配置项（支持 200-500 字），并实现了 LLM Prompt 的动态注入与后端逻辑范围锁定。
- **结构化模板升级**：优化了摘要生成的系统指令，强制要求 LLM 采用中括号四段式结构（主要话题、情感动态、关键时间、关系变化），并引入板块间空行大幅提升阅读体验。

#### 2. 国际化与 UI 细节适配 (Localization & UI Refinement)
- **分页系统全量适配**：彻底完成了信息库分页器的多语言化，包括“每页显示”、“项”、“第 X/Y 页”以及“上一页/下一页”按钮。
- **日期选择器本地化**：实现了日期过滤控件的三语适配，支持根据当前语言动态切换“选择日期”与“日期范围”提示。
- **术语体系精简演进**：将中文社交关系标签升级为更精简直观的描述词（亲和、活跃、掌控、高傲、冷淡、孤避、顺应、谦让），并保持了对前三代术语（原型型、支配型、主导型）的完美向下兼容。
- **系统稳定性保障**：
    - **Hydration 冲突修复**：重构了 `AppProvider` 的语言初始化逻辑，彻底解决了 Next.js 服务端渲染与客户端水合不匹配的报错。
    - **防御性渲染修复**：修复了因部分语言包定义缺失导致的 `TypeError` 崩溃，并为日期组件增加了健壮的回退机制。

#### 3. 开发工具链更新 (Dev Tools)
- **LMStudio 高性能适配**：在 `run_dataflow_dev.py` 中内置了最新的 Gemma 26B 本地模型配置，并修正了 API 标识符匹配逻辑，显著提升了 E2E 测试的便利性。

---

## [v0.6.4] — 2026-05-09

### WebUI 交互体验与视觉效果深度优化 (WebUI UX & Visual Overhaul)

#### 1. 关系图交互与导出增强 (Graph Interactions)
- **专业级 SVG 导出**：导出文件名现在会自动包含当前的群组名称，格式为 `RelationGraph_[GroupName].svg`，大幅提升资产管理的便捷性。
- **物理参数知识库 (Tooltips)**：为力导向图的所有核心参数（排斥力、中心引力、边权影响、阻尼、迭代次数）以及功能开关新增了交互式问号提示，点击即可实时查看其对布局影响的科学定义。
- **术语规范化**：响应学术与心理学标准，将社交关系模型中的 **“主导”** 术语全面更名为 **“支配” (Dominant)**，涉及后端逻辑、LLM 提示词、数据库常量及 WebUI 标签，同步补全了日文 (支配) 适配。

#### 2. 视觉渲染引擎优化 (Rendering Logic)
- **动态边宽控制**：新增「默认边宽」调节项，支持 0.5px 至 5.4px (原始 300%) 的实时调节，并以此为基准按比例缩放亲密度/消息数权重。
- **平行线防重叠算法**：重构了双向边的渲染逻辑，增加边宽时两条平行线将向外侧扩张并保持恒定内部间距，彻底解决了高权重下连线堆叠在一起的问题。
- **箭头渲染修正**：
    - **动态缩放**：箭头尺寸上限提升至 64px，并实现了 SVG Marker 随滑块参数的等比例缩放。
    - **精准避让**：连线端点现在会根据目标节点的实时半径自动偏移，确保箭头始终完美衔接在节点边缘，不再被节点遮挡。
- **字体大小自定义**：新增连线标签「显示/隐藏」开关及其字号调节功能（6px - 24px），支持根据缩放倍率自动补偿显示。

#### 3. 插件配置与任务调度优化 (Config & Tasking)
- **「摘要记忆」专属板块**：在插件配置中新增摘要管理区块，将生成频率调节移入其中，使分类逻辑更符合认知。
- **摘要频率精细化**：将摘要生成频率升级为下拉选择模式，支持以 1、4、8、12、24、48 小时为间隔精准控制后台任务的生成节奏。

#### 4. UI 逻辑与国际化 (Logic & i18n)
- **模式感知反馈**：在「环形布局」或「锁定模式」下，暂不可用的物理参数面板会自动变为低对比度灰色半透明状态，清晰指示当前功能的可用性。
- **全量三语补全**：以上所有新增功能、提示词、滑块标签及文件命名逻辑均已完美适配 **中文 (zh)**、**英语 (en)** 和 **日语 (ja)**。

---

## [v0.6.3] — 2026-05-09

### 开发环境修复 (Dev Environment Fixes)

#### 1. 修复演示数据注入 NameError
- **修复缺失导入**：在 `web/server.py` 和 `run_webui_dev.py` 中补全了 `MessageRef` 的导入，彻底解决了在 WebUI 中注入演示数据时提示 「name 'MessageRef' is not defined」 的崩溃问题。
- **同步数据结构**：确保开发环境启动脚本 (`run_webui_dev.py`) 使用与 WebUI 接口一致的最新丰富演示数据集。

---


## [v0.6.2] — 2026-05-09

### 演示数据与测试环境增强 (Mock Data & Dev Env)

#### 1. 演示数据集扩充 (Rich Demo Data)
- **新增人格**：引入了文学爱好者「Diana」，为社交关系图增加了更多样化的节点。
- **情节记忆扩容**：演示事件增加至 8 个，涵盖了技术交流、音乐分享、徒步计划、AI 伦理等丰富场景。
- **语义摘要增强**：为所有演示事件编写了更具描述性的语义摘要（Summary），方便测试搜索与详情展示。
- **社交关系深化**：新增了跨群组的全球范围（global）与特定群组（group-specific）的印象关系，使关系图谱更具层次感。

#### 2. 开发脚本修复
- **同步 Event 模型**：修复了 `run_webui_dev.py` 和 `web/server.py` 中创建演示数据时因缺少必填字段导致的类型错误。

---


## [v0.6.1] — 2026-05-09

### 统计页面显著性增强 (Stats Visibility Boost)

#### 1. 响应时长深度集成 (Response Time Integration)
- **顶层磁贴展示**：在统计页面顶端新增「平均响应时间」核心卡片，直接展示引擎处理任务的总平均耗时。
- **性能细节扩充**：在底层性能面板补全了「总平均处理时长」指标，与子任务耗时形成完整闭环。
- **布局优化**：调整统计网格为 5 列布局，使核心指标（人格、事件、印象、响应、锁定）并排显示，状态感知更直接。

#### 2. 数据可靠性保障
- **后端聚合计算**：修改 `web/server.py`，在 API 层自动聚合核心处理环节的耗时，减少前端计算压力。
- **渲染稳定性**：移除了性能面板的显示门槛，现在页面会始终展示性能统计占位符，即便数据尚未加载完成，提升 UI 稳定性。

---


## [v0.6.0] — 2026-05-09

### 系统同步与性能统计修复 (System Sync & Perf Fix)

#### 1. 修复性能统计缺失问题 (Performance Metrics Fix)
- **后端修复**：修正了 `web/server.py` 中 `stats_data` 方法未包含性能耗时字段的 Bug，现在它能正确从 `core.utils.perf` 获取并返回数据。
- **前端增强**：在「数据统计」页面进入时强制触发数据刷新，确保性能分析面板（情节提取、对话边界、召回耗时等）能够正确渲染，不再因初始化延迟而隐藏。

#### 2. 版本里程碑更新
- **核心适配完成**：完成了从多语言支持、锁定归档机制、情节摘要字段到性能监控的全量适配，系统进入 v0.6.x 稳定开发阶段。

---


## [v0.5.9] — 2026-05-09

### 核心架构与 UI 适配 (Core & UI Sync)

#### 1. 引入情节摘要字段 (Event Summary)
- **核心模型同步**：适配后端 `Event` 模型新增的 `summary` 字段（精简语义摘要），确保情节记忆的完整性。
- **后端持久化**：补全了 `web/server.py` 和 `core/api.py` 中的 CRUD 逻辑，使摘要信息能被正确接收、存储并返回。
- **演示数据更新**：修复了 `run_webui_dev.py` 因缺失 `summary` 参数导致的启动崩溃问题，并补充了高质量的演示摘要内容。

#### 2. 前端展示与编辑增强
- **详情页展示**：在事件流详情卡片和知识库详情行中新增摘要展示区块，采用沉浸式边框设计。
- **表单支持**：在事件创建与编辑弹窗中新增摘要文本域（Textarea），支持手动微调 LLM 生成的摘要内容。
- **国际化补全**：同步补全了摘要字段的中、英、日三语标签。

---


## [v0.6.0] — 2026-05-09

### 核心变更：语义聚类提取与性能监控 (Semantic Partitioning & Performance Monitoring)

#### 1. 语义划分策略升级 (Partitioner Strategy)
- **Encoder 驱动的聚类**：引入了 `BasePartitioner` 抽象层，新增基于 Encoder (如 BGE-small) 的 `SemanticPartitioner`。利用 **DBSCAN 算法** 在数学层面实现话题解交织。
- **话题解交织能力**：系统现在能自动识别并分离同一个消息窗口内交织的多个讨论主题，并将无意义的离群消息判定为噪声。
- **混合动力架构**：支持在 WebUI 中动态切换 `LLM 划分` 或 `Encoder 聚类` 策略。后者极大减轻了 LLM 的逻辑开销。

#### 2. 语义蒸馏与存储优化
- **新增 Summary 字段**：`Event` 领域模型及 SQLite 表结构新增 `summary` 字段（DB Migration 005），专门存储去噪后的语义精华。
- **蒸馏式总结 (Distillation)**：提取流程由“找索引”进化为“写摘要”。LLM 现在只负责对 Encoder 划分好的纯净消息簇生成干货结论，单次响应速度大幅提升。

#### 3. 系统级性能监控 (System Performance Tracking)
- **多阶段耗时追踪**：新增 `PerfTracker` 工具，实时监测并记录 `Partition` (划分)、`Distill` (蒸馏)、`Retrieval` (检索) 和 `Recall` (召回注入) 各阶段的平均用时。
- **前端数据透传**：更新了 `/api/stats` 接口，前端 Dashboard 现在可以实时展示各阶段的性能指标（毫秒级）。

#### 4. 稳定性与 Dataflow 验证
- **全量测试通过**：同步更新并修复了全量 315+ 个测试用例，确保 `summary` 字段的引入不影响历史兼容性。
- **Dataflow 健壮性**：修复了 `run_dataflow_dev.py` 脚本，引入了异常时间戳容错与 LLM 失败逃生机制，显著提升了开发调试的流畅度。

---

## [v0.5.0] — 2026-05-09

### 统计增强与性能分析

#### 1. 新增性能耗时统计 (Performance Metrics)
- **核心流程监控**：在统计页面新增「性能耗时」面板，直观展示情节提取、对话边界检测、长对话提炼、Prompt 注入以及混合检索的平均执行耗时。
- **全量国际化**：同步补全了性能指标的中、英、日三语详细说明与翻译。

#### 2. 系统同步优化
- **API 协议对齐**：更新前端 `Stats` 接口定义，完美适配后端最新的 `perf` 性能跟踪协议。

---


## [v0.5.7] — 2026-05-09

### 修复与完善

#### 1. 关系图谱国际化深度补全 (Graph Localization)
- **语义化标签同步**：移除了关系图谱中硬编码的「友好」、「支配」等中文标签，现在这些标签会随系统语言（中、英、日）同步切换。
- **轴向标注本地化**：图谱详情中的「积极/消极」、「服从/支配」轴向端点已实现全量国际化，支持更直观的跨语言心理模型展示。
- **弹窗与提示汉化**：补全了人格创建、编辑以及印象修改弹窗中的所有描述文本与错误提示。

#### 2. 代码健壮性与清理
- **i18n 文件去重**：清理了 `lib/i18n.ts` 中由于多次迭代产生的重复键位，修复了 TypeScript 编译时对象字面量属性重复的错误。
- **全局错误处理**：将通用的 `deleteFailed` 等状态提示移入 `common` 语言包，提升了代码的复用性与一致性。

---


## [v0.5.6] — 2026-05-09

### 修复与改进

#### 1. 插件配置页面深度优化 (Plugin Config Overhaul)
- **移除冗余选项**：删除了在 WebUI 中关闭 WebUI 的悖论选项 (`webui_enabled`)。
- **全量国际化**：为所有配置项（端口、向量模型、检索参数等）补全了中、英、日三语的详细标签与提示信息，告别硬编码提示。
- **同步后端 Schema**：新增了 `retrieval_active_only` 和 `impression_update_alpha` 等缺失的配置项，确保 WebUI 配置与核心引擎完全同步。
- **依赖联动增强**：优化了配置项之间的禁用/启用联动逻辑（如禁用向量检索时自动灰度相关参数）。

---


## [v0.5.5] — 2026-05-09

### 修复

#### 1. 统计图表颜色与主题同步修复
- **优化 ChartStyle**：现在的图表样式不仅支持系统级暗色模式，还完美支持通过 `.dark` 类手动切换的暗色模式。
- **修复颜色解析**：确保图表颜色变量能准确继承当前选择的主题色（Accent Color），而非固定在初始状态。

---


## [v0.5.4] — 2026-05-09

### WebUI 与力导向图增强

#### 1. 关系图交互优化
- **SVG 导出增强**：导出关系图时，文件名现在会自动包含群组名称（格式：`RelationGraph_[GroupName].svg`），便于管理多个群组的可视化资产。
- **物理参数说明**：为所有核心物理参数（排斥系数、引力、边权影响、阻尼、迭代次数）以及功能开关（防节点重叠、LinLog 模式、抑制枢纽）新增了提示说明（Tooltip），帮助用户理解各参数对布局的影响。
- **术语统一**：将社交关系中的“主导”统一更名为“支配”（Dominant），涉及后端逻辑、LLM 提示词、数据库常量及 WebUI 标签。
- **物理参数预设优化**：调整了力导向图的初始默认值（排斥系数、引力、边权影响等均设为最小值，迭代次数设为 100），提供更清晰的初始布局起点。
- **摘要生成配置**：在插件配置中新增“摘要记忆”板块，支持通过下拉菜单自定义摘要生成频率（1、4、8、12、24、48 小时），并同步更新了后端调度逻辑。
- **交互视觉增强**：在环形布局模式下，所有暂不可用的物理参数现在会以低对比度（灰色/半透明）显示，增强用户对当前模式可用功能的感知。

#### 2. 力导向算法调整
- **排斥系数范围扩展**：将排斥系数（Repulsion）的最大值上限从 15 提升至 30（原来的 2 倍），支持更稀疏的节点分布。
- **引力范围扩展**：将中心引力（Gravity）的最大值上限从 5 提升至 10，增强对大型图谱的向心聚集控制。

#### 3. 全量国际化
- **三语支持补全**：为上述新增的参数说明和导出逻辑补全了中、英、日三语翻译，确保多语言环境下的一致性体验。

---

## [v0.5.3] — 2026-05-09

### Bug 修复

- **修复 WebUI `_handle_demo` 500 错误**：`Impression` 构造调用使用了已废弃的旧字段名（`relation_type/affect/intensity`），导致注入演示数据时返回 500。已更新为当前字段名（`ipc_orientation/benevolence/affect_intensity`），并补充了 `power` 与 `r_squared` 参数。
- **修复 `server.py` 内置 `_seed` 同名问题**：底部开发脚本的 `_seed` 函数存在相同的旧字段问题，直接运行 `python web/server.py` 时会立即崩溃。
- **`stats_data()` 补充 `locked_count` 字段**：后端响应缺少前端类型所要求的 `locked_count`，现已在遍历事件时同步统计锁定数量。
- **`events_data()` 补充 `total` 字段**：响应中补充 `total` 以符合前端 `EventsResponse` 类型定义。
- **修复 `next.config.mjs` dev 模式 API 代理失效**：`output: 'export'` 在 dev 模式下禁用了 rewrites，导致所有 `/api/*` 请求返回 "Internal Server Error"。现通过环境变量判断，在 `next dev` 时跳过 `output: 'export'` 并启用 `skipTrailingSlashRedirect`，确保 API 代理正常工作；`next build` 行为不变。
- **修复 `_handle_spa_fallback` 不识别 Next.js trailingSlash 导出格式**：补充 `{path}/index.html` 检测，正确响应 `/events/` → `output/events/index.html`，避免所有子路由都降级为根页面。

---

## [v0.5.2] — 2026-05-09

### 统计分析与架构增强

#### 1. 数据统计页面 (Statistics)
- **新增统计页面**：在工具栏下新增「数据统计」页面，提供记忆库的全景运行状态分析。
- **时序活跃趋势**：使用 shadcn 风格的图表展示近 30 日的事件发生频率趋势。
- **定性指标分析**：计算并展示平均参与者数、每事件触发的关系推断数、平均记忆重要度等深度指标。
- **集成 Recharts**：引入 recharts 并封装了符合 shadcn 规范的 `Chart` 组件。

#### 2. 多语言与 UI 补全
- **全量国际化**：补全了统计页面及导航栏的中、英、日三语翻译。
- **侧边栏优化**：在侧边栏底部实时显示核心数据计数（人格、事件、印象），增强状态感知。

#### 3. 核心 Bug 修复与持久化
- **修复锁定丢失 Bug**：彻底修复了后端 API 在更新事件时丢失 `is_locked` 和 `status` 字段的问题，确保锁定状态在重启或刷新后依然有效。
- **数据同步优化**：前端锁定操作改为即时局部更新，无需等待全量重新加载，提升交互流畅度。

---


## [v0.5.1] — 2026-05-09

### 前端与多语言增强

#### 1. 多语言支持扩展
- **新增日语 (ja)**：支持中、英、日三语动态切换，完善了全量 i18n 覆盖。
- **类型安全修复**：重构 `I18n` 类型定义，支持递归字符串映射，解决了切换语言时的 TypeScript 类型分配错误。
- **UI 优化**：设置页面的语言切换从 `Select` 升级为 shadcn `Tabs` 组件，提供更直观的交互体验。

#### 2. 事件流视觉与功能增强 (Professional UI)
- **锁定状态 (Locked)**：
    - **时间轴**：锁定事件圆点从空心圈变为实心点 (Solid)，通过视觉重量突出持久化状态。
    - **详情页**：新增左侧彩色装饰条 (Accent Bar) 和 `Lock` 图标，并在标题栏右侧提供快捷锁定/解锁切换按钮。
- **归档状态 (Archived)**：
    - **视觉降权**：归档事件在时间轴上以半透明虚线展示，详情卡片应用去色 (Grayscale) 滤镜，暗示其非活跃状态。
- **快速操作**：修复了 `i18n` 未定义导致的多个组件编译错误，并将归档、锁定等状态操作整合进详情面板。

---


## [v0.5.0] — 2026-05-09

### 核心变更：纯批次 LLM 事件划分 (Pure Batch LLM Event Partitioning)

#### 1. 事件提取流程重构
- **批次触发逻辑**：将事件划分权力从硬编码规则移交给 LLM。`MessageRouter` 现在根据消息计数（默认 20 条）触发批次处理，不再进行单纯的硬性截断。
- **多事件支持**：LLM 现在可以分析一段对话并将其划分为一个或多个逻辑事件，返回精确的消息起始/结束索引。
- **话题继承机制**：引入 `inherit` 字段，支持跨批次话题的自动关联（`inherit_from`），显著提升了长对话的语义一致性。
- **提示词工程优化**：更新了 System Prompt 以支持 JSON Array 输出，并为每条对话消息注入索引编号以便精准定位。

#### 2. 社交认知增强
- **可配置的学习率**：新增 `impression_update_alpha` 配置项。用户可在 WebUI 中调整 Bot 的社交惯性（Alpha 比例，默认为 0.3），平衡 Bot 对新印象的接受度与旧记忆的稳定性。
- **Schema 同步**：更新了 `_conf_schema.json`，为新的配置项提供了详细的中文说明与滑块交互支持。

#### 3. 稳定性与测试修复
- **测试套件全面修复**：修复了因 Impression 模型向 IPC (Interpersonal Circle) 坐标系演进导致的所有 54+ 处历史测试失败，确保核心逻辑 100% 通过。
- **架构解耦**：清理了 `MessageRouter` 与 `EventExtractor` 之间的耦合逻辑，移除了预创建空壳 Event 的冗余流程，使数据流更加清晰。

---

## [v0.4.4] — 2026-05-09

### 核心变更：事件流页面架构重构

#### 1. 登录机制安全性提升
- **Token 认证系统**：实现了配置密码与自动生成 Token 的双轨制。若 `webui_password` 留空，启动时将自动生成随机 Token 并生成带 Token 的访问链接。
- **自动登录**：前端现支持通过 URL 参数 `?token=xxx` 实现静默登录，提升了 headless 部署环境下的可用性。

#### 2. 事件流 (Events) 页面交互重塑
- **常驻侧边栏 (Permanent Sidebar)**：参考关系图页面，将“时间跨度缩放”和“回收站”按钮移至右侧常驻面板，释放了顶部空间。
- **详情展示逻辑优化**：
    - 引入了“欢迎面板”，在未选中事件时提供交互引导。
    - 选中事件后，详情卡片在侧边栏原地平滑切换，不再产生由于侧边栏弹出导致的布局抖动。
- **Header 整合**：将搜索框整合进主 Header，建立了更简洁的“标题 - 筛选 - 内容”三层架构。

#### 3. 视觉与性能修复
- **动画消抖**：修复了事件流页面首次加载时圆圈坐标计算引起的视觉抖动。
- **布局一致性**：严格遵循 shadcn/ui 规范重构了页面容器，解决了侧边栏被筛选栏截断的问题。


记录每个 Phase 的交付内容、关键设计决策及技术细节。

---

## [v0.4.3] — 2026-05-08

### 核心变更：关系图参数全接入

#### 1. msg_count 接入（节点 & 边）
- **后端**：`EventRepository` 新增 `count_messages_by_uid_bulk()`（单次聚合查询，返回全量 `{uid: count}`）和 `count_edge_messages(uid1, uid2, scope)`（按 scope 过滤），SQLite 实现使用 `json_each(events.interaction_flow)` 遍历；In-memory 实现用于测试。
- **后端**：`graph_data()` 重写，为每个 PersonaNode 注入 `msg_count`，为每条 ImpressionEdge 注入 `msg_count`（按 scope 过滤）。
- **前端**：修复 `params-panel.tsx` 的成员列表排序——`msgs-desc` / `msgs-asc` 现在真正按 `msg_count` 降序/升序排列（之前落空为 `return 0`）。
- **前端**：NodeDetail、EdgeDetail 的 "消息数" 字段和 Detail header 的 "总消息" 条目现在有真实数据显示。
- **前端**：`edgeWidthSource = 'msgs'` 和 `gravSource = 'msgs'` 物理参数选项现在使用真实 `totalMsgs` 值（通过 `msg_count` 计算），不再退化为常量 1。

#### 2. 情感映射维度选择器（benevolence ↔ power）
- **前端**：`VisualParams` 新增 `sentimentAxis: 'benevolence' | 'power'`，默认 `'benevolence'`。
- **前端**：`params-panel.tsx` 在"情感着色"开关开启时显示"情感映射维度"选择器（共融轴 B / 支配轴 P）。
- **前端**：`network-graph.tsx` 的 `edgeColor()` 根据 `sentimentAxis` 决定用 `affect`（benevolence）还是 `power` 值来着色边。
- **前端**：`edge-detail.tsx` ImpressionSection 同时显示两条 AffectBar（共融轴和支配轴），AffectBar 支持自定义 `axisLabels`（支配轴端文字为"服从 / 支配"）。
- **前端**：双向综合面板新增"支配性 (P)" AffectBar，与"共融性 (B)"并列显示。
- **前端**：`node-detail.tsx` 连接关系列表中每条边同时展示 B 和 P 两个数值（title 属性标注轴名）。

#### 3. r_squared 可视化
- **前端**：`edge-detail.tsx` ImpressionSection 在两条 AffectBar 下方显示 `IPC 拟合 R² = X.XX`，共享同一个值描述 2D 向量的象限拟合质量。

---

## [v0.4.2] — 2026-05-08

### 核心变更：响应式细节与交互规范化

#### 1. 响应式与排版修复
- **PageHeader 优化**：修复了标题和描述在窄屏下不当换行导致的重叠问题。通过引入 `min-w-0` 和强制 `truncate whitespace-nowrap` 确保了在空间受限时 UI 的整洁。

#### 2. 交互逻辑同步
- **详情面板闭环**：在事件流页面，实现了选中状态与详情侧边栏的深度同步。点击背景或再次点击已选中的事件将自动关闭详情面板。
- **全局刷新反馈**：为所有页面（Events, Graph, Library）的刷新按钮统一引入了 `isRefreshing` 状态控制，点击后将播放 `animate-spin` 旋转动画，增强实时反馈感。

#### 3. 冗余逻辑清理
- **移除多选系统**：根据最新的产品交互规范，彻底移除了事件流页面和知识库页面中的多选删除（selectedIds）逻辑及其相关的 UI 组件（Checkbox、批量删除按钮），回归轻量化的单点管理模式。

---

## [v0.4.1] — 2026-05-07

### 核心变更：交互体验与动效优化

#### 1. 平滑动效系统
- 为事件流（Event Flow）所有 SVG 元素（坐标轴、继承线、节点、文本）引入了全量 CSS 过渡动画。
- **平滑缩放**：调整时间跨度（Time Gap）时，时间轴及所有关联事件将以 `0.4s ease-out` 的节奏平滑重排，消除了瞬间跳变的生硬感。

#### 2. 持久化选中状态
- **节点交互反馈**：新增 `selectedEventId` 状态。点击事件节点后，该节点将保持“实心”高亮状态。
- **取消选择**：点击时间线背景区域可自动清除选中状态，使 UI 状态反馈符合直觉。

---

## [v0.4.0] — 2026-05-07

### 核心变更：事件流重构与全局筛选系统统一

#### 1. 事件流（Event Flow）深度优化
- **动态轴缩放**：引入时间跨度（Time Gap）滑块，支持 30m 至 7d 的离散缩放，替代了原本无实质含义的密度拉条。
- **事件堆叠（Event Stacking）**：
    - 同一时间槽及线程内的事件现在以“叠放”形式展示，通过圆圈大小和透明度递减体现视觉深度。
    - **悬停交互升级**：悬停于堆叠点时自动展开（水平平铺），允许用户精准查看并交互（编辑/删除）其中的每一个子事件。
- **继承线视觉改良**：被过滤或截断的父事件连接线改为渐弱的虚线，并带有呼吸动画，增强了时序溯源的直观性。

#### 2. 全局筛选系统重构（`FilterBar`）
- **组件化统一**：抽离了原本分散的筛选逻辑，建立了统一的 `FilterBar` 共享组件。
- **布局优化**：采用 Flex 布局替代硬编码比例，左侧标签筛选（TagFilter）与右侧时间筛选自动对齐，中间通过垂直 `Separator` 分隔。
- **UI 对齐**：所有筛选控件强制顶部对齐，确保不同长度标题下的对齐一致性。
- **修复视觉 Bug**：删除了 `TagFilter` 的冗余边框，解决了 Filter 栏底部双线条问题。

#### 3. 增强型时间范围选择器（`DateRangePicker`）
- **Shadcn 规范重塑**：遵循官方最佳实践，将分离的日期输入框改为单一触发按钮 + 双月份联动日历（Multi-month calendar）。
- **交互提升**：支持在一个弹窗内完成开始与结束日期的点选，极大提升了跨月选择的效率。

#### 4. 全局功能下沉
- **关系图（Graph）集成**：在群组列表页引入了 `FilterBar`，支持按人格最后活跃时间过滤群组。
- **数据库（Library）增强**：为事件与人格选项卡新增了完整的时间范围筛选能力，支持按时序精准定位历史记录。

---

## [v0.3.0] — 2026-05-06

### 核心变更：IPC 社交取向分析系统（Phase A + C）

#### 1. Impression 数据模型重构（Breaking Change）
- 旧字段 `relation_type` → `ipc_orientation`（8 种 IPC 中文标签）
- 旧字段 `affect` → `benevolence`（亲和轴 [-1, 1]）
- 旧字段 `intensity` → `affect_intensity`（IPC 模长 [0, 1]）
- 新增 `power`（支配轴 [-1, 1]）、`r_squared`（八分区归属置信度 [0, 1]）
- 新增常量 `IPC_VALID_ORIENTATIONS`（frozenset，8 个中文标签）
- 新增 `BigFiveVector` 冻结 dataclass（OCEAN 各维 [-1, 1]，含 `__post_init__` 范围校验）

#### 2. DB Migration 004
- `migrations/004_ipc_impression.sql`：RENAME COLUMN 及 ADD COLUMN 变更
- 旧 relation_type 语义保留注释：friend→友好, rival→敌意, colleague→主导友好 等

#### 3. IPC 数学模型（`core/social/ipc_model.py`）
- `classify_octant(B, P) → str`：atan2 最近八分区标签
- `affect_intensity(B, P) → float`：`√(B²+P²)/√2`，[0,1]
- `r_squared(B, P) → float`：`1 - d²/(r+ε)²`，d=点到质心距离
- `bigfive_to_ipc(bfv) → (B, P)`：Procrustean 旋转（DeYoung 2013 近似系数）
- `derive_fields(B, P) → (orientation, intensity, r²)`：便捷组合函数

#### 4. Big Five 评分基础设施（`core/social/big_five_scorer.py`）
- `BigFiveScorer(Protocol)`：可替换接口（未来 BERT 实现兼容）
- `LLMBigFiveScorer`：单次 LLM 调用 → `{"O":f,"C":f,"E":f,"A":f,"N":f}`，超时/解析失败 fallback 零向量
- `BigFiveBuffer`：per-session per-user 消息计数 + BigFiveVector 缓存，X 条消息触发后台异步评分

#### 5. 社交取向分析器（`core/social/orientation_analyzer.py`）
- `SocialOrientationAnalyzer.analyze(window, buffer, salience, scope) → int`
- per (observer, subject) pair：BigFive 缓存 → IPC 坐标 → 事件显著性加权 → 衍生字段
- EMA 融合（α=0.3）：新印象 = 0.3×新值 + 0.7×旧值

#### 6. EventExtractor 集成（`core/extractor/extractor.py`）
- 修复 Bug：`self._system_prompt` 和 `self._llm_timeout` 之前从未从 `cfg` 赋值
- 新增可选参数：`big_five_buffer`, `orientation_analyzer`, `ipc_enabled`
- 事件关闭后台任务：喂入消息到 BigFiveBuffer → 触发 maybe_score → 运行 IPC 分析

#### 7. 配置扩展（`core/config.py`）
- 新增 `IPCConfig` dataclass：`enabled`, `bigfive_x_messages`, `bigfive_llm_timeout`
- `PluginConfig.get_ipc_config()` 读取 `ipc_enabled`, `bigfive_x_messages`, `bigfive_llm_timeout_seconds`

#### 8. 组件连接（`core/plugin_initializer.py`）
- 按 `ipc_cfg.enabled && relation_enabled` 条件构建 `BigFiveBuffer` + `SocialOrientationAnalyzer`
- 修复 `_maybe_trigger_impression`：旧 IPC 字段名（`relation_type`, `affect`, `intensity`）全部替换为新 IPC 字段；规则启发式 colleague→主导友好, stranger→友好

---

## [v0.2.2] — 2026-05-06

### 核心变更

#### 1. 向量嵌入 (Embedding) 引擎升级
- **API 接入支持**：新增 `ApiEncoder`，支持调用 OpenAI 兼容的远程 Embedding API。
- **并发与批处理引擎**：新增 `EmbeddingManager` 作为向量请求的中转中心，支持请求队列化、自动批处理 (Batching) 和并发信号量 (Semaphore) 控制。
- **智能重试机制**：新增 `core/utils/retry.py` 抽象重试层，支持最大重试次数、重试延迟和指数退避 (Exponential Backoff)，提升外部 API 调用的鲁棒性。

#### 2. 深入配置控制与 WebUI 升级
- **动态配置面板**：WebUI 配置页已全面适配 17 个新增参数，支持 `select` 枚举选择（如 Provider 切换）与分组管理。
- **Dashboard 增强**：首页新增“已锁定记忆”统计卡片，实时监控受保护记忆规模。
- **记忆锁定 UI**：
    - 在事件流时间线（Timeline）气泡卡片中显示 🔒 图标。
    - 事件编辑与创建对话框中集成“锁定记忆”开关。
    - 详情面板展示同步后的锁定状态。

### 技术细节
- **类型安全**：重构了前端 `ApiEvent` 和 `Stats` 定义，确保 `is_locked` 与 `locked_count` 全链路类型检查。
- **构建优化**：完成了前端 `npm run build` 校验，确保 Next.js 静态导出的代码健壮性。
- **重构 Encoder 协议**：新增异步 `encode_batch` 接口。本地模型（SentenceTransformers）通过 `asyncio.run_in_executor` 下沉至线程池执行以防止阻塞事件循环。
- **智能重试集成**：`PluginInitializer` 切换为使用 `EmbeddingManager` 代理所有内部组件（如 `Extractor` 和 `HybridRetriever`）的向量化请求。
- 新增 `tests/test_embedding_manager.py` 和 `tests/test_retry.py` 确保并发时序和容错逻辑正确。

---

## [v0.2.1] — 2026-05-06

### 核心变更

#### 1. 虚拟上下文管理 (VCM) 与 ContextManager
- **统一调度**：新增 `core/managers/context_manager.py`，集中管理所有活跃会话窗口（MessageWindow）。
- **内存优化**：实现 LRU 缓存（`context_max_sessions`）与 TTL 过期自动清理（`context_session_idle_seconds`）。
- **状态机逻辑**：引入 VCM 状态机（FOCUSED, RECALL, EVICTION, DRIFT），动态调节记忆检索权重与上下文压力。

#### 2. 记忆自动清理与保护
- **自动代谢**：实现基于重要度阈值（`memory_cleanup_threshold`）的周期性自动删除任务。
- **锁定保护**：为 `Event` 模型新增 `is_locked` 字段，允许手动锁定关键记忆以豁免清理。
- **物理删除**：清理逻辑同步覆盖数据库记录及其关联的向量索引。

#### 3. 配置项增强
- 新增 `vcm_enabled`、`context_window_size` 等 7 个可配置项，支持在 WebUI 实时调整。

### 技术细节
- **数据库迁移**：新增 `003_event_locked.sql` 迁移脚本。
- **API 扩展**：`core/api.py` 统计接口新增 `locked_count` 支持。
- **稳定性保证**：新增 `tests/test_context_manager.py` 与 `tests/test_memory_cleanup.py`；增强 `run_core_dev.py` 全链路测试。

---

## [v0.2.0] — 检索增强与架构重构 — 2026-05-05

### 核心变更
- **混合检索升级**：引入 RRF (Reciprocal Rank Fusion) 融合 BM25 与向量搜索；支持 `active_only` 归档过滤。
- **RecallManager**：新增统一召回管理器，支持 `system_prompt`、`user_message`、`fake_tool_call` 等多种注入模式。
- **插件架构重构**：引入 `PluginInitializer` 和 `EventHandler` 剥离业务逻辑，精简 `main.py` 入口。
- **WebUI 全面重塑**：迁移至 Next.js + shadcn/ui 架构，支持二级认证（Login/Sudo）与插件面板挂载。

---

## [v0.1.0] — 基础架构实现 — 2026-05-03

### 核心变更
- **三轴记忆模型**：建立 Episode (事件), Relation (社交), Narrative (摘要) 核心领域模型。
- **双引擎存储**：实现 SQLite (FTS5) + sqlite-vec (向量) 持久化层。
- **Markdown 投影**：支持将数据库状态投影为可阅读/编辑的本地 Markdown 文件，并实现双向同步。
- **基础任务**：实现重要度衰减、画像合成与自动摘要生成的后台调度。