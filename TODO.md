# TODO

### 情绪四维状态（Soul Layer）设计 [Done]
参考 angel_memory 的 tanh 弹性算法，用四个 -20~+20 能量维度（RecallDepth / ImpressionDepth / ExpressionDesire / Creativity）映射为行为参数。结合 SOUL.md 形成双层体系：
- **长期人格层**：Big Five（由 `persona_synthesis` 周期生成，写入 SOUL.md）
- **短期状态层**：四维能量（每轮对话后 tanh 衰减更新，写入 session 状态）
- 两层分别注入 system prompt 不同位置（长期在 persona 段，短期在当前状态段）

---

### 加权随机检索
在 `HybridRetriever` 的 RRF 融合结果上加一层 softmax 采样，替代确定性 top-K 截断。用分数作为权重做带放回采样，让 bot 的记忆表现更接近人类的"有时想起、有时忘记"，避免永远只检索到同几条高分事件。改动范围：`core/retrieval/hybrid.py` 一个函数，可配置开关。

### LLM 主动记忆工具调用 [Done]
在 AstrBot `@filter.on_llm_request()` 钩子层面注册两个 tool：
- `core_memory_remember(content, strength)`：模型主动触发存储，写入 Event
- `core_memory_recall(query)`：模型主动触发检索，返回相关记忆片段

让模型自主决定何时存储和检索，而不是系统被动注入。不改 `core/` 存储层，只在 adapter 层增加 tool 定义。

### Sleep Consolidation 强化 [Done]
在 `daily_maintenance` 的 cleanup 阶段，将"显著性低于阈值"的事件改为降级到 `archived` 状态，而非直接物理删除。只有 `archived` 超过保留期（如 30 天）的事件才真正删除。现有 `archive_event()` 接口已存在，只需修改 `run_memory_cleanup` 的删除逻辑。

### 指令集配置 [Done]
使用 `@filter.command()` 体系为插件注册管理指令，按 command group 层级组织：

```
/mrm
  ├── status          查询插件运行状态（事件数、任务状态）
  ├── run <task>      手动触发周期任务（decay / synthesis / summary）
  ├── flush           清空当前 session 窗口
  ├── recall <query>  手动触发记忆检索并返回结果
  ├── help            显示插件指令介绍
  ├── webui on        启用并返回webUI访问链接
  └── webui off       关闭webUI功能
```

### 插件多语言支持（i18n）
在 `.astrbot-plugin/i18n/` 下创建 `zh-CN.json` 和 `en-US.json`，覆盖：
- `metadata.yaml` 的 `display_name`、`desc`
- `_conf_schema.json` 所有字段的 `description`、`hint`、`labels`

不动源码，只新增两个 JSON 文件。

### WebUI 接入 AstrBot 官方 Plugin Pages (https://docs.astrbot.app/dev/star/guides/plugin-pages.html)

当前架构：独立 `aiohttp` server（端口 2655）+ Next.js SPA（`web/frontend/output/`）+ 自定义 Session 鉴权（`web/auth.py`）。

目标：迁移到 AstrBot Plugin Pages 标准（`pages/moirai/index.html` + `context.register_web_api()` + `window.AstrBotPluginPage` bridge），由 AstrBot 统一管理端口和鉴权。`core/` 全程不动。

**阶段 1 — 后端路由迁移**（可独立先做）
- 从 `web/server.py` 提取所有 handler 函数到 `web/plugin_routes.py`
- 改用 `context.register_web_api()` 批量注册（约 40 条路由），挂载到 `/api/plug/<plugin_name>/`
- 删除 `web/auth.py`（鉴权交 AstrBot）和 `web/registry.py`（PanelRegistry）
- 考虑在Astrbot的规范下PanelRegistry的功能是否还可以实现，如何可以的话怎么实现
- `web/server.py` 降级为纯本地调试入口
- `main.py` 替换 `WebuiServer.start()` 为路由注册调用

**阶段 2 — 前端构建适配**（主要风险点）
- `next.config.mjs` 加 `output: 'export'` + `trailingSlash: true`，`distDir` 指向 `../../pages/moirai`
- 验证 Next.js App Router 静态导出后客户端路由能否从单一 `index.html` 入口正常工作（AstrBot iframe 不做 SPA fallback）

**阶段 3 — API 适配层**
- `web/frontend/lib/api.ts` 加 bridge 检测：`window.AstrBotPluginPage` 存在时走 `apiGet/apiPost`，否则走原 `fetch`，保留本地调试双路径兼容


### 前端对于archieved事件的相关管理显示和支持功能

### 重构web/frontend/app/events页面中的组件，将event，时间轴等独立组件拆分出来放置在`web/frontend/components/events`中

---

## 后端架构优化与演进 (Refinement & Evolution)

### [设计] 叙事轴摘要向量化与分层 RAG
目前“每日摘要”仅作为 Markdown 文件存储。应将其向量化并存入 `events` 表（标记为 `type: narrative`），使 `RecallManager` 能够直接检索高概括性的摘要。实现分层 RAG 策略：宏观问题匹配摘要层，微观细节匹配情节层，提升 Token 效率。

### [性能] 周期性维护任务合并 (Consolidation Task)
将 `persona_synthesis`（人格合成）与 `impression_recalculation`（印象重算）合并。目前两者均涉及全量 Persona 扫描及关联 Event 查询，合并后可实现一次扫描、多重更新，预计降低 40% 以上的 IO 负载。

### [鲁棒] 全局 LLM 任务队列管理 [Done]
目前已实现 `LLMTaskManager` 全局单例，通过 `llm_concurrency` 配置项统一限制 `Extractor`、`Summary`、`Synthesis` 等组件对 LLM Provider 的瞬时并发压力，防止 API 击穿。

### [质量] 语义提取策略预筛选
在 `SemanticPartitioner` 分段后、LLM 蒸馏前，增加“噪声过滤”步骤。剔除聚类结果中的表情包、复读、打卡等无意义消息，降低 LLM 幻觉风险并节省 Token。

### [架构] 统一 SSOT 与同步边界清理
明确数据库为唯一事实源（Single Source of Truth）。Markdown 投影应定位为“只读产物”或“离线备份”。除了 `IMPRESSIONS.md` 外，不鼓励其他文件的反向同步，转而强化 WebUI 的富文本/结构化编辑能力。

