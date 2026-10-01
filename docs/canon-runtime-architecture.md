# canon 运行时结构

本文件记录 canon 运行时代码**现在**的结构、已知的结构问题，以及把终端原型迁到正式 Bot 路径（B6–B9）时的指引。指引是给后续开发者和编码 agent 的启发与约束，不是已批准的计划：动代码之前，先在 `docs/TODO.md` 写出具体计划并得到用户批准（这个文件被 `.gitignore` 忽略，只在本机）。终端的行为说明见 [canon 终端试聊](canon-terminal.md)，整体状态见 [canon：原作剧情记忆](canon.md)。

## 现在的结构

2026-09-27 起（v1.2.18.sub），终端原型的检索和装填逻辑已迁进 `core/canon`，终端、工具回调和检索评测走同一套代码。

| 环节 | 位置 | 说明 |
|---|---|---|
| 抽取与写入 | `core/canon/extract.py`、`fact_extract.py`、`importer.py`、`store.py` | `CanonStore` 基于 aiosqlite，异步、可写；只有导入和基准会用 |
| 查询解析 | `core/canon/query.py`：`TurnPlan`、`plan_turn`、`route`、`needs_motive_rerank`、`explicit_quote` 与关键词表 | 纯函数，除别名查找外没有 IO；`context.py` 的 `resolve_name` 做名字纠正 |
| 只读访问与索引 | `core/canon/reader.py`：`CanonReader`、`fact_search` | 同步 sqlite、`mode=ro`；构造时在内存里建三份两字 BM25（事件文本、原文台词、场景资料）和别名表，查询方法只读这些数据和 SQLite |
| 召回与融合 | `core/canon/retrieval.py`（`fuse`、`CanonRetrieval`）、`lexical.py`、`vector_index.py` | hybrid 需要派生向量索引；embedding 由 `devtools/retrieval.py` 的 `ProviderBridge` 提供 |
| 结构扩展与综述 | `context.py` 的 `expand_events`、`overview.py`；`CanonReader.overview_search`、`expand_context` | |
| 证据装填与预算 | `core/canon/packing.py`：`Hit`、`fill*`、`rank_reason_hits`、`result_line`、`estimate_tokens`；`recall.py` 的 `CanonRecall._incident`（讲经过的事件窗口）；`gateway.py` 的 `EvidencePack` | 预算常量仍直接写在 `fill_*` 里。`EvidencePack.render` 按 `CanonReader.sequence` 编号、换成第一人称，并列出 `CanonReader.causal_links` 的因果许可 |
| 调度 | `core/canon/assembly.py`：`EvidenceAssembler`、`EvidenceSettings` | 一轮一个实例，持有证据包和本轮预算；首轮预取、`canon_recall` / `canon_overview` 工具和近况事实块都经过它。自适应装填放宽的预算对之后的工具调用可见 |
| 提示词、工具与收尾 | `core/canon/turn.py`：`CanonTurn`（三个工具回调、档案直查、`system` / `block` / `messages`、`tool_text`、`settle`、`check`），以及 `knowledge`、`build_block`、`build_system`、`OUTPUT_RULES`、`MEMORY_NOTE`、`STYLE`（[讲法]）、`archive_names`、`supplement_recall`；`query.py` 的 `task_of` | 终端和 Bot 共用。终端每次请求前重建系统提示词，工具结果只回一行说明；Bot 的系统提示词在工具轮之间不变，`tool_text` 把[你的记忆]块随结果返回：第一次带整块，之后只带新想起的事（标“新1”“新2”，写明排在已给出的哪件事前后，见 `EvidencePack.render_new`），因为宿主对话里前面的工具结果还在；执行次数上限为 `MAX_TOOL_ROUNDS`。`run_turn` 可带入宿主侧的 `memory_block`（普通记忆），只给模型看，不参与路由和检查 |
| 生成 | `run_canon_chat.py` 的 `generate`、`ModelClient`（httpx，同步）、`Session`、`conversation_history` | |
| 检查 | `core/canon/gateway.py` 的 `align`、`inspect`、`check_reply`、`beat_line` | 检查本身不调模型：逐句对到证据，按结构标出问题；有问题才调一次模型定点修补，修补后仍有问题的句子换成对上的记忆原句。`CheckReport.stages` 记录对齐、修补和替换，供 `--trace` 和评测写出 |
| 时间事实 | `core/canon/temporal.py` 的 `resolve`；`CanonReader.fact_context` | |
| 世界日历 | `core/canon/calendar.py`（离线定坐标，`calendar-apply` 写 `event_times`）；`CanonReader.times`、`now`、`time_label`；`recall.py` 的 `timeline` / `recent` 路径 | 只存坐标，外部年表正文不入库；运行时只读 |
| 时间说法 | `core/canon/anchors.py`（锚点的范围选择、归属与定位措辞）；锚点表在 `character.py` 的 `ANCHORS`；`CanonReader.time_phrase`、`now_phrase`；`recall.py` 的 `present_phrase` | 给模型看的时间用大事件说，日历只在底下排序；证据包的 `when` 接 `time_phrase` |
| 评测 | `devtools/canon/retrieval.py`、`dialogue_eval.py`、`budget_sweep.py`、`fact_focus.py`；终端 `--trace` | 检索评测经 `EvidenceAssembler` 组包；只从终端导入默认库路径 `DEFAULT_DB`。`dialogue_eval.py` 仍整体运行终端的代码快照 |
| 插件侧 | `core/adapters/core_canon.py` 的 `CanonGeneration`；`core/adapters/core_events.py` 的 `generation_v1` / `on_generation_v1`；`core/plugin_initializer.py` 的 `_open_canon`；配置在 `get_canon_config` / `CanonConfig` | Core Generation Protocol v1 的参与方：`before_generation` 注入 canon 块，`offer` 提供工具，`tool` 转给 `CanonTurn`，`review` 在 `after_generation` 之前审稿。读库和审稿里的模型调用都在一个工作线程上排队执行。插件里暂时只有词法检索 |

