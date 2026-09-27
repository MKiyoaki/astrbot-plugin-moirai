# canon：原作剧情记忆

`core/canon/` 把 Arknights-Texts 导出的 story_pack 抽取成独立的剧情记忆库 `canon.sqlite`，扮演阿米娅时按对话取回她在原作中经历或得知的事。完整规格见 Arknights-Texts 仓库的 `docs/canon-memory-design.md`（spec v1.4）。本文件记录 Moirai 这边的实现状态和与规格不同的地方。

> **版权**：story_pack、canon.sqlite、审阅页、基准输出和评测集都含剧情原文，只能留在本机，不能提交到任何 git 仓库。测试夹具全部是自编文本。

## 文档索引

| 文档 | 内容 |
|---|---|
| 本文件 | 当前状态、信息流、Bot 验收计划、与规格不同的地方 |
| [canon 抽取与基准](canon-extraction.md) | 命令、全库构建、增量规则、本地修正、抽取基准与评测框架 |
| [canon 抽取版本记录](canon-extraction-history.md) | v3–v11 各版 prompt 的改动和试跑结果，从新到旧 |
| [canon 时间线与事实有效期](canon-temporal-facts.md) | 时间事实的数据模型、候选构建、审阅与查询 |
| [canon 终端试聊](canon-terminal.md) | `moirai canon test` 的当前行为：每轮流程、证据预算、检索、综述、档案 |
| [canon 运行时结构](canon-runtime-architecture.md) | 运行时代码结构、已知问题、迁到正式 Bot 路径的指引 |
| [canon 检索实验](canon-retrieval-experiment.md)（英文） | 检索设计、题库和各次测量 |
| [canon 对话质量](canon-dialogue-quality.md)（英文） | 终端对话各轮改动的动机和测量 |

每个数字和规则只在负责它的文档里写一次，其他地方链接过去；改动时先找到它的出处。

## 当前状态

M1（B1–B5）已完成；M2（B6–B9）的正式路径还没开始，但检索、装填和回复核验已经在终端试聊里做成原型。

| 部分 | 状态 |
|---|---|
| B1 目录结构 | `config.py`、`schema.sql`、`store.py`、`prompt.py`、`extract.py`、`importer.py`、`cli.py`；基准用的 `audit.py`、`probes.py`、`compare.py`、`judge.py`、`bench.py`；时间事实用的 `fact_extract.py`、`fact_review.py`、`temporal.py`；终端原型用到的 `retrieval.py`、`lexical.py`、`vector_index.py`、`context.py`、`overview.py`、`gateway.py` |
| B2 配置 | `_conf_schema.json` 新增 `canon` 分组；`PluginConfig.get_canon_config()`；`canon_persona_map` 格式错误时对所有人格都不生效。插件里目前只有配置，没有调用 canon 的代码 |
| B3 canon.sqlite | schema v5（v2–v4 的旧库打开时原地升级）；trigram 全文表（不可用时降级为 bigram）；库内 `event_vec` 随共享 embedding 的维度创建，模型身份变化时清空重编码。终端试聊不读这两类表，见 [canon 终端试聊](canon-terminal.md) 的“检索”一节 |
| B4 抽取 | 默认 `canon-extract-v10`（已运行 100 场景与 618 场景全量）；可选 `canon-extract-v11`（只跑过 20 和 100 场景试验）。确定性 user prompt、10 条校验规则、带问题清单的重试（连续失败最多 4 次）、超过 2 万字的场景分块、解析前修复字符串内部未转义的英文双引号。见 [canon 抽取与基准](canon-extraction.md) |
| B5 导入 | 命令行导入；按 scene_hash 增量；抽取缓存；中断后续跑；删除包里已没有的场景；另有不调用模型的干员档案导入 `archive-import` |
| 时间事实候选 | 全库分块抽取与失败续跑、审阅包与冲突分组、人工批准后导入、偏序与覆盖判断。V10 用 `canon-facts-v2`，V11 用 `canon-facts-v3`。V10 全库有 5,930 条候选，全部未审阅，库里没有已批准的事实。见 [canon 时间线与事实有效期](canon-temporal-facts.md) |
| 抽取基准 | `cli bench` / `compare` / `judge`：真实接口、回放、估算；金标准探针、逐事件对比、重测信度、可选 LLM 裁判；手动测试用 `run_canon_dev.py` |
| 终端试聊原型 | `moirai canon test`：路由、hybrid 检索、综述、结构扩展、档案工具、回复核验。主体逻辑在仓库根目录的 `run_canon_chat.py`，不是正式路径。见 [canon 终端试聊](canon-terminal.md) |
| B6–B9 检索、注入、命令、初始化 | 正式路径未开始。前提是把终端原型迁进 `core/canon`，见 [canon 运行时结构](canon-runtime-architecture.md) |

