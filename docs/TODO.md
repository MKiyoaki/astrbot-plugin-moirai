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

- [x] **Event Stream 可视化重构**：已并入 v0.15.0，见下方计划。
- [ ] **预设关系（Preset Impressions）**：管理员/用户预设 bot 对某人的先验态度（朋友/仇人/亲人），关闭 LLM 提取时也生效
  - **设计方向已确认（2026-05-21）**：
    - 不新建独立表；直接 upsert 到现有 `Impression` 行，`confidence=1.0` 表示用户显式设定，权重最高
    - 阈值方案：`benevolence > 0.5` 为正向强，`0 < b ≤ 0.5` 为正向弱，`-0.5 ≤ b < 0` 为负向弱，`b < -0.5` 为负向强（用 ±0.5 作对称边界，非启发式）
    - 预设枚举 → `(benevolence, power)` 坐标映射：
      - `lover`  → (0.85, -0.2)；`friend` → (0.55, 0.0)；`neutral` → (0.0, 0.0)
      - `cold`   → (-0.4, 0.1)；`hostile` → (-0.8, 0.3)
    - 交互入口：`/mrm benevolence <uid> <preset>`；如果记录不存在则新建，存在则覆盖 benevolence/power 并强制 confidence=1.0
    - impression 注入段（`_build_relation_segment`）需同步加阈值行为指令（如 `benevolence > 0.5` → "可以用较温暖的语气回应"），实现类 Lily 好感度的 prompt 效果
  - 待实现子项：
    - [ ] `command_manager.py` 新增 `/mrm benevolence` 子命令，解析 uid + preset，调用 impression_repo.upsert
    - [ ] `recall_manager._build_relation_segment` 追加阈值行为指令文本
    - [ ] i18n 三语（preset 名称 + 命令帮助 + 行为指令文本）
    - [ ] 测试：preset upsert 覆盖旧行 / 新建行 / 阈值指令文本输出
- [ ] **WebUI Library 页面 Impression 直接删除入口**：Library 当前主要管理事件/人格/群组；后续增加 impression 表视图再接入

### 待确认设计决策

- [ ] **Narrative Event `inherit_from` 下钻**：向 `inherit_from` 写入当天所有 episode event_id 的 payload 开销评估（每天数十个 ID），以及对"宏观→微观"上下文展开的实际价值
- [ ] **`IMPRESSIONS.md` 反向同步长期去向**：当前 FileWatcher（30s 轮询）+ 正则解析维护成本高；评估是否新增 WebUI 直接 impression 表单提交 API，将 FileWatcher 降级为"离线备份"入口
- [ ] **分层 RAG 查询分类器精度提升**：当前关键词计数投票；评估接入轻量 embedding 相似度或 LLM 分类，但需权衡延迟开销

---

## v0.16.3 全程序事件提取效率与召回质量修复 (in progress)

### User constraints / 约束
- 当前同时对比 `EVENT_MODE = "encoder"` 与 `EVENT_MODE = "llm"` 的 realtime dev 表现。
- 这次目标是优化实际插件运行链路；`run_realtime_dev.py` 只是复现、压测和验收入口，不能只修 dev runner。
- 所有改动内容必须通过验证；未验证项只能保持 `[ ]` 并写清剩余风险。
- 先根据 realtime dev 日志登记可疑问题；执行前再确认优先级与实现方案。
- 保持 `run_realtime_dev.py` 的诊断输出，后续每次优化都用同一组 mock 数据对比。

### Release goal / 本次版本目标和预期
- 目标 1：修复核心事件提取、事件索引、记忆召回链路中的质量问题，实际插件环境和 dev runner 使用同一套核心逻辑。
- 目标 2：让 `run_realtime_dev.py` 能同时验证“事件提取质量”和“语义召回质量”，不再出现 LLM 模式只能测提取、不能测 vector recall 的盲区。
- 目标 3：确定后续默认推荐路径。当前观测显示 LLM 模式事件粒度更符合预期；encoder 模式保留为性能/无 batch LLM 切分的对照路径，但需要优化重复编码与过度碎片化。
- 目标 4：降低实际运行和 realtime dev 的不可解释耗时。需要能看到每个窗口的 message_count、partition_count、LLM duration、fallback/parse 状态，并能定位长尾窗口。
- 目标 5：降低无证据召回污染。查询包含明确实体/作品名但候选没有词面证据时，应返回 0 条或注入明确 no-evidence，而不是注入语义相近但无关的事件。
- 预期验收：
  - LLM 模式支持 `LLM extraction + encoder retrieval/indexing` 后，`Vector candidates` 不再固定为 0。
  - encoder 模式 partition 阶段复用已有 embedding 后，`partition avg` 明显低于当前 27s 基线。
  - `parse_error` fallback 至少可解释；优先通过 retry/repair 避免低质量 fallback event。
  - tag 不再出现人名、完整原文片段、纯问候语、URL 截断文本。
  - `task_summary` / `task_synthesis` 不再显示误导性的 0.000s。