测试（本机的 `tests/`）直接从 `core/canon` 导入，只有 `conversation_history` 仍从终端导入。

## 已知的结构问题

1. **读取对象不能跨线程共用。** `CanonReader` 持有一个默认 `check_same_thread` 的 sqlite 连接，不能交给线程池里的另一个线程使用；`search`、`overview_search`、`expand_context` 还把 trace 写在实例属性（`last_channels`、`last_overview_trace`、`last_expansion_trace`）上，`CanonRetrieval.last_trace` 也一样，多个对话共用一个实例时会互相覆盖。终端和评测是单线程、一轮接一轮，没有问题。Bot 路径（v1.2.33.sub）暂时用一个工作线程：`CanonGeneration` 的读库、工具和审稿（含修补的模型调用）都在这个线程上排队执行，多个对话会互相等待；Core 对单次调用超时后，线程上的工作仍会做完。并发多个对话时，再改为每线程一个连接、内存索引共享、trace 改为每轮的对象。
2. **索引有两套。** 向量：库内 `event_vec`（`import --embed` 写入）和构建目录旁的派生索引（终端实际用的）。全文：库内 trigram 表 `events_fts` / `beats_fts` 和启动时建的内存 BM25（终端实际用的）。
3. **融合有两套。** canon 用加权 RRF（k=10，四路权重不同），Moirai 原有记忆用 `core/retrieval/rrf.py` 的等权 RRF（k=60）。
4. **预算互不知晓。** 终端的证据预算、插件配置 `canon_token_budget`（v1.2.33.sub 起默认 2000，与终端一致）和原有 memory 块的预算各自独立（数字见 [canon 终端试聊](canon-terminal.md) 的“证据预算”）。
5. **证据包每轮重建。** 工具往返不写入历史，上一轮用过的证据在下一轮就没有了；追问只能靠 `focus` / `topics` 重新检索，检查也看不到上一轮的依据。
6. **同步和异步混用。** 读取与生成是同步的（sqlite3、httpx），插件和 `CanonStore` 是异步的。
7. **已写入但没用上的数据。** `cognitions`（逐场景的人物态度）和 V11 的 `view_access` 都已入库，运行时没有读取。

## 目标分层

