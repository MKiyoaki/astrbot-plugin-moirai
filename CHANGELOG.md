# CHANGELOG

记录每个 Phase 的交付内容、关键设计决策及技术细节。

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