### Observed baseline / 观测基线
- 数据集：`mock_realtime.json`，225 messages，2 groups。
- encoder 模式：12 extraction tasks → 26 events；事件平均 8.50 source messages；多三元组 summary 8/26；低置信事件 4/26；raw messages persisted=225，event-message links=221。
- encoder 性能：Phase 1 ingestion 约 2.7s；Phase 2 extraction 约 90s；`partition avg=27.194s`、`distill avg=7.865s`、`recall_search=5.016s`。
- encoder 召回：查询“卿泽对原神的看法”时 BM25=0、Vector=20，最终注入 3 条无原神证据的事件；严格 prompt 能正确回答“没有相关证据”。
- LLM 模式：19 extraction tasks → 19 events；事件平均 11.84 source messages；多三元组 summary 15/19；低置信事件 1/19；raw messages persisted=225，event-message links=225。事件粒度明显优于 encoder 模式。
- LLM 性能：Phase 1 ingestion 约 2.9s；Phase 2 extraction 约 45s；`extraction avg=12.859s`、`last=46.132s`。总体比 encoder 模式快，但存在单个长尾窗口。
- LLM 召回：BM25=0、Vector=0、Injected=0。原因是 realtime runner 在 LLM 模式下使用 `NullEncoder`，没有向量索引；因此 LLM 模式当前只能测试提取质量，不能测试语义召回质量。
- LLM 稳定性：出现一次 `parse_error` fallback（message_count=2），生成 confidence=0.20 的低质量 fallback event，topic 包含 URL 截断文本。
- 2026-05-22 LLM 回归：12 extraction tasks → 12 events；平均 18.75 source messages；multi-triple 8/12；低置信 0；raw/event links 225/225，说明“LLM 单事件完整窗口覆盖”生效。
- 2026-05-22 tag 回归：tag 已更具体（如 `大五人格`、`性格分析`、`学术化要求`、`调戏对话`、`游戏攻略`、`记忆系统`），但平均 3.42 tags/event 偏多，且缺少上层类别聚合，适合引入“预设类别 tag + 具体 tag”的层级模型。
- 2026-05-22 recall benchmark：无证据查询正确 hits=0；但 `gariton`、`big-five`、`fee`、`academic` 等有证据查询 hits=0，`arknights` 命中也不精确，说明 no-evidence guard 与 query term 抽取/层级 tag/FTS tokenization 需要继续调。
- 2026-05-22 00:30 LLM 回归：12 extraction tasks → 12 events；平均 18.75 source messages；links 225/225，事件覆盖稳定；`gariton`/`arknights`/`big-five` 已可召回，`fee` 仍命中宽泛事件，`academic` 跨 group 仍漏召回。
- 2026-05-22 00:30 LLM 效率：Phase 2 wall time 约 60s；单任务 `extraction avg=36.815s last=50.787s`，说明并发隐藏了部分长尾；`recall_search≈5.02s` 主要来自 embedding 默认 5s 节流，不是回答 LLM 慢。
- 2026-05-22 00:39 LLM 回归：12 extraction tasks → 12 events；links 225/225；avg tags/event=3.58；multi-triple 6/12；低置信 1（`简短呼唤`），说明整体覆盖稳定但小窗口/低信息窗口仍会产生低置信事件。
- 2026-05-22 00:39 recall 效率验证：`recall_search` 从约 5.02s 降至约 0.074s，确认 embedding 默认节流修复有效；这项改动在实际 AstrBot 路径中也生效，因为默认值来自 `core.config.EmbeddingConfig` 和 `_conf_schema.json`，不是 dev runner 私有逻辑。
- 2026-05-22 00:39 recall 质量：无证据原神查询 hits=0；`gariton` hits=3、`arknights` hits=1、`big-five` hits=1；`fee` 仍命中宽泛事件；`academic` 在 group=1919810 仍 hits=0。下一轮重点是 narrow evidence scoring 和跨 group/topic term 覆盖。

### Priority / 优化优先级

#### 重要
- [x] **解耦提取策略与召回 encoder**：实际插件已由 `embedding_enabled` 独立控制召回/indexing encoder；dev runner 已同步为 `EVENT_MODE = "llm"` 时默认加载 retrieval/indexing encoder（可由 `RETRIEVAL_ENCODER_ENABLED` 关闭），避免 LLM 模式 `Vector candidates = 0`。
- [x] **复用窗口内已计算 embedding**：`SemanticPartitioner` 已优先复用 `MessageWindow.messages[*].embedding`，仅对缺失向量调用 `encoder.encode_batch`，并兼容 numpy/list 向量。
- [x] **补充每窗口性能与质量诊断**：`EventExtractor.__call__` 已记录 session、strategy、message_count、partition_count、event_count、low_conf、duration、event_ids；runner 已输出 event quality、recall diagnostics、完整 perf metrics。
- [x] **LLM parse_error 处理**：`_extract_batch` 已在 parse 失败时记录 response snippet 并追加一次严格 JSON repair LLM 调用；repair 仍失败才 fallback。
- [x] **召回 no-evidence guard**：`RecallManager.recall()` 已对 vector-only 候选做显式实体词覆盖检查；当没有任一候选同时包含查询实体词时返回 0，避免“原神无证据”污染注入。
- [x] **tag/topic 清洗**：`EventExtractor` 已过滤人名/UID、URL、纯问候、过长或句子化 tag；topic 已移除 URL 并限制长度。
- [x] **性能指标修正**：`run_group_summary()` / `run_persona_synthesis()` 的 `task_summary` / `task_synthesis` 计时已覆盖完整任务体，不再只计 config 初始化。
- [x] **tag normalisation 具体性回归测试**：当前 tag 已变干净，但有过度归并到 `社交/情感/娱乐/知识/技术` 等大类的风险；本轮已禁止种子大类有损吸附具体 tag，并补充 `明日方舟十四章`、`大五人格分析请求`、`凸优化` 等保留测试。
- [x] **LLM 单事件完整窗口覆盖**：LLM 模式 12 events / 201 links 暴露出单事件 `start_idx/end_idx` 未覆盖完整窗口，导致 24 条非噪声消息未链接；本轮已在 LLM 单 DB Event 时强制覆盖完整窗口消息。
- [x] **预设 tag 层级分类**：当前 tag 具体性变好但偏多，且召回缺少类别桥接。本轮已实现派生式一对一映射：`chat_content_tags` 保留具体主题词，`tag_categories` 以 `{具体tag: 预设category}` 形式由规则派生并通过 API 输出；暂不做数据库迁移。
- [x] **有证据召回漏召回修复（第一轮）**：benchmark 显示 `Gariton`、`大五人格`、`导师/稿费`、`学术圈靠关系` 有证据查询未命中。本轮已过滤“谁/请求/发生/互动/问题”等问题词，并让 evidence filter 使用真正主题词和 tag category；仍需下一轮 realtime 实测确认命中率。
- [x] **Event Detail 文本溢出修复**：截图显示聚焦事件详情中显著度徽标和摘要长文本可能超出卡片；已去掉聚焦卡片 scale，给摘要值、统计格、显著度徽标加 `min-w-0`、宽度约束和断行。
- [x] **召回固定 5s 延迟修复**：`recall_search≈5s` 来自 embedding 默认 `batch_interval_ms/request_interval_ms=5000`。当前默认 provider 是 local，因此已把默认节流改为 `50ms/0ms`，dev runner 同步暴露 `RETRIEVAL_ENCODER_BATCH_INTERVAL_MS` / `RETRIEVAL_ENCODER_REQUEST_INTERVAL_MS`；远端 API 用户仍可手动调大以避免限流。
- [ ] **用户自定义母类后的 tag category 重链**：当前 `tag_categories` 是派生字段，不落库；若用户只是改预设母类配置，下一次 API/召回读取会按新规则即时派生，无需迁移。若后续允许人工保存“具体 tag → 母类”或把 category 写入索引，则必须增加 taxonomy version、dirty 标记和重链/重建索引任务。
- [x] **摘要 [事件列表] 与 Event Stream 绑定**：把摘要中的事件列表从“纯文本标题快照”升级为“event_id 驱动的派生区块”。读取摘要时解析 `[event_id8]`，用事件库最新 `topic` 重建 `[事件列表]` 并写回 Markdown；事件 update/reextract 后主动同步引用该事件的 summary 文件，保证 LLM 重跑标题后摘要事件列表能实时反映并固化。
- [x] **实际 AstrBot 路径鲁棒性复核**：本轮新增逻辑已同时接到 `web/plugin_routes.py` 与 `web/server.py`，共享 `core.tasks.summary_links`，避免 dev server 可用但 AstrBot 插件面板不可用。事件更新、reextract、summary get/regenerate 四个入口均覆盖。

