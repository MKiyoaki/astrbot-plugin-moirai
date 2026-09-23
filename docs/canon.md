# canon：原作剧情记忆

`core/canon/` 把 Arknights-Texts 导出的 story_pack 抽取成独立的剧情记忆库 `canon.sqlite`，扮演阿米娅时按对话取回她在原作中经历或得知的事。完整规格见 Arknights-Texts 仓库的 `docs/canon-memory-design.md`（spec v1.3）。本文件记录 Moirai 这边的实现状态和与规格不同的地方。

> **版权**：story_pack、canon.sqlite、审阅页、基准输出和评测集都含剧情原文，只能留在本机，不能提交到任何 git 仓库。测试夹具全部是自编文本。

## 当前状态（M1）

| 部分 | 状态 |
|---|---|
| B1 目录结构 | `config.py`、`schema.sql`、`store.py`、`prompt.py`、`extract.py`、`importer.py`、`cli.py`，以及基准用的 `audit.py`、`probes.py`、`compare.py`、`judge.py`、`bench.py` |
| B2 配置 | `_conf_schema.json` 新增 `canon` 分组；`PluginConfig.get_canon_config()`；`canon_persona_map` 格式错误时对所有人格都不生效 |
| B3 canon.sqlite | 建表、trigram 全文检索（不可用时降级为 bigram）、向量表随 encoder 维度创建，encoder 变化时清空重编码 |
| B4 抽取 | system prompt `canon-extract-v3`（按自然断点切事件，summary 最多 300 字，每个事件附 0–5 条 beats）、确定性 user prompt、8 条校验规则、带问题清单的重试（共 3 次）、超过 2 万字的场景分块、解析前修复字符串内部未转义的英文双引号 |
| B5 导入 | 命令行导入；按 scene_hash 增量；抽取缓存；中断后续跑；删除包里已没有的场景 |
| 抽取基准 | `cli bench` / `compare` / `judge`：真实接口、回放、估算；金标准探针、逐事件对比、重测信度、可选 LLM 裁判；手动测试用 `run_canon_dev.py`，见下文 |
| B6–B9 检索、注入、命令、初始化 | 未开始（M2） |

`/mrm canon import` 属于 B8，在 M2 接入；M1 只有命令行入口。

## 信息流

```
Arknights-Texts（不调用大模型，确定性）
  upstream/ 镜像 → build_index.py → processed/index.sqlite → export_story.py → exports/story_pack/
                                                                  manifest.json · scenes.jsonl · characters.json
                                                                  entities_seed.json · pilot.txt
────────────────────────────── 手动复制或指定路径 ──────────────────────────────
Moirai core/canon（M1，已实现）
  cli import / cli bench → Importer
    ① 读 story_pack，第一次导入时写入实体种子
    ② 按 scene_hash + PROMPT_VERSION 和 canon.sqlite 对比，得出要处理的场景；删除包里已没有的场景
    ③ 每个场景：抽取缓存（extractions 表）命中就直接用，不调用接口；否则
         build_user_prompt（L 编号台词）+ SYSTEM_PROMPT → 模型接口 → 去 <think>/代码围栏 → JSON
         → 8 条校验 → 不通过就带着问题清单重试，最多 3 次 → 结果（成功或失败）写入 extractions
    ④ 一个事务写入：scenes、lines、events（触发器同步全文索引）、event_evidence（L 编号换成 line_key）、
       event_beats（触发器同步 beats_fts）、views / view_evidence、episodes、cognitions、edges、
       entities / aliases / event_entities
    ⑤ 有 encoder 时给新事件编码向量（event_vec）；更新 meta；输出报告
  cli dump → review.html（人工审阅）；cli status → 库的概况
────────────────────────────────── M2，未实现 ──────────────────────────────────
  Core before_generation → event_handler：先注入 Moirai 原有的 memory 块，再调用 canon.inject
    → 检索（全文〔事件和 beats〕+ 向量 + 实体三路召回，RRF 融合，按渠道和层级加权）
    → 渲染 canon 块：命中的整个事件 + 命中 beat 的原文行（{DOCTOR} 按人格桶设置渲染，按 token 预算截断）
    → 注入 system prompt
```