`/mrm canon import` 属于 B8，在 M2 接入；目前只有命令行入口。

## 全库构建准备与 Bot 验收

V10 的真实 Nexus 全库构建已运行：618 个场景中 616 个事件抽取成功，生成 5,930 条时间事实候选；两个事件抽取失败的场景跳过了事实抽取。候选仍全部待审阅，库里没有已批准的时间事实。M2 仍需完成一条可在真实 Bot 对话中工作的检索与注入路径，并用已审阅数据验证。它仍使用 B6–B9 规定的正式路径，不另写一套仅供试跑的检索逻辑；原规格的全库失败率、检索延迟和 B10 测试验收目标不变。

Bot 试跑用的库原定为本机 `.dev_data/canon/v7/20/api/20260924-045430-kcl-arc_nexus/canon.sqlite`（20 个场景、164 个事件，`canon-extract-v7`，`vec_dim=0`）；现在另有 v10 全库 `.dev_data/canon/v10/all/build/canon.sqlite` 和它的派生向量索引。开始 B6 前要决定用哪份库，以及正式路径用库内 `event_vec` 还是派生索引（见 [canon 运行时结构](canon-runtime-architecture.md) 的待决问题）。无论用哪份，都**复制**到 Bot 的 `data_dir/canon/canon.sqlite` 后再启用，保留原件供对照。库和测试记录里若含剧情原文，都只留在本机。

实施与验证顺序：

1. 先按 [canon 运行时结构](canon-runtime-architecture.md) 把终端原型的检索和装填逻辑迁进 `core/canon`，再完成 B6 检索、B7 渲染及 Core `before_generation` 注入、B9 生命周期；先接入 B8 的 `/mrm canon status` 和 `/mrm canon test`，便于检查实际命中与渲染结果。保持 canon 默认关闭，只让显式映射的人格桶使用。加入相应 B10 离线测试，覆盖检索降级、token 预算、博士称呼、时间过滤、`clear_namespace` 之后的注入以及 canon 故障不影响原有记忆。
2. 在启用 Core Event Protocol v1 的 AstrBot 中，把试跑库映射到阿米娅人格桶，用同一批问题先看 `/mrm canon test` 的事件、分数、证据，再看真实回复和实际注入块。分别检查范围内的剧情、试跑库范围之外的话题、博士身份开关、时间点过滤、重复提问及 canon 不可用时的降级。范围外问题要分别记录“没有命中 canon”和“Bot 最终怎样回答”：模型自带知识也可能回答，不等于 canon 泄漏。
3. 记录错误命中、漏召回、错误渠道、原文证据不贴题和回答中的身份混淆，用户审阅后决定是否需要调整检索、渲染或抽取。确认试跑可用，再完成 B8 后台全库导入与其余 B10 测试，并按原规格验收当前 story_pack 的全部场景。当前包的 `manifest.json` 记录 618 个场景；规格中的 622 是旧规模，导入数量以当次包为准。

