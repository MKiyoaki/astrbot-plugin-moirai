# TODO

### 插件多语言支持（i18n）
在 `.astrbot-plugin/i18n/` 下创建 `zh-CN.json` 和 `en-US.json`，覆盖：
- `metadata.yaml` 的 `display_name`、`desc`
- `_conf_schema.json` 所有字段的 `description`、`hint`、`labels`

不动源码，只新增两个 JSON 文件。

### 前端对于archieved事件的相关管理显示和支持功能

---

## 后端架构优化与演进 (Refinement & Evolution)

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

---

## 待确认的设计决策（Deferred Decisions）

### [设计] narrative Event 的 inherit_from 下钻
当前 narrative Events 的 `inherit_from` 为空列表，不指向当天的 episode events。
待评估：向 `inherit_from` 写入当天所有 episode event_id 的 payload 开销（每天数十个 ID），
以及是否对”宏观→微观”上下文展开有实际价值。

### [架构] IMPRESSIONS.md 反向同步的长期去向
当前：FileWatcher（30s 轮询）+ 正则解析器，维护成本较高。
待评估：是否在 WebUI 新增直接的 impression 表单提交 API，将 FileWatcher 降级为”离线备份”入口。

### [设计] 分层 RAG 查询分类器精度提升
当前实现：关键词计数投票（`_MACRO_KWS` / `_MICRO_KWS`）。
待评估：接入轻量 embedding 相似度或 LLM 分类提升精度，但需权衡延迟开销。

### [可选优化] `run_memory_cleanup` 返回值 double-counting
`core/tasks/cleanup.py` 中 `total += archived` + `total += deleted` 会对同一次运行中
先被归档、后被永久删除的事件计数两次（测试失败：`test_memory_cleanup.py::test_cleanup_locked_event_not_deleted`）。
数据安全不受影响（`is_locked` 保护正常），仅影响返回值统计语义。
修复方案：只 `return deleted`，或改为返回 `{"archived": archived, "deleted": deleted}`。