数据只单向流动：canon 只进 prompt，聊天内容永远不写回 canon。运行时不调用大模型；只有导入和基准测试会调用抽取接口。

## 命令行

在插件根目录下运行，API key 只从环境变量读取：抽取用 `CANON_API_KEY`，裁判用 `CANON_JUDGE_API_KEY`（没有就用 `CANON_API_KEY`）：

```bash
python -m core.canon.cli import --pack <story_pack> --db <canon.sqlite> \
    --api-url <OpenAI 兼容地址> --model <模型> [--only pilot.txt] [--concurrency 2] [--timeout 300]
python -m core.canon.cli status --db <canon.sqlite>
python -m core.canon.cli dump --db <canon.sqlite> --only pilot.txt [--out review.html]
python -m core.canon.cli bench --pack <story_pack> (--only <清单> | --scene <key> ...) \
    (--estimate | --replay <目录> | --api-url <地址> --model <模型>) \
    [--probes <探针文件>] [--baseline <运行目录>] [--repeats N] [--price-in <每百万输入 token 单价> --price-out <输出单价>]
python -m core.canon.cli compare <运行目录> <运行目录> [...]
python -m core.canon.cli judge --run <运行目录> --pack <story_pack> --api-url <地址> --model <模型> [--repeats 3] [--labels <人工标注>]
```

`dump` 生成本地 HTML 审阅页：左边是带 L 编号的原文，右边是事件、获知渠道、第一人称摘要、认知和事件关系；鼠标移到事件上会高亮它的证据行。

## 抽取基准

`bench` 每次运行都新建一个运行目录和独立的 `canon.sqlite`，不读取也不写入正式库或试跑库的抽取缓存，走的是和正式导入完全相同的 `Importer → extract_scene → CanonStore` 路径。运行目录按类别放在 `.dev_data/canon/bench/` 下：真实接口在 `api/`，回放在 `replay/`，`--repeats` 的一组运行在 `repeats/`（外加 `stability.md`）。`--out` 可以指定别的上级目录，这时不再分类。

### 模式和命令

| 命令 | 作用 | 费用 |
|---|---|---|
| `bench --estimate` | 首轮调用次数、输入字数、粗略 token 范围、会切块的场景 | 0 |
| `bench --replay <目录>` | 本机假接口按 user prompt 返回已保存的回复，走一遍真实的 HTTP 客户端、解析、校验、落库和报告。目录可以是试跑目录（`index.json` + `out/`）或上一次基准的运行目录；切块的场景不能回放 | 0 |
| `bench --api-url --model` | 真实接口 | 按用量 |
| `bench ... --probes <文件>` | 用金标准探针评分 | 0 |
| `bench ... --baseline <运行目录>` | 总览加一列基线，并和基线逐事件对齐对比 | 0 |
| `bench ... --repeats N` | 同一配置跑 N 次，报告重测信度（`stability.md`） | N 倍 |
| `compare <运行> <运行> [...]` | 两个运行逐事件对比；三个以上报告重测信度 | 0 |
| `judge --run <运行目录> --api-url --model [--repeats 3] [--labels <人工标注>]` | LLM 裁判，结果写回同一个运行目录的报告 | 每场景每次 1 次调用 |

运行目录里有：