#### 次要
- [ ] **encoder 模式 distill 调用数优化**：评估“每窗口一次 batch distill”或“相邻 partition 批量蒸馏”，降低当前约 26 次 LLM distill 调用。
- [x] **LLM 并发控制基线**：实际插件已有 `LLMTaskManager`；dev runner 已接入 `LLM_CONCURRENCY` 并传入 extraction、persona synthesis、group summary，使测试更接近实际环境。
- [ ] **encoder 模式后处理合并**：对同一窗口内相邻、时间连续、tag 重叠或 summary 互补的 partition 合并，减少 semantic clustering 过度碎片化。
- [x] **raw link 差异解释**：runner 的 Event Quality 已输出 `Unlinked raw messages` 和最多 5 条未链接样本；下一轮实测用它判断是 noise filter 预期丢弃还是链接遗漏。
- [ ] **低置信事件诊断**：输出低置信来源是 LLM parse、fallback_single_extraction、noise partition、tag alignment 失败，还是小窗口信息不足。
- [x] **Recall benchmark query 集**：runner 已增加多条检索/召回诊断查询，覆盖无证据、有证据、跨 group、具体 tag 命中、纯语义命中；默认不额外调用回答 LLM，避免测试成本过高。
- [x] **摘要 [事件列表] 与 Event Stream 绑定**：当前 `[事件列表]` 已确定性写入 `[topic] - [event_id8]`。本轮执行方案已落地：后端输出 `linked_events` 结构化 metadata；Summary UI 渲染为可点击事件链，点击后写入 `sessionStorage em_focus_event` 并跳转 `/events`；后端同步最新 topic 并持久化 Markdown。
- [ ] **摘要 callback / 记忆逻辑效率评估**：若 summary 绑定 event ids，可让摘要成为 narrative index，回调/召回时先用日摘要定位候选 event ids，再展开事件详情；需要评估 token 成本、过期一致性、事件删除/归档后的引用修复。

#### 可选
- [ ] **小窗口轻量路径**：对 message_count 很小的窗口设计轻量 prompt 或规则路径，避免 2 条消息也发完整 batch prompt 后 parse 失败。
- [ ] **固定查询集评测**：在 realtime runner 中加入多条 recall benchmark query，覆盖有证据、无证据、跨 group、tag 命中、纯语义命中。
- [ ] **事件质量评分**：输出 summary 三元组数量、tag 名词性、topic 长度、fallback 占比等评分，用于多次测试横向对比。
- [ ] **WebUI perf 对齐**：后续把 runner 中有价值的细分性能指标同步到 WebUI stats 页面。

