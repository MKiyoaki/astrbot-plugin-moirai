# canon 运行时结构

本文件记录 canon 运行时代码**现在**的结构、已知的结构问题，以及把终端原型迁到正式 Bot 路径（B6–B9）时的指引。指引是给后续开发者和编码 agent 的启发与约束，不是已批准的计划：动代码之前，先在 `docs/TODO.md` 写出具体计划并得到用户批准（这个文件被 `.gitignore` 忽略，只在本机）。终端的行为说明见 [canon 终端试聊](canon-terminal.md)，整体状态见 [canon：原作剧情记忆](canon.md)。

## 现在的结构

| 环节 | 位置 | 说明 |
|---|---|---|
| 抽取与写入 | `core/canon/extract.py`、`fact_extract.py`、`importer.py`、`store.py` | `CanonStore` 基于 aiosqlite，异步、可写；只有导入和基准会用 |
| 只读访问与索引 | `run_canon_chat.py` 的 `CanonReader` | 同步 sqlite、`mode=ro`；启动时在内存里建三份两字 BM25（事件文本、原文台词、场景资料）和别名表 |
| 查询理解与路由 | `run_canon_chat.py` 的 `TurnPlan`、`plan_turn`、`route` | 靠文件顶部的关键词表判断意图；`core/canon/context.py` 的 `resolve_name` 做名字纠正 |
| 召回与融合 | `core/canon/retrieval.py`（`fuse`、`CanonRetrieval`）、`lexical.py`、`vector_index.py` | hybrid 需要派生向量索引；embedding 由 `devtools/retrieval.py` 的 `ProviderBridge` 提供 |
| 结构扩展与综述 | `core/canon/context.py` 的 `expand_events`、`overview.py`；`CanonReader.overview_search`、`expand_context` | 综述的候选打分和组包仍在 `run_canon_chat.py` |
| 证据装填与预算 | `run_canon_chat.py` 的 `fact_search`、`fill*`；`core/canon/gateway.py` 的 `EvidencePack` | 预算常量直接写在 `fill_*` 里 |
| 提示词与工具 | `run_canon_chat.py` 的 `knowledge`、`build_system`、`OUTPUT_RULES`、三个工具 schema | |
| 生成 | `run_canon_chat.py` 的 `generate`、`ModelClient`（httpx，同步） | |
| 核验 | `core/canon/gateway.py` 的 `check_reply` | 已在 `core/canon`，会调用模型 |
| 时间事实 | `core/canon/temporal.py` 的 `resolve`；`CanonReader.fact_context` | |
| 评测 | `devtools/canon/retrieval.py`、`dialogue_eval.py`、`fact_focus.py` | 都直接 import `run_canon_chat` |
| 插件侧 | `core/config.py` 的 `get_canon_config`、`core/canon/config.py` 的 `CanonConfig` | 只有配置；`event_handler` 没有调用 canon |

`tests/test_canon_context.py`、`test_canon_lexical.py`、`test_canon_vectors.py` 也直接从 `run_canon_chat` 导入被测函数。

## 已知的结构问题

1. **主体逻辑在仓库根目录的开发脚本里。** 路由、召回、装填、提示词和生成都在 `run_canon_chat.py`（约 1,800 行）。插件不能依赖这个脚本，而 canon.md 要求 B6–B9 不另写一套仅供试跑的检索逻辑，所以正式路径的前提是先把这些逻辑迁进 `core/canon`。
2. **索引有两套。** 向量：库内 `event_vec`（`import --embed` 写入）和构建目录旁的派生索引（终端实际用的）。全文：库内 trigram 表 `events_fts` / `beats_fts` 和启动时建的内存 BM25（终端实际用的）。
3. **融合有两套。** canon 用加权 RRF（k=10，四路权重不同），Moirai 原有记忆用 `core/retrieval/rrf.py` 的等权 RRF（k=60）。
4. **预算互不知晓。** 终端的证据预算、插件配置 `canon_token_budget` 和原有 memory 块的预算各自独立（数字见 [canon 终端试聊](canon-terminal.md) 的“证据预算”）。
5. **证据包每轮重建。** 工具往返不写入历史，上一轮用过的证据在下一轮就没有了；追问只能靠 `focus` / `topics` 重新检索，核验器也看不到上一轮的依据。
6. **同步和异步混用。** 读取与生成是同步的（sqlite3、httpx），插件和 `CanonStore` 是异步的。
7. **已写入但没用上的数据。** `cognitions`（逐场景的人物态度）和 V11 的 `view_access` 都已入库，运行时没有读取。

## 目标分层（启发，不是定案）

参照 MemOS 的“接口层 / 操作层 / 基础设施层”划分，按职责拆成四层，终端和 Bot 共用同一套：