| 文件 | 内容 |
|---|---|
| `report.md` | 总览（可和基线对比）、失败的调用（接口失败 / JSON 格式错 / 校验不通过）、探针、逐事件对比、裁判、质量检查、全量外推、逐场景表、需要人工看的条目 |
| `summary.json` | 总览的数字，可作为下一次运行的 `--baseline` |
| `results.jsonl` | 每个场景一行：状态、块数、每次调用的耗时 / token / 校验问题、质量指标、自动检查结果 |
| `review.html` | 这次抽取结果的审阅页 |
| `failures/` | 校验不通过的原始回复，每次调用一个文件 |
| `judge.jsonl` | 跑过 `judge` 才有：逐事件的裁判结果（含每次重复的判断） |
| `console.log`、`judge.log` | 用 `run_canon_dev.py` 跑才有：运行和裁判时的逐次调用记录 |
| `canon.sqlite` | 这次运行的库，可以用 `status` / `dump` 查看，也可以作为 `--replay` 或 `compare` 的输入 |

### 开发工具 run_canon_dev.py

插件根目录下的 `run_canon_dev.py` 用来手动跑基准，写法和 `run_realtime_dev.py` 一样：模型、地址和 key 取自本机的 `run_config.py`（`MODEL_TYPE`，可以用 `CANON_MODEL_TYPE`、`CANON_JUDGE_MODEL_TYPE` 单独指定），story_pack、探针、场景清单、基线和单价都在 `run_config.py` 的 `CANON_*` 里设置，模板见 `run_config.py.example`。它直接调用 `run_bench` 和 `judge_into`，所以结果和命令行的 `bench` / `judge` 完全一样。

```bash
python run_canon_dev.py                          # 列出已有的运行和主要指标
python run_canon_dev.py estimate                 # 估算，不调用接口
python run_canon_dev.py run                      # 真实接口；开始前显示模型和估算并要求确认（-y 跳过）
python run_canon_dev.py run --replay pilot       # 回放 v1 试跑
python run_canon_dev.py run --repeats 3          # 重测信度
python run_canon_dev.py judge [运行]              # LLM 裁判，默认最近一次真实接口的运行；开始前确认
python run_canon_dev.py compare <运行> <运行> [...]
python run_canon_dev.py open [运行] [--report]    # 用浏览器打开审阅页或报告
```

`<运行>` 可以写目录名、名字里的一段、路径，或 `latest` / `latest-api` / `latest-replay`；回放来源、基线和 `compare` 还可以写 `pilot`。

运行时每次模型调用打一行（场景、第几次、耗时、token、校验问题和原始回复文件），每个场景结束打一行；终端底部的状态行每秒刷新，显示用时、完成数、预计剩余时间、累计 token 和费用，以及正在进行的调用各自等了多久。输出不是终端时，状态改为每 30 秒打一行。这些行同时写进日志：正常结束后移到运行目录的 `console.log`（裁判是 `judge.log`），中断时留在 `bench/logs/`。`compare` 的结果写到 `bench/compare/`。Ctrl+C 中断后，没跑完的运行目录在列表里标为"未完成"，已经花掉的调用不会重放。

`.dev_data/` 整个被 `.gitignore` 忽略，`run_config.py` 也是；工具本身匹配 `/run_*_dev.py`，同样默认不跟踪，要提交得像 `run_realtime_dev.py` 那样显式 `git add -f`。

### 评测框架和出处