### Future validation / 需要验证和确认的技术点
- [ ] LLM 模式加载 encoder 后，额外 encoder 成本是否可接受；本轮已新增 dev 配置 `RETRIEVAL_ENCODER_ENABLED` / `RETRIEVAL_ENCODER_MODEL`，仍需用实测确认默认开启是否合适。
- [ ] LLM 模式是否应成为默认推荐 extraction path；encoder 模式是否仅作为低 LLM 成本/可解释语义聚类路径保留。
- [ ] `SemanticPartitioner` 复用消息 embedding 后，DBSCAN 距离矩阵和 time penalty 是否仍是主要瓶颈；是否需要改为相邻距离切分而不是全矩阵聚类。
- [ ] vector no-evidence 阈值如何选：过严会漏召回同义内容，过松会注入无关事件。需要用“原神无证据”和“有证据样本”双向验证。
- [ ] tag sanitizer 的规则边界：中文短语、人名、作品名、游戏名、群内昵称之间如何区分，避免误杀有效标签。
- [ ] raw message link 差异是否属于 noise filter 的合理结果；如果合理，指标应明确显示“有意不链接”的数量。
- [ ] LLM repair/retry 是否显著增加延迟；DeepSeek、LMStudio 本地模型是否需要不同 retry 策略。
- [ ] 新 no-evidence guard 是否过严：需要用“同义词/别名能召回”的正样本验证，避免只支持词面完全覆盖。
- [ ] tag sanitizer 是否误杀群内常用作品名/角色名；如果误杀，需要改为“人名/UID 黑名单 + 白名单词库/NER”组合。
- [ ] `task_summary` / `task_synthesis` 新计时是否与 WebUI stats 页面展示一致；需要实际跑一次 summary/synthesis 后确认非 0 且数量合理。
- [x] 层级 tag 第一版决策：暂不持久化新字段，由 `chat_content_tags` 动态派生 `tag_categories`；API/WebUI 可读，后续如需人工编辑 category 再做迁移。
- [x] Summary `[事件列表]` 绑定 event_id 前缀第一版已验证；本轮采用后端解析 event_id 前缀并返回 `linked_events`。如果出现前缀碰撞，先保留原文本项并标记 unresolved；后续可改为隐藏 JSON sidecar metadata。
- [ ] 用户修改母类集合后的行为验证：修改 category 词表后，已有事件的 `chat_content_tags` 不应改变；`tag_categories` 应按新词表/override 即时变化；如 category 被写入向量索引或 FTS，需要确认重建后召回结果一致。
- [ ] 默认 embedding 节流下调后的限流风险：本地 encoder 应显著降低 recall benchmark 时间；远端 embedding API 需要用户实测是否需把 `embedding_request_interval_ms` 调回较高值。

### Possible implementation / 当前可能的技术实现办法
- [x] `run_realtime_dev.py`：把 extraction strategy 与 retrieval encoder 拆开。`EVENT_MODE="llm"` 控制提取，`RETRIEVAL_ENCODER_ENABLED` 控制是否加载 `SentenceTransformerEncoder` 给 indexing/recall 使用。
- [x] `SemanticPartitioner.partition()`：优先读取 `window.messages[i]` 上已附着的 embedding；只有缺失时调用 `encoder.encode_batch`。同时增加 `partition_encode`、`partition_distance`、`partition_cluster` 计时。
- [x] `EventExtractor.__call__`：围绕每个窗口记录 extraction diagnostic，包括 session_id、message_count、strategy、partition_count、persisted_count、low_conf_count、duration、event_ids。
- [x] `parse_llm_output` / `_extract_batch`：parse 失败时保留短 response snippet；实现一次“严格 JSON 修复 prompt retry”，失败后再 fallback。
- [x] `fallback_single_extraction` / tag alignment 后处理：增加 topic/tag sanitizer，拒绝 URL、过长文本、纯问候、人名/UID 和句子片段；topic 空值回退到“未命名事件”。
- [x] `RecallManager.recall()`：加入实体词覆盖检查，BM25=0 且 vector-only 候选没有同一事件覆盖查询实体词时返回 0。
- [x] `PerfTracker` 与 task 包装：`task_summary`、`task_synthesis` 计时覆盖真实 LLM 调用；runner 继续展示同一 phase 命名。
- [ ] `RecallManager.recall()` debug 增强：后续返回 BM25/vector/RRF/final score 分量，帮助解释为什么某条事件最终被注入。
- [x] tag hierarchy 方案 A：保留 `chat_content_tags` 为具体 tag，新增派生 `tag_categories`，不让 LLM 自由生成；当前通过规则映射到预设类别，后续可替换为 embedding/配置映射。
- [ ] tag hierarchy 方案 B：不改数据模型，维护内存/配置级 `tag_taxonomy`，检索时把 query 和 event tags 动态扩展到类别词；实现成本低但 WebUI 难展示层级。
- [ ] tag relink 方案：新增 `tag_taxonomy_version = hash(categories + rules + manual_overrides)`；每次保存 taxonomy 时比较 version。派生模式只清缓存；持久化模式扫描 distinct tags 重算 `tag_category_links`；如果 category 参与 embedding/FTS，则将受影响 events 加入 reindex 队列。
- [ ] tag manual override 方案：提供 `tag_category_overrides: {具体tag: 母类}`，优先级高于规则/embedding 推断；删除或重命名母类时，把相关 override 标记为 orphan，让 WebUI 提示用户重新选择。
- [ ] summary binding 方案 A：Summary UI 解析 `[事件列表]` 中的 `[event_id8]`，调用现有 `/api/events` 后按前缀匹配并跳转到 `/events?event_id=...`。
- [ ] summary binding 方案 B：后端 `/api/summary` 返回 `{ content, linked_events }`，由 summary task 同步写 sidecar JSON，保证绑定稳定并减少前端解析 markdown。
- [x] summary binding 本轮方案 C：不新增 sidecar 文件，新增共享 helper `core.tasks.summary_links`。`/api/summary` 返回 `{content, linked_events}`，同时把 Markdown 中的 `[事件列表]` 重写为当前 event topic；事件 update/reextract 后调用 helper 扫描并同步引用该 event 的 summary 文件。这样对旧摘要兼容、无迁移、可立即固化标题变化。

