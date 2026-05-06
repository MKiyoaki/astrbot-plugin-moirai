# CHANGELOG

记录每个 Phase 的交付内容、关键设计决策及技术细节。

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