| 维度 | 做法 | 借鉴 |
|---|---|---|
| 必须抽到的情节 | 探针的锚点行（line_key）至少一半被某个事件精确引用算覆盖；渠道也对才算通过；按重要度 1–3 加权。精确引用见下文“事件证据是整段时怎么算” | 重要度加权召回，arXiv 2604.03141 |
| 不能越界 | 缺席场景只能 unstated、不写 episode；名单外说话人的行不能当她的证据；不能出现原文没有的词 | 知识边界的可见 / 不可见两组，arXiv 2606.25632（ReverieMem） |
| 合成分数 | 覆盖组和边界组的准确率按条数加权取调和平均（仿 KBF），任何一组崩掉总分都会降 | 同上 |
| 失败归因 | 未抽出 / 范围内未引用 / 渠道错误 / 被合并 / 越界 / 场景失败；她的台词覆盖率按台词密度分段 | 失败分类与多实例压缩，arXiv 2602.10881；按阶段归因，arXiv 2605.30771 |
| 版本对比与稳定性 | 按证据行的重合系数（交集除以较小的集合，阈值 0.5）对齐事件，报告事件 F1、渠道一致率和 Cohen's κ；同配置多跑即重测信度 | 元组级 P/R/F1，arXiv 2602.10881；机会校正的一致性，arXiv 2606.19544 |
| 证据是否支撑摘要 | 可选 LLM 裁判：引证召回率（证据完全支撑摘要的事件占比）、引证精确率（完全支撑的事件里证据行不多余的比例）、渠道支撑率 | ALCE，arXiv 2305.14627 |
| 裁判可信度 | 裁判温度 0；`--repeats 3` 报告重测 κ；`--labels` 和人工标注比 κ | arXiv 2606.19544；DREAM 的人工校验，arXiv 2608.05170 |
| 确定性优先 | 能从原文机械判断的（说话人、渠道边界、外部人名、代词、字面"博士"）不交给 LLM | GroundEval，arXiv 2606.22737 |
| 成本 | 按这次每个输入字的 token 用量外推全量导入的 token 和费用 | 组件化评测的成本维度，arXiv 2606.24775 |

### 事件证据是整段时怎么算

v1、v2 的事件证据是挑出的十来行关键行。v3 把事件定义成一段连贯的情节以后，arc:nano 把事件证据写成了整段的行区间：20 个场景里多数场景 95–100% 的行都落在某个事件的证据里，单个事件最多 118 行。按原来的算法，这会让两个指标失真：

- 探针覆盖和她的台词被引用比例几乎自动满分，因为每个锚点、每句台词都落在某个事件的范围里。这次运行的台词被引用比例按旧算法是 0.975，按新算法是 0.848。
- 和基线的事件 F1 被压低。同一件事，基线引 10 行，v3 引 70 行并且包含这 10 行，Jaccard 只有 0.14，达不到原来 0.2 的阈值。这次运行按旧算法只配上 59 个事件，F1 0.534；改用重合系数后配上 89 个，F1 0.805。

现在的算法：

- **精确引用**（`audit.cited_lines`）：事件有 beats 时，取 beats 的证据加视角证据；没有 beats 时，取事件证据加视角证据。v1、v2 的结果没有 beats，所以分数不受影响，基线重新计算后完全不变。探针覆盖和她的台词被引用比例都按精确引用算。
- **事件管的整段**：事件证据加精确引用，只用来判断"被合并"，也就是几条渠道不相容的探针是否落在同一个事件的范围里。锚点在某个事件的范围里、却没有被精确引用时，记为"范围内未引用"，不算覆盖。
- **对齐**：用重合系数配对。一个事件被拆成几段，或几段被并成一个时，一对一的配对只配上其中一段，其余记为只在一方出现，所以 F1 仍然反映粒度差异。

没有采用的：对话层面的两两比较裁判（ReverieMem、DREAM 的未来泄漏与因果一致性、CoSER）和 LongMemEval / LoCoMo 式问答，这些都需要检索和生成，放到 M3 的评测集（规格第 6 节）。

### 金标准探针

探针文件是 `Arknights-Texts/eval/canon_extract_probes.jsonl`（只留在本机），每行一条，只引用 scene_key 和 line_key：

```json
{"id": "05-leader", "scene": "obt/main/...", "kind": "cover", "anchors": ["obt/main/...#112.1", "..."],
 "channels": ["experienced"], "importance": 3, "note": "……", "status": "draft"}
```

`kind`：`cover`（必须覆盖，`channels` 为允许的渠道）、`absent`（她缺席）、`no_episode`、`not_evidence`（`anchors` 不能作为她的视角证据）、`not_mention`（输出不能出现 `text`）。`status: draft` 表示还没人工审定，报告会注明。line_key 不在场景里（上游改过）的探针记为过期，不计分。