### v0.16.3 Handoff notes / 交接说明（给下一个 agent）
- TODO 阅读顺序：先读文件顶部的“TODO 规范”，再读当前最新未完成 section（现在是 `v0.16.3 全程序事件提取效率与召回质量修复`），最后只把 Backlog 当作待讨论池。下方所有 `(completed)` 版本 section 只用于追溯历史，不应重新执行其中的 Phase。
- 状态解释：`🚧` 是当前 session 正在执行或刚落地但仍需最终验证的项目；`[x]` 必须表示代码已改且对应测试已通过；`[ ]` 是未完成/待验证项，不代表已经失败。接手时优先处理当前 section 里的 `🚧` 和“重要”下的 `[ ]`，不要从旧版本 completed 章节开始。
- 验证阅读逻辑：`Verification` 里已打勾的命令是本轮已经跑过的基线；新增代码后需要追加新的验证行，不要覆盖旧结果。若只修改文档可说明无需 build；若修改 `web/frontend`，必须 typecheck，并按 AGENTS 规则执行 `npm run build` 与 `tools/sync_frontend.py -f`。
- 运行环境逻辑：`run_config.py` 是本地私有配置且已 gitignore；不要为了提交改它。需要新增测试参数时改 `run_config.py.example`，实际用户会在本地 `run_config.py` 手动同步。
- 实际环境逻辑：`run_realtime_dev.py` 只是复现工具；任何核心行为必须确认实际 AstrBot 路径也接入，通常需要同时检查 `core/plugin_initializer.py`、`web/plugin_routes.py`、`web/server.py`、共享 `core/` helper。
- 当前版本正在做的是“全程序事件提取效率与召回质量修复”，不是单独修 `run_realtime_dev.py`。dev runner 是验收工具，核心改动必须落在 `core/`、`web/plugin_routes.py`、`web/server.py` 等实际插件路径。
- 已确认 LLM 模式事件粒度更接近期望，当前默认推荐路径倾向 `EVENT_MODE="llm"` + retrieval encoder enabled。encoder 模式保留，但仍有过度碎片化和 distill 调用数过多问题。
- 已确认 recall 固定 5s 延迟来自 embedding 默认节流，已改成 local 默认 `50ms/0ms`。用户 00:39 实测 `recall_search≈0.074s`，说明修复有效。
- tag hierarchy 当前是派生字段：`chat_content_tags` 是具体 tag，`tag_categories` 是 `{具体tag: 母类}`，不落库。用户未来可能需要手动编辑母类，届时要做 taxonomy version + relink/reindex。
- 本轮正在执行 summary-event binding：旧摘要 Markdown 里只有 `[topic] - [event_id8]`。要求是事件标题被编辑或 reextract 后，摘要 `[事件列表]` 能自动用最新 topic 反映并写回文件，同时 Summary UI 可跳转到 Event Stream 对应事件。
- 实现约束：必须同时改 standalone WebUI 和 AstrBot plugin routes；不要只改前端或只改 dev server。后端 helper 应在 `core/tasks/summary_links.py` 之类共享位置，避免两套路由逻辑漂移。
- 预计验证重点：summary helper 单测、plugin routes summary API 测试、standalone WebUI summary API 测试、frontend typecheck、frontend layout test、backend full tests、build + sync static assets。

### Implemented in this session / 本轮已落地目标
- [x] 核心 `SemanticPartitioner` 复用已附着 embedding，降低 encoder 模式重复编码开销。
- [x] 核心 `EventExtractor` 增加窗口级日志、JSON repair retry、topic/tag sanitizer。
- [x] 核心 `RecallManager` 增加 vector-only no-evidence guard，减少无证据相似事件注入。
- [x] 核心 `run_group_summary` / `run_persona_synthesis` 修正性能计时覆盖范围。
- [x] 核心 tag normalisation 放宽并保留具体主题词：tag 长度上限放宽到 12，种子大类不再覆盖更具体 tag，prompt 明确要求保留作品名/技术名词/机制名。
- [x] 核心 LLM 单事件完整窗口覆盖：当 LLM 只返回一个 DB Event 时强制链接完整连续窗口，避免有意义原文未进入 event-message links。
- [x] WebUI Event Detail Card 修复聚焦状态文本/徽标溢出：移除 scale，补充内部文本断行和宽度约束。
- [x] tag hierarchy 第一版：新增 `core.tags.taxonomy`，为每个具体 `chat_content_tags` 派生一个预设 category，并在 core/web API 输出 `tag_categories`。
- [x] recall evidence filter 第一轮：问题词过滤和 required evidence term 抽取已调整，避免 `谁请求了大五人格分析`、`卿泽和Gariton发生了什么互动` 这类查询被问题词误杀。
- [x] embedding 默认节流调整：本地召回/indexing 默认不再等待 5s；`_conf_schema.json`、`core.config.EmbeddingConfig`、`run_realtime_dev.py` 与 `run_config.py.example` 已同步。
- [x] 实际插件路径确认：`core/plugin_initializer.py` 中 embedding/indexing 已由 `embedding_enabled` 独立于 extraction strategy 控制，且使用 `LLMTaskManager`；本轮无需改核心初始化。
- [x] dev runner 同步实际路径：LLM 模式默认也可加载 retrieval encoder，并接入 `LLMTaskManager`、质量诊断、未链接 raw message 样本、recall benchmark query 集。
- [x] Summary/Event 互绑定：新增 `core.tasks.summary_links`，让 summary 读取、事件编辑、事件 reextract 都能刷新 `[事件列表]` 中 stale title；Summary UI 可点击跳转 Event Stream。
- [x] 版本发布记录：`metadata.yaml`、README 徽章、根目录 `CHANGELOG.md` 与 `docs/CHANGELOG.md` 已升至 v0.16.3。
- [x] 新增/更新单测覆盖 partition 复用、parse repair、tag/topic sanitizer、vector no-evidence guard、summary/synthesis timer 回归。

