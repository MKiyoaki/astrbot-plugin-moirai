# TODO

### 插件多语言支持（i18n）
在 `.astrbot-plugin/i18n/` 下创建 `zh-CN.json` 和 `en-US.json`，覆盖：
- `metadata.yaml` 的 `display_name`、`desc`
- `_conf_schema.json` 所有字段的 `description`、`hint`、`labels`

不动源码，只新增两个 JSON 文件。

### 前端对于archieved事件的相关管理显示和支持功能

---

## 后端架构优化与演进 (Refinement & Evolution)

### [设计] 叙事轴摘要向量化与分层 RAG
目前“每日摘要”仅作为 Markdown 文件存储。应将其向量化并存入 `events` 表（标记为 `type: narrative`），使 `RecallManager` 能够直接检索高概括性的摘要。实现分层 RAG 策略：宏观问题匹配摘要层，微观细节匹配情节层，提升 Token 效率。

### [性能] 周期性维护任务合并 (Consolidation Task)
将 `persona_synthesis`（人格合成）与 `impression_recalculation`（印象重算）合并。目前两者均涉及全量 Persona 扫描及关联 Event 查询，合并后可实现一次扫描、多重更新，预计降低 40% 以上的 IO 负载。

### [质量] 语义提取策略预筛选
在 `SemanticPartitioner` 分段后、LLM 蒸馏前，增加“噪声过滤”步骤。剔除聚类结果中的表情包、复读、打卡等无意义消息，降低 LLM 幻觉风险并节省 Token。

### [架构] 统一 SSOT 与同步边界清理
明确数据库为唯一事实源（Single Source of Truth）。Markdown 投影应定位为“只读产物”或“离线备份”。除了 `IMPRESSIONS.md` 外，不鼓励其他文件的反向同步，转而强化 WebUI 的富文本/结构化编辑能力。

