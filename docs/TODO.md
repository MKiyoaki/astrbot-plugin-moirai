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

## 待讨论的功能方向（Feature Discussions）

### [设计] 用户预设关系（Preset Impressions）

**背景**：目前 Impression 完全由 LLM 从对话中自动提取。希望支持管理员/用户为 bot 预设对某人的先验态度（如"朋友""仇人""亲人"），在 LLM 提取功能关闭时也能对 agent 行为生效。

**讨论中的分歧**：
- 预设关系使用枚举模板（朋友/仇人/亲人），由系统映射到 benevolence × power 双轴数值，`confidence` 设低（约 0.2）标记为先验；随真实对话积累会被更高置信度数据覆盖
- 担忧：双轴数值是从真实行为拟合来的，手动填入破坏数据来源一致性；且先验关系在 agent 判断中的权重理应很低

**两个待决定的子问题**：

1. **是否注入 system prompt？**
   - 仅可视化：出现在关系图中，不影响 agent 行为，完全安全
   - 注入 prompt：用弱化语气（"据初始设定，与 TA 关系为朋友"），对 agent 有实际影响，但权重难以精确控制
   - 折中：作为独立字段注入，与自动提取的 impression 分开，prompt 里明确区分两者来源

2. **数据存储位置**
   - 方案 A：写入现有 `Impression` 表，加 `is_pinned` flag 区分人工 vs 自动，extractor upsert 时跳过 pinned 记录
   - 方案 B：独立的 `PresetRelation` 表，完全不混入自动提取数据，判断结构无污染，但需要新增 repo/schema

**倾向**：方案 B + 仅可视化作为 MVP，后续视需求再开启 prompt 注入开关。

---

### [设计] 关系图管理操作（Graph CRUD）

**背景**：目前缺少对关系数据的精细化管理入口。

**合理的操作（待实现）**：
- 删除单条 impression：`DELETE /api/impressions/{observer}/{subject}/{scope}`
- 按 group 批量清除 impression（加确认弹窗）
- WebUI Library 页面对 impression 的直接删除入口

**不合理的操作（不做）**：
- 手动新建 persona（无行为依据，产生"无根"节点）
- 手动拖拽/重排关系图拓扑（破坏事件驱动的数据一致性）

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