### Verification
- [x] `python -m py_compile core\extractor\extractor.py core\extractor\partitioner.py core\managers\recall_manager.py core\tasks\summary.py core\tasks\synthesis.py run_realtime_dev.py` → passed。
- [x] `pytest tests\backend\test_partitioner.py -q` → 3 passed。
- [x] `pytest tests\backend\test_extractor.py -q` → 35 passed。
- [x] `pytest tests\backend\test_recall_manager_extra.py -q` → 8 passed。
- [x] `pytest tests\backend\test_tasks.py tests\backend\test_summary_mood.py -q` → 36 passed。
- [x] `pytest tests\backend\test_recall_manager_extra.py tests\backend\test_recall_pipeline_opts.py -q` → 18 passed，2 个既有 `AsyncMock` warning，待后续单独清理。
- [x] `pytest tests\backend -q` → 644 passed，3 warnings（1 个 faiss/numpy deprecation；2 个既有 `AsyncMock` warning）。
- [x] `python -m py_compile core\extractor\extractor.py core\extractor\prompts.py run_realtime_dev.py` → passed。
- [x] `pytest tests\backend\test_extractor.py tests\backend\test_tag_normalization.py -q` → 45 passed。
- [x] `pytest tests\backend -q` → 648 passed，3 warnings（1 个 faiss/numpy deprecation；2 个既有 `AsyncMock` warning）。
- [x] `pytest tests\frontend\test_loom_layout.py -q` → 51 passed。
- [x] `cd web\frontend && npm.cmd run typecheck` → passed。
- [x] `cd web\frontend && npm.cmd run build` → passed（sandbox 下因 Google Fonts 网络失败一次；授权网络后通过）。
- [x] `python tools\sync_frontend.py -f` → synced（sandbox 下因内部 build 取 Google Fonts 失败一次；授权网络后通过）。
- [x] `python -m py_compile core\tags\taxonomy.py core\domain\models.py core\managers\recall_manager.py web\server.py web\plugin_routes.py core\api.py run_realtime_dev.py` → passed。
- [x] `pytest tests\backend\test_tag_taxonomy.py tests\backend\test_recall_manager_extra.py tests\frontend\test_webui.py -q` → 66 passed，1 warning（faiss/numpy deprecation）。
- [x] `cd web\frontend && npm.cmd run typecheck` → passed。
- [x] `pytest tests\backend -q` → 653 passed，3 warnings（1 个 faiss/numpy deprecation；2 个既有 `AsyncMock` warning）。
- [x] `python -m py_compile core\config.py run_realtime_dev.py` → passed。
- [x] `pytest tests\backend\test_new_configs.py tests\backend\test_embedding_manager.py -q` → passed。
- [x] `python -m json.tool _conf_schema.json` → passed。
- [x] `pytest tests\backend -q` → 653 passed，3 warnings（1 个 faiss/numpy deprecation；2 个既有 `AsyncMock` warning）。
- [x] `python -m py_compile core\tasks\summary_links.py web\plugin_routes.py web\server.py` → passed。
- [x] `pytest tests\backend\test_summary_links.py tests\frontend\test_api_v4.py tests\frontend\test_webui.py -q` → 63 passed，1 warning（faiss/numpy deprecation）。
- [x] `pytest tests\frontend\test_loom_layout.py -q` → 51 passed。
- [x] `pytest tests\backend -q` → 655 passed，3 warnings（1 个 faiss/numpy deprecation；2 个既有 `AsyncMock` warning）。
- [x] `pytest tests\frontend -q` → 229 passed，1 warning（faiss/numpy deprecation）。
- [x] `cd web\frontend && npm.cmd run typecheck` → passed。
- [x] `cd web\frontend && npm.cmd run build` → passed（首次 sandbox 失败：当前 shell 找不到 `conda`，且 Google Fonts 网络被拦；授权网络后 `npm.cmd run build` 通过）。
- [x] `python tools\sync_frontend.py -f` → synced 到 `pages/moirai/`（授权网络后通过）。
- [x] 新增/更新 encoder partition 复用、tag sanitizer、vector no-evidence guard 相关测试。
- [ ] `python run_realtime_dev.py` with `EVENT_MODE = "encoder"` → 用户实测记录优化后 Phase 1/2/5/7 全量输出；重点看 `partition avg`、`partition_encode`、未链接 raw 样本、注入事件。
- [ ] `python run_realtime_dev.py` with `EVENT_MODE = "llm"` + `RETRIEVAL_ENCODER_ENABLED = True` → 用户实测确认 `Vector candidates` 不再固定为 0、无原神证据查询注入 0、`task_summary/task_synthesis` 非 0。
- [ ] 如涉及 WebUI 静态资源，本轮未修改前端，不需要 `npm run build` / `sync_frontend.py -f`；若后续改 WebUI stats 展示再执行。

---

## v0.16.0 多账号绑定 / 跨平台人格合并 (completed)

### User constraints / 约束
- 同一真人可能在多平台有多个账号（QQ + Discord 等），需手动把多个账号 ID 绑定到同一用户名下。
- 绑定后人格分析数据合并看待；绑定可再次分离；每次绑定/解绑都立即重跑一次人格合成。
- 采用**软分组覆盖层**（零数据迁移、完全可逆）：每个平台账号永久保留自身 `Persona`/`uid`
  与全部原始数据，绑定只是关联进命名 group，合成时跨成员聚合后镜像写回。
- 操作界面：Web UI 页面 + 聊天指令两者都要。
- 合成始终合并；召回默认也合并，提供开关 `account_merge_synthesis_only`，开启后召回不合并。
- 关系图谱/Library 中同 group 折叠为单一节点。
- 所有改动限制在 `astrbot-plugin-enhanced-memory/` 内；先更新 TODO 再动代码。

### Technical implementation path

#### Phase 0 — 登记与基线
- [x] 本计划写入 TODO；基线 `pytest tests/backend -q` → 614 passed。