Bot 运行时的 canon 检索不调用抽取模型；真实对话仍按 Bot 所用生成模型计费。插件里目前只有配置项，设置 `canon_enabled` 本身还不能启动上述试跑。

## 信息流

```
Arknights-Texts（不调用大模型，确定性）
  upstream/ 镜像 → build_index.py → processed/index.sqlite → export_story.py → exports/story_pack/
                                                                  manifest.json · scenes.jsonl · characters.json
                                                                  entities_seed.json · samples/
────────────────────────────── 手动复制或指定路径 ──────────────────────────────
Moirai core/canon（M1，已实现）
  cli import / cli bench → Importer
    ① 读 story_pack，第一次导入时写入实体种子
    ② 按 scene_hash + PROMPT_VERSION 和 canon.sqlite 对比，得出要处理的场景；删除包里已没有的场景
    ③ 每个场景：抽取缓存（extractions 表）命中就直接用，不调用接口；否则
         build_user_prompt（L 编号台词）+ SYSTEM_PROMPT → 模型接口 → 去 <think>/代码围栏 → JSON
         → 10 条校验 → 不通过就带着问题清单重试，连续失败最多 4 次 → 结果（成功或失败）写入 extractions
    ④ 一个事务写入：scenes、lines、events（触发器同步全文索引）、event_evidence（L 编号换成 line_key）、
       event_beats（触发器同步 beats_fts）、views / view_evidence、episodes、cognitions、edges、
       entities / aliases / event_entities
    ⑤ 有 encoder 时给新事件编码向量（event_vec）；更新 meta；输出报告
  cli dump → review.html（人工审阅）；cli status → 库的概况
────────────────── M2，未实现（终端原型见 canon-terminal.md）──────────────────
  Core before_generation → event_handler：先注入 Moirai 原有的 memory 块，再调用 canon.inject
    → 查询解析：意图、主体、时间点
    → 检索：向量 + 事件文本 + 原文台词 + 实体四路加权 RRF；角色不知情（unstated）的事件只作导航，不注入
    → 装填 canon 块：命中事件的摘要 + 相关原文行（{DOCTOR} 按人格桶设置渲染，按 token 预算截断）
    → 注入 system prompt
```

数据只单向流动：canon 只进 prompt，聊天内容永远不写回 canon。检索不调用模型；导入和基准会调用抽取接口，终端的回复核验会调用对话模型。Bot 路径上怎样核验还没有决定，见 [canon 运行时结构](canon-runtime-architecture.md) 的待决问题。

## 与规格不同的地方

- **`events` 表多了整数主键 `rid`**，`event_id` 改为 `NOT NULL UNIQUE`。全文检索按 rowid 关联，文本主键表的 rowid 在 `VACUUM` 后可能改变，会让全文索引错位。
- **抽取出的实体先按别名查找**：名字已经是某个实体的别名（例如种子里的英文代号），就复用那个实体，不再新建。
- **不用 `RETURNING`**：规格要求 SQLite ≥ 3.34，`RETURNING` 需要 3.35。
- **测试用 unittest**：规格 B10 写的是 pytest，但本仓库环境没有 pytest，`run_realtime_dev.py --self-test` 用 unittest 发现测试。`tests/test_canon.py` 按现有测试的写法编写；`tests/` 按本仓库的 `.gitignore` 只留在本地。
- **`SimpleLLMClient`** 增加可选参数 `timeout`（默认仍是 60 秒）和 `temperature`（默认仍是 0.1，裁判用 0），并把接口返回的 `usage` 带回来，用于统计 token。它固定发送 `temperature: 0.1`；部分推理模型只接受默认的 temperature，会返回 400，基准里记为接口失败，真实运行前先用一个场景试通。接口返回错误时，异常信息里带上响应体的前 300 字，方便看到网关给出的原因。
- **`extract_scene` 和 `Importer` 多了可选的 `observer`**：每次模型调用后收到一条记录（块号、第几次、耗时、token、校验问题、原始回复），基准用它统计；正式导入不传。