参照 MemOS 的“接口层 / 操作层 / 基础设施层”划分，按职责分四层，终端和 Bot 共用同一套。前三层已按下表落位：

- **查询解析**：`query.py`。以后可整理成带类型的查询结构（意图、主体、焦点、`as_of`、要查的记忆类型——事件、综述、档案、事实——以及知情要求）。
- **检索**：`reader.py` 加 `retrieval.py`、`overview.py`、`context.py`。输入查询，输出带 trace 的候选；不调用模型。
- **调度**：`assembly.py` 和 `packing.py`。接入 Bot 后，这一层也负责和原有 memory 块分配同一份预算。
- **检查**：`gateway.py`。

Bot 路径上的 canon 工具回调应复用终端的 `CanonRecall` / `EvidenceAssembler`，不要再抄一份组包流程。首轮预取（`prefetch()`）只留在离线检索评测里，不作为 Bot 的默认路径（见待决问题 4）。

## 迁移记录与对比方法

2026-09-27 分四步迁移（纯函数 → 读取 → 调度 → 清理），每一步只移动代码。迁移前发现：`moirai canon test --questions` 实际运行 `devtools/canon/retrieval.py`，它自带一份组包流程，缺少终端对“问原因”题的上下文扩展，所以此前的题库数字测的不是终端的实际注入。合并后，316 道对比题中评测与终端的注入事件、证据长度和路线逐题一致（此前 31 题不一致）。评测还修掉一处诊断问题：印象类综述的 trace 会带上一题的结构扩展记录。

之后再做只移动代码的重构，用本机的对比工具验证（`.dev_data/canon/parity/`，被 `.gitignore` 忽略，因为题目含剧情原文）：

1. `build_inputs.py` 从各题库、对话题和少量路径覆盖题生成固定输入。
2. `PYTHONHASHSEED=0 .venv/bin/python .dev_data/canon/parity/run.py <标签>` 在 V10 全库上离线记录四份输出：检索评测报告；终端逐题的 dry-run 状态和完整证据包文本；终端逐题接一个脚本化假模型跑完整一轮（工具回调、补查、核验调用的全部输入）；多轮对话的跨轮状态；另在有档案的 v7 库上跑档案工具。`--hybrid replay` 用首次记录的查询向量离线重放 hybrid 模式。
3. `python .dev_data/canon/parity/compare.py <A> <B>` 逐题比对，有差异时退出码为 1。

它覆盖不到已审阅时间事实的渲染（现有库里没有已审阅事实），这部分由 `tests/test_canon_reader.py` 的合成库测试覆盖。

## 必须保持的约定

- 运行时只读，不写 `canon.sqlite`；聊天内容不写回 canon。
- `unstated` 事件只做导航，不注入；`role_candidate` 获知标签和 `reported` 事实候选都不当作角色知识或世界事实。
- 汇报即知情（2026-09-28 用户决定）：V11 视角为 `unstated`、但带 `direct_report`（报给阿米娅）或 `command_report`（报给博士或凯尔希）获知标签的事件，读取时渠道记为 `reported`（“经汇报得知”），视为阿米娅已知。作为罗德岛领导人，她知道汇报内容，但不必说明由谁转达。她只知道汇报本身：证据包里这类事件的摘要换成获知标签的 `content`，证据行只取标签引用的行。`record_available` 与 `role_candidate` 仍不算知情；V10 库没有 `view_access`，行为不变。规则写在 `CanonReader` 一处（`REPORT_ACCESS`），检索、组包、综述和评测的已知事件集合共用它。
- 角色相关的写法只放在 `core/canon/character.py` 的 `CharacterProfile`，按 `CanonPersona.character` 取用。它记录自称名、玩家称谓与占位符（博士、{DOCTOR}、@doctor）、所属组织、汇报接收人、世界名与游戏术语，并带 `report_knowledge` 开关，和 `user_is_doctor` 开关并列。运行时模块（reader、retrieval、gateway、packing、query、overview、context、assembly、lexical、vector_index）不直接写角色名。抽取 prompt 是按版本冻结的故事包资产，不在此列。
- 防护测试 `tests/test_canon_guards.py`（本地）钉住以下几项，改动时要同步更新文档、版本号和钉值：
  - 各版本抽取与事实 prompt 的文本（文本变了必须换版本号，因为缓存按版本命中）；
  - 定点修补提示词和各类问题说明在阿米娅配置下的渲染结果；
  - 汇报即知情规则及其开关；
  - 综述路线的问法类别；
  - 默认人设的禁括号规则与 3,000 token 上限；
  - 路由门槛；
  - 运行时代码不写角色名，也不照抄评测题原句。