#### Phase 1 — 数据层
- [x] 新建 `migrations/015_persona_groups.sql`：`persona_groups` 表 + `personas.group_id` 列 + 索引。
- [x] `core/domain/models.py`：`Persona.group_id` 字段；新增 `PersonaGroup` dataclass。
- [x] `core/repository/base.py` + `sqlite.py` + `memory.py`：persona `group_id` 读写；
      新增 `PersonaGroupRepository`（抽象 + SQLite + 内存实现）。迁移 + CRUD smoke 通过。
- [x] `core/plugin_initializer.py`：实例化 `persona_group_repo` 并接线。

#### Phase 2 — 覆盖层
- [x] 新建 `core/social/persona_group.py`：`expand_uids` / `aggregate_events`。

#### Phase 3 — 人格合成 group 感知
- [x] `core/tasks/synthesis.py`：`_synthesize_one_persona` 加 `force`；新增 `synthesize_persona_group`
      与 `_synthesize_persona_or_group`/`_mirror_group_attrs`；`run_persona_synthesis` /
      `run_persona_synthesis_for_uid` / `PersonaSynthesisTrigger` / `run_consolidated_maintenance`
      折叠 group；`plugin_initializer` 全部接线 `persona_group_repo`。88 synth/persona 测试通过。

#### Phase 4 — 绑定/解绑服务
- [x] 新建 `core/managers/account_link_manager.py`：`bind_accounts` / `unbind` / `dissolve` /
      `rename` / `list_groups` / `list_human_personas` + 后台强制重合成 + 配对码（内存 + TTL）。
      `plugin_initializer` 接线 `account_link_manager`。smoke 通过。

#### Phase 5 — Web API + 图谱折叠
- [x] `web/plugin_routes.py` + `web/server.py`：persona-group API（list personas/groups、create、
      rename、dissolve、add/remove member）+ `graph_data` 同 group 节点折叠/边重映射；
      `run_webui_dev.py` 接线 dev 服务器。113 graph/web/persona 测试通过。

#### Phase 6 — 配置开关 + 召回展开
- [x] `_conf_schema.json` + `core/config.py`：`relation.account_merge_synthesis_only`（默认 false）
      接入 `InjectionConfig`。
- [x] `core/managers/recall_manager.py`：`_build_relation_segment` 在开关关闭时经
      `expand_uids` 跨 group 成员汇总 impressions；`plugin_initializer` 接线 `persona_group_repo`。
      75 recall/config 测试通过。

#### Phase 7 — 聊天指令
- [x] `main.py` + `core/managers/command_manager.py`：`/mrm bind`（无参取配对码 / 带码兑现）、
      `/mrm unbind`；委派 `AccountLinkManager`。管理员直绑由 WebUI 覆盖，未做 4 参聊天指令。
      全量 614 后端测试通过、无回归。

#### Phase 8 — 前端
- [x] `lib/api.ts` 新增 `personaGroups` API + 类型；`components/config/account-binding-manager.tsx`
      绑定管理组件（三语内联标签）；`app/bindings/page.tsx` 页面；侧边栏新增「账号绑定」入口。
      typecheck 通过、lint 0 error（3 个既有 warning 与本改动无关）。

#### Phase 9 — 构建与验证
- [x] 新增 `tests/backend/test_persona_groups.py`（10 测试）；`npm run build` + `sync_frontend.py -f`；
      双 changelog 与 `metadata.yaml` 升至 v0.16.0。

### Verification
- `pytest tests/backend -q` → 624 passed（含 10 个新测试）
- `pytest tests/frontend -q` → 218 passed
- `cd web/frontend && npm.cmd run typecheck` → passed
- `cd web/frontend && npm.cmd run lint` → 0 error（3 个既有 warning，与本改动无关）
- `cd web/frontend && npm.cmd run build` → 13 静态页（含新 `/bindings`）
- `python tools/sync_frontend.py -f` → synced 到 `pages/moirai/`
- 实机待用户验证：两个平台账号各发消息 → WebUI「账号绑定」页绑定 → 图谱合并为单节点 →
  `/mrm bind` 配对码流程 → 解绑后图谱拆回；`account_merge_synthesis_only` 开关行为。

---

## v0.15.0 AstrBot config grouping hotfix (completed)

### User constraints / 约束
- 修复 AstrBot 原生 config 页面底部出现未分类配置项的问题。
- 不修改 AstrBot core framework；只修插件自身的配置保存/读取路径。
- 版本统一归入 v0.15.0，不新增其他 patch version。

### Root cause
- `_conf_schema.json` 已经把 `embedding_provider`、`llm_concurrency`、`retrieval_top_k` 等字段放在分组下。
- WebUI quick setup/config save 发送 flat payload，保存 handler 直接把这些字段写入 root config，并同步到 AstrBot live config root。
- AstrBot 原生配置页按 schema group 渲染 nested 字段，root 中多出的 flat 字段因此显示为未分类设置。

### Technical implementation path
- [x] Phase 1 - Add schema-aware config helpers to flatten schema, read nested values, and normalize flat updates into schema groups.
- [x] Phase 2 - Update plugin route config save/read path to write known fields into nested groups and remove stale root duplicates.
- [x] Phase 3 - Update standalone WebUI server config save/read path with the same behavior.
- [x] Phase 4 - Add regression tests covering flat payload -> nested storage and AstrBot live config sync.

### Verification
- [x] `python -m py_compile web/plugin_routes.py web/server.py web/config_schema.py` -> passed
- [x] `pytest tests\frontend\test_config_sync.py -q` -> passed, 3 passed, 1 warning
- [x] `pytest tests\frontend\test_config_sync.py tests\frontend\test_api_v5.py -q` -> passed, 6 passed, 1 warning
- [x] `pytest tests\frontend -q` -> passed, 218 passed, 1 warning

## v0.15.0 Release metadata & changelog finalization (completed)