### 自动质量检查

`audit.py` 只做能从原文机械判断的事，结果是给人工审阅的线索，不是成败标准：

- 字面"博士"
- 疑似用"他"指代博士
- 名单外说话人的台词被当作她的视角证据
- 她说了话却标 unstated
- 亲历或目睹但视角证据里既没有她的台词也没有提到她
- 她未出场却写了 episode
- 疑似外部知识：输出里出现原文、官方简介、前情都没有的人名。人名取自实体种子：`character_table` 的角色全部保留，只来自说话人的名字按泛称规则过滤掉"军官""孩童"之类
- 实体名不在原文：弱信号，在 v1 试跑上 19 条里只有 1 条是真问题，其余多为改写
- 事件顺序颠倒

另外还会统计：
- 渠道分布
- concept 类实体数
- 用 ta 指代博士的次数
- 她的台词被引用的比例（按精确引用算，按台词密度分段）
- 边的数量

"她"指代博士不做机械检查，因为摘要里的"她"几乎都指目标角色本人。

### 这几条路径只能用基准跑

| 路径 | 怎么跑 |
|---|---|
| 真实的 HTTP 调用、解析、落库 | `--replay .dev_data/canon/pilot`，零成本 |
| 真实模型的首次通过率、重试、耗时、token | `--api-url --model --only pilot.txt`，会产生费用 |
| 长场景切块 | 在真实接口的运行里加 `--scene obt/main/level_st_13-03`（约 2.1 万字，切成 2 块） |
| AstrBot provider 的调用路径 | M2（B8、B9）接入后才有 |

> **数据外发**：规格 B11 规定剧情文本只在抽取时发给用户配置的接口。`judge` 会把被引用的原文行另外发给裁判接口，所以默认不运行，只在显式调用时执行。

## 事件粒度（canon-extract-v3）

v2 在 KCL `arc:lite` 上把一段交火拆成一拍一拍：场景 01 有 8 个事件，其中 5 个是她只在旁边看的碎片，每个只有一行视角证据。这样拆，检索时抓不到主线，注入名额会被同一段情节的碎片占满，输出 token 也会随事件数增加。只减少事件数，150 字的 summary 又装不下一整段情节。v3 按下面几篇论文验证过的做法改成两层：

| 做法 | 实现 | 依据 |
|---|---|---|
| 事件 = 一段连贯的情节，只在自然断点切 | prompt 列出断点：场景或地点转换、一段对话或一轮交锋结束、话题转折，再加上她的参与方式改变；每个事件通常 8–40 行，每个场景通常 2–8 个事件 | SeCom：话题连贯的段落级记忆单元优于按轮次（过碎）和按会话（过粗）；ReadAgent：叙事长文在自然停顿点分页，并限定每页的最小和最大长度；Michelmann et al.：LLM 切分叙事事件与人的共识一致 |
| summary 用"缩写"写法，放宽到 300 字 | 按顺序保留起因、关键动作、台词要点和结果，而不是一句概括 | ReadAgent：让模型"缩写"比"总结"更能保留叙事流程；SeCom、LongMemEval：只用摘要当记忆会丢细节 |
| 细节作为检索键，不单独注入 | 每个事件附 0–5 条 `beats`（每条最多 25 字，带证据行），存进 `event_beats` 并建立 `beats_fts`；M2 检索时命中 beat，注入的是它所属的整个事件，再加上这条 beat 对应的原文行 | LongMemEval：保留原内容、把抽出的事实作为额外的检索键，recall@k 提高 9.4%，QA 提高 5.4%；MemGAS：多粒度并存优于单一粒度；ES-Mem：记忆单元同时保存摘要和原文，去掉原文时效果下降最多 |

