# CHANGELOG

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