### User constraints / 约束
- 补齐 Event Stream 重构后的 changelog，并确认不单独 bump 版本。
- 根目录 `CHANGELOG.md` 与 `docs/CHANGELOG.md` 都要记录本次用户可见变化。

### Technical implementation path
- [x] Phase 1 — 确认 `metadata.yaml` 保持 `v0.15.0`，并补充双 changelog。

### Verification
- `git status --short -- metadata.yaml CHANGELOG.md docs\CHANGELOG.md` → changed as expected

---

## v0.15.0 Event Stream centered mobius orbit hotfix (completed)

### User constraints / 约束
- 修正 knot active 指示：不是在锚点旁边画一个莫比乌斯符号，而是让小圆沿以锚点为中心的莫比乌斯/∞ 轨迹运动。
- 锚点本体作为轨迹中心保持稳定。

### Technical implementation path
- [x] Phase 1 — 替换侧边 animated path 为 centered animateMotion orbit。

### Verification
- `cd web/frontend && npm.cmd run typecheck` → passed
- `pytest tests\frontend\test_loom_layout.py -q` → passed, 45 passed

---

## v0.15.0 Event Stream knot mobius indicator (completed)

### User constraints / 约束
- 将 thread view 中 knot 的圆形脉冲效果改为锚点旁边的莫比乌斯/∞ 运动指示。
- 锚点本体保持稳定，不再用扩大圆环表达焦点或选中。

### Technical implementation path
- [x] Phase 1 — 替换 active/focus knot 的视觉指示，从圆形 glow 改为侧边 animated mobius path。

### Verification
- `cd web/frontend && npm.cmd run typecheck` → passed
- `pytest tests\frontend\test_loom_layout.py -q` → passed, 45 passed

---

## v0.15.0 Event Stream focus outline hotfix (completed)

### User constraints / 约束
- 修复 thread view 中移动/点击圆形 knot 时出现的矩形默认 focus outline。
- 保留 knot 的键盘可访问性，不移除 `role="button"` / `tabIndex`。

### Technical implementation path
- [x] Phase 1 — 去除 SVG 默认矩形 outline，改用节点自身的圆形 focus 高亮。

### Verification
- `cd web/frontend && npm.cmd run typecheck` → passed
- `pytest tests\frontend\test_loom_layout.py -q` → passed, 45 passed

---

## v0.15.0 Event Stream reconfiguration (completed)

### User constraints / 约束
- 所有代码改动仅限 `astrbot-plugin-enhanced-memory/` 工作区内。
- 先更新 TODO，再改源码；每个阶段完成并通过相关验证后再勾选。
- 不改后端 API、`ApiEvent` 数据形状、全局 store、事件 dialogs，也不修改 core framework 代码。
- 以 `IMPLEMENTATION.md` 为实现规格，`Event Stream - Demo.html` 为视觉参考；保留既有脏工作区变更，不回滚用户或已有产物改动。

### Technical implementation path
- [x] Phase 0 — 任务登记与基线验证：登记本计划；已确认 `pytest tests\frontend\test_loom_layout.py tests\frontend\test_ui_polish.py` 与 `npm.cmd run typecheck` 基线通过。
- [x] Phase 1 — 数据层：新增 `events-aggregator.ts` 与 `session-clustering.ts`，稳定派生 spindle/group 统计与 thread session layout 输入。
- [x] Phase 2 — Spindle 一级视图：新增 `spindle-grid.tsx`、`spindle-card.tsx`、`mini-thread.tsx`，`/events` 默认渲染 spindle grid。
- [x] Phase 3 — Thread 二级视图：新增 `event-thread.tsx`，按 `expandedGroupId` 只渲染当前 group，并保留事件选择、highlight、CRUD 入口。
- [x] Phase 4 — Detail panel 与页面接入：重做 `DetailPanel` 内部视觉，保留 props；完善 `em_focus_event` / `em_highlight_events` 自动展开链路。
- [x] Phase 5 — 动画、i18n、测试：追加 silk/keyframe CSS 和三语 i18n 新键；更新前端结构测试覆盖新架构。
- [x] Phase 6 — 构建与同步：运行前端类型检查、结构测试、build，并同步静态产物到运行环境。

### Verification
- `pytest tests\frontend\test_loom_layout.py tests\frontend\test_ui_polish.py` → baseline passed, 75 passed
- `cd web/frontend && npm.cmd run typecheck` → baseline passed
- `pytest tests\frontend -q` → passed, 218 passed, 1 warning
- `cd web/frontend && npm.cmd run typecheck` → passed
- `cd web/frontend && npm.cmd run lint` → passed with 2 existing warnings outside this change (`graph/page.tsx`, `sidebar-user-menu.tsx`)
- `cd web/frontend && npm.cmd run build` → passed（首次普通沙箱构建因 Google Fonts 网络获取失败；批准网络访问后通过）
- `python tools/sync_frontend.py -f` → passed（同步到 `pages/moirai/`；普通沙箱同样受 Google Fonts 网络限制，批准网络访问后通过）
- `python run_webui_dev.py` / `cd web/frontend && npm.cmd run dev` → existing local services verified: `http://localhost:2654/api/stats` 200, `http://localhost:3000/events/` 200

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
- 三档层级：基础 / 进阶 / 专家。基础档极简 —— 只保留最关键开关，数值微调全部下沉，基础用户可通过快速设置向导预设包完成配置，不手动调参。
- Soul 标记为实验性、默认关闭、不进基础档、不进任何默认开启的预设。
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
- [x] 二元 `showAdvanced` 替换为三段 `ToggleGroup`（基础/进阶/专家），过滤改「显示 level ≤ 当前档」；localStorage `em_config_level`（兼容旧 `em_show_advanced_config`）
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