事件数不设硬性上限，免得触发整次重试。`audit.py` 把"事件超过 8 条""事件只覆盖不到 3 行（场景至少 20 行时）""beat 证据不在事件证据里"作为提示写进报告，报告总览里有 beats 的数量。

出处：

- Pan et al., *On Memory Construction and Retrieval for Personalized Conversational Agents*（SeCom，ICLR 2025），[arXiv 2502.05589](https://arxiv.org/abs/2502.05589)：LOCOMO 上段落级 71.57、按轮次 65.58、按会话 63.16、摘要记忆 53.87（GPT4Score）；零样本 LLM 切分在 DialSeg711 上 F1 0.888。
- Lee et al., *A Human-Inspired Reading Agent with Gist Memory of Very Long Contexts*（ReadAgent），[arXiv 2402.09727](https://arxiv.org/abs/2402.09727)：断点选在场景转换、对话结束、叙事转折处，每页 280–600 词（QuALITY/QMSum）；NarrativeQA 的 ROUGE-L 比最好的检索基线高 31.98%。
- Wu et al., *LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory*，[arXiv 2410.10813](https://arxiv.org/abs/2410.10813)：用摘要或事实替换原内容会损失 QA；以事实做扩展检索键，recall@k +9.4%、QA +5.4%。
- *ES-Mem: Event Segmentation-Based Memory for Long-Term Dialogue Agents*，[arXiv 2601.07582](https://arxiv.org/abs/2601.07582)：基于事件分割理论切分，记忆单元保存边界描述、摘要和原文；消融实验中去掉原文下降最多。
- *From Single to Multi-Granularity: Toward Long-Term Memory Association and Selection of Conversational Agents*（MemGAS），[arXiv 2505.19549](https://arxiv.org/abs/2505.19549)：会话、轮次、摘要、关键词多粒度并存，LongMemEval-s F1 20.38，单一粒度 13.78。
- Michelmann et al., *Large language models can segment narrative events similarly to humans*，[arXiv 2301.10297](https://arxiv.org/abs/2301.10297)：GPT-3 切出的叙事事件边界比单个人工标注者更接近人工共识。
- Fountas et al., *Human-inspired Episodic Memory for Infinite Context LLMs*（EM-LLM），[arXiv 2407.09450](https://arxiv.org/abs/2407.09450)：按事件切分并做边界修正，使单元内部连贯、单元之间分开；这里只借鉴了"单元内连贯、单元间分离"的原则，没有用它基于 surprise 的切分算法。

## 增量规则

一个场景算已完成，要同时满足：库里的 `scene_hash` 等于包里的，且有当前 `PROMPT_VERSION` 下的成功抽取。场景行、台词行和全部抽取结果在同一个事务里写入，所以 hash 变化、prompt 版本变化、上次失败、上次中途中断的场景都会被重新处理，而已有成功缓存的场景不会再调用 API。

prompt 每升一版，旧版本的缓存都不再命中：试跑库 `.dev_data/canon/canon.sqlite` 里的 20 条 v1 缓存和 v2 的单场景运行，仍然可以作为 `--replay` 的来源和对比基线。

## 校验前的本地修正

这几种问题都在真实接口的试跑里出现过，而且都不值得整次重试。每次重试要重新生成整个场景，在 arc:lite 上一次要 1–1.6 万 token。所以先在本地修正，修正后照常经过 8 条校验。每次调用修了几处、丢了几条都记在 `results.jsonl`，报告总览里有合计。规格 v1.3 的 B4 也记录了这些修正。

- **未转义的引号**：模型常在 JSON 字符串里直接用英文双引号引用原话，比如 `"乙说"好"。"`，整段 JSON 因此解析失败。`parse_json` 直接解析失败时，把字符串内部后面不跟 `,` `:` `}` `]` 的引号改成 `\"` 再解析一次；能直接解析的 JSON 不做改动。引号后面紧跟半角逗号或冒号时判断不了，仍然按失败重试，重试的问题清单会提示引号的写法。
- **无歧义的格式问题**：`normalize_output` 把能确定对应到行号的证据统一成 `L` 行号数组。支持的写法有：
  - 整数 `2`、`"2"`、`"l2"`、全角 `"Ｌ２"`；
  - 区间 `"L8-L10"`，连接符也认 –、—、~、至；
  - 用 、或 , 分隔的列表；
  - 由以上写法混合组成的数组。

  它还会规范几种同样没有歧义的写法：枚举值（in_world_time、channel、边和实体的 type）去掉空格并转成小写；边的 `explicit` 如果写成字符串 `"true"` 就转成布尔值，`confidence` 写成数字字符串就转成数字；participants 写成一个字符串时拆成数组。倒序区间、`"第2行"` 这类认不出来的写法原样留下，交给校验。
- **不合格的辅助条目**：`prune_auxiliary` 丢掉不合格的单条实体、beat、认知和边，比如类型不对、证据越界、边指向不存在的事件。事件、视角和 episode 这些核心字段出错，仍然整次重试。
- **没有视角证据的在场渠道**：视角标成 experienced、witnessed、told 或 recalled，却一行视角证据都没给时，按总原则 5（无法判断时用 unstated）改成 `unstated`，不再整次重试。arc:lite 在场景 01 的两次试跑都遇到过这种情况。这些改动都记进报告的"丢弃或降级的条目"。
- **字面"博士"**：prompt 要求提到博士时写 {DOCTOR}，但 arc:nano 在 20 个场景的试跑里写了 61 处字面"博士"（v1 基线 12 处）。`normalize_output` 把 topic、summary、in_world_note、beats、实体名、视角 note、episode、认知的 target 和 stance 里的"博士"换成 {DOCTOR}，participants 里的换成 `@doctor`；实体名正好是博士的，按"entities 里不要列出博士"丢掉。story_pack 里没有别的人物被称作"某某博士"，替换没有歧义。"他"是否指博士判断不了，不做替换，仍由质量检查提示。字数按显示长度算，{DOCTOR} 算 2 个字，替换不会让文本超过上限。
- **长度上限留余量**：prompt 里的建议长度不变，校验的上限放宽：topic 30、summary 400、beat 40、episode 300、stance 60（建议值分别是 20、300、25、200、40）。超过建议值但没超过上限的，只在报告里记为"超过建议长度"。实体名允许单字，W、陈、年都是真实的角色名。

## 与规格不同的地方

- **`events` 表多了整数主键 `rid`**，`event_id` 改为 `NOT NULL UNIQUE`。全文检索按 rowid 关联，文本主键表的 rowid 在 `VACUUM` 后可能改变，会让全文索引错位。
- **抽取出的实体先按别名查找**：名字已经是某个实体的别名（例如种子里的英文代号），就复用那个实体，不再新建。
- **不用 `RETURNING`**：规格要求 SQLite ≥ 3.34，`RETURNING` 需要 3.35。
- **测试用 unittest**：规格 B10 写的是 pytest，但本仓库环境没有 pytest，`run_realtime_dev.py --self-test` 用 unittest 发现测试。`tests/test_canon.py` 按现有测试的写法编写；`tests/` 按本仓库的 `.gitignore` 只留在本地。
- **`SimpleLLMClient`** 增加可选参数 `timeout`（默认仍是 60 秒）和 `temperature`（默认仍是 0.1，裁判用 0），并把接口返回的 `usage` 带回来，用于统计 token。它固定发送 `temperature: 0.1`；部分推理模型只接受默认的 temperature，会返回 400，基准里记为接口失败，真实运行前先用一个场景试通。接口返回错误时，异常信息里带上响应体的前 300 字，方便看到网关给出的原因。
- **`extract_scene` 和 `Importer` 多了可选的 `observer`**：每次模型调用后收到一条记录（块号、第几次、耗时、token、校验问题、原始回复），基准用它统计；正式导入不传。