- 证据编号可追溯：事件 `E`、档案 `A`、已审阅事实 `F` 都能回到 `line_key`；对话引用 `C` 只说明谁在聊天里说过什么，不证明世界事实。
- 检索和检查不调用模型；只有生成和定点修补调用。
- 每个预算数字只有一个出处。
- 已保留的抽取 prompt 版本一字不改。
- 剧情原文、数据库、评测报告只留在本机，不进 git；测试只用自编文本。
- Moirai 依赖 Core，不依赖 Oedipus；和 Oedipus 的交互只走 Core 的版本化协议。

## 待决问题

这些需要实验数据或用户决定，不能在迁移时顺手合并：

1. **索引选哪套**：向量用 `event_vec` 还是派生索引；全文用 trigram 表还是内存 BM25（要比较召回、启动时间和常驻内存）。
2. **融合怎样统一**：用哪个 k 和权重，用 200 题评测决定。
3. **Bot 的预算**：插件默认值和终端基础值该取哪个；canon 块和原有 memory 块怎样分配名额。2026-09-30 全数据流测试暂时分开计：普通记忆 800，canon 每轮 2,000。是否共用一份，按测试数据再定；普通记忆的窗口大小另行测试。
4. **Bot 里怎样召回和检查**（2026-09-30 已定方向）：Bot 沿用终端逻辑，不采用“生成前注入证据块”。
   - 模型通过工具调用选档位：不召回、轻量召回、深度探索、查档案。召回过的轮次做逐句对齐检查和定点修补。
   - 2026-10-01 已实现：Core v0.8.0 的 Generation Protocol v1 提供扩展声明工具（Core 交给宿主，执行转回扩展）和审稿替换回复两项能力，Event Protocol v1 不变；Moirai v1.2.33.sub 接入。Moirai 不改用 AstrBot 自己的工具注册，以免绑死宿主。
   - 工作区的 `scripts/fullflow_test.py` 默认走这条真实 Core 路径，脚本当宿主跑工具循环；`--path terminal` 保留终端路径作对照。
5. **聊天记忆污染**：Bot 说出的剧情内容会被 Moirai 的事件抽取器写进聊天记忆，之后作为“我们聊过的事”召回时会绕过 gateway。需要在抽取或召回时标注这类内容的来源。2026-09-30 用户决定先观察：全数据流测试记录哪些聊天记忆事件是由阿米娅的剧情回答构成的，以及它们之后是否又被注入。
6. **跨轮工作记忆**：是否保留最近几轮的证据 ID，下一轮以压缩形式带回，供追问和检查使用。
7. **未用数据**：`cognitions`、`view_access` 是否进入检索或注入；进入前需要审阅。

## 参考

- MemOS（[arXiv 2507.03724](https://arxiv.org/abs/2507.03724)）：接口 / 操作 / 基础设施三层，以及每条记忆带来源签名、使用频率、版本链的元数据。canon 语料是冻结的只读记忆，论文里的生命周期衰减、KV 缓存注入和参数记忆都不适用；适用的是分层和来源元数据。
- HaluMem（[arXiv 2511.03506](https://arxiv.org/abs/2511.03506)）：把记忆幻觉拆成抽取、更新、问答三个阶段分别计量，发现错误主要在抽取和更新阶段产生并向后传递。canon 已有抽取探针、检索题库和对话评测，缺的是时间事实的“更新”阶段（状态变更对）评测。

## 流程

- 计划写进本机的 `docs/TODO.md`，得到用户批准后再动代码。
- 改变插件行为的提交，要按 Moirai 的惯例同时加 `CHANGELOG.md` 条目并升 `metadata.yaml` 版本（见工作区 `AGENTS.md`）。
- 结构或约定变了，同步更新本文件。