- **查询解析**：把 `TurnPlan` 整理成带类型的查询结构（意图、主体、焦点、`as_of`、要查的记忆类型——事件、综述、档案、事实——以及知情要求）。纯函数，除别名查找外没有 IO。
- **检索**：各路召回、融合、结构扩展和综述候选。输入查询结构，输出带 trace 的候选；不调用模型。
- **调度**：给候选分配预算，装填 `EvidencePack`。接入 Bot 后，这一层也负责和原有 memory 块分配同一份预算。
- **核验**：`gateway.py`，已在 `core/canon`。

迁完后，`run_canon_chat.py` 只剩参数解析、会话状态和打印；Bot 的 `before_generation` 处理函数调用同样的三层。

## 迁移启发

1. **先搬纯函数。** 路由判断、`fill_*` 装填和预算规则连同常量一起搬，测试改为从 `core/canon` 导入。每次只搬一层。
2. **再拆 `CanonReader`。** 分成“只读数据访问”和“内存索引”两部分。同步读取可以留着，由 Bot 侧放进线程执行，但边界要写清楚。
3. **评测跟着切换。** `devtools/canon/*.py` 改为从 `core/canon` 导入，保证评测测的就是正式路径。
4. **每一步做逐题回归。** 对同一个库用 `moirai canon test --questions --retrieval baseline` 跑 200 题，和迁移前的报告逐题比对路线和注入事件 ID，必须完全一致。hybrid 模式同理，但要加 `--allow-remote`，会把查询发给 embedding 服务。
5. **迁移完成后再做 B6–B9。** 迁移本身不改行为；行为改动另开条目。

## 必须保持的约定

- 运行时只读，不写 `canon.sqlite`；聊天内容不写回 canon。
- `unstated` 事件只做导航，不注入；`role_candidate` 获知标签和 `reported` 事实候选都不当作角色知识或世界事实。
- 证据编号可追溯：事件 `E`、档案 `A`、已审阅事实 `F` 都能回到 `line_key`；对话引用 `C` 只说明谁在聊天里说过什么，不证明世界事实。
- 检索不调用模型；只有生成和核验调用。
- 每个预算数字只有一个出处。
- 已保留的抽取 prompt 版本一字不改。
- 剧情原文、数据库、评测报告只留在本机，不进 git；测试只用自编文本。
- Moirai 依赖 Core，不依赖 Oedipus；和 Oedipus 的交互只走 Core 的版本化协议。

## 待决问题

这些需要实验数据或用户决定，不能在迁移时顺手合并：

1. **索引选哪套**：向量用 `event_vec` 还是派生索引；全文用 trigram 表还是内存 BM25（要比较召回、启动时间和常驻内存）。
2. **融合怎样统一**：用哪个 k 和权重，用 200 题评测决定。
3. **Bot 的预算**：插件默认值和终端基础值该取哪个；canon 块和原有 memory 块怎样分配名额。
4. **Bot 里怎样核验**：Core Event Protocol v1 的 contribution 只有 prompt 文本块、`reply_prefix` 等，没有替换最终回复的操作，所以终端 gateway 不能原样用在 Bot 上。要么只注入约束，要么扩展 Core 协议；后者是 Core 仓库的改动，需要走 Core 的 TODO 批准。
5. **聊天记忆污染**：Bot 说出的剧情内容会被 Moirai 的事件抽取器写进聊天记忆，之后作为“我们聊过的事”召回时会绕过 gateway。需要在抽取或召回时标注这类内容的来源。
6. **跨轮工作记忆**：是否保留最近几轮的证据 ID，下一轮以压缩形式带回，供追问和核验使用。
7. **未用数据**：`cognitions`、`view_access` 是否进入检索或注入；进入前需要审阅。

## 参考

- MemOS（[arXiv 2507.03724](https://arxiv.org/abs/2507.03724)）：接口 / 操作 / 基础设施三层，以及每条记忆带来源签名、使用频率、版本链的元数据。canon 语料是冻结的只读记忆，论文里的生命周期衰减、KV 缓存注入和参数记忆都不适用；适用的是分层和来源元数据。
- HaluMem（[arXiv 2511.03506](https://arxiv.org/abs/2511.03506)）：把记忆幻觉拆成抽取、更新、问答三个阶段分别计量，发现错误主要在抽取和更新阶段产生并向后传递。canon 已有抽取探针、检索题库和对话评测，缺的是时间事实的“更新”阶段（状态变更对）评测。

## 流程

- 计划写进本机的 `docs/TODO.md`，得到用户批准后再动代码。
- 改变插件行为的提交，要按 Moirai 的惯例同时加 `CHANGELOG.md` 条目并升 `metadata.yaml` 版本（见工作区 `AGENTS.md`）。
- 结构或约定变了，同步更新本文件。
