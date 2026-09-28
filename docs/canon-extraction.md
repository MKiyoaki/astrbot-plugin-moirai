# canon 抽取与基准

本文件说明怎样把 story_pack 抽取成 `canon.sqlite`：命令、全库构建、增量规则、校验前的本地修正，以及抽取基准和评测框架。各版抽取 prompt 的改动和试跑结果见 [canon 抽取版本记录](canon-extraction-history.md)；整体状态见 [canon：原作剧情记忆](canon.md)。

## 命令行

在插件根目录下运行，API key 只从环境变量读取：抽取用 `CANON_API_KEY`，裁判用 `CANON_JUDGE_API_KEY`（没有就用 `CANON_API_KEY`）：

```bash
python -m core.canon.cli import --pack <story_pack> --db <canon.sqlite> \
    --api-url <OpenAI 兼容地址> --model <模型> [--only samples/20.txt] [--concurrency 2] [--timeout 300] [--embed]
python -m core.canon.cli status --db <canon.sqlite>
python -m core.canon.cli dump --db <canon.sqlite> --only samples/20.txt [--out review.html]
python -m core.canon.cli bench --pack <story_pack> (--only <清单> | --scene <key> ...) \
    (--estimate | --replay <目录> | --api-url <地址> --model <模型>) \
    [--probes <探针文件>] [--baseline <运行目录>] [--repeats N] [--price-in <每百万输入 token 单价> --price-out <输出单价>]
python -m core.canon.cli compare <运行目录> <运行目录> [...]
python -m core.canon.cli judge --run <运行目录> --pack <story_pack> --api-url <地址> --model <模型> [--repeats 3] [--labels <人工标注>]
```

`--embed` 给事件编码向量，用的是 Moirai 共享的 embedding 入口和 `run_config.py` 的 `RETRIEVAL_*` 配置（本地模型、KCL 或其他 OpenAI 兼容服务），和普通记忆同一套代码；canon 不再单独加载本地模型。这样写入的是库内的 `event_vec` 表；终端试聊和检索评测不读它，而是读构建目录旁的派生索引（见 [canon 终端试聊](canon-terminal.md) 的“检索”一节）。正式 Bot 路径用哪一套向量尚未决定，见 [canon 运行时结构](canon-runtime-architecture.md)。

`dump` 生成本地 HTML 审阅页：顶部选择场景，左边是带 L 编号的原文，右边按事件标题、渠道和行范围列出可折叠的摘要与细节；事件证据、第一人称摘要、认知和事件关系按需展开。鼠标移到事件上会高亮它的证据行，点击蓝色行号可定位原文。

## 全库 canon 构建

`moirai canon build` 从当前 story_pack 的全部场景增量构建 `.dev_data/canon/<当前 prompt 版本>/all/build/canon.sqlite`（现在是 `v10/all/build/`），先运行 V10 事件抽取，再运行分块时间事实候选抽取，产出同目录的候选 JSONL、审阅包、失败报告和逐场景 `review.html`。中断或失败后重跑相同命令，成功场景和事实分块命中数据库缓存。`moirai canon estimate all` 不调用模型，可先核对场景规模。真实接口的 `moirai canon run` 默认在当前版本事件基准后自动抽取时间事实候选，结果写入同一份 summary.json / report.md；`--no-facts` 才跳过。`moirai canon run all` 则生成一次性全量 benchmark，并自动追加事实候选；一次性基准不用于中断后的事件阶段续跑。

候选只属于待审阅数据。完整 618 场景也不会凭导出顺序生成世界时间先后、事实有效期终点或“当前”状态；必须核实原文、批准候选及有证据的时间关系。`moirai canon test --db .dev_data/canon/v10/all/build/canon.sqlite` 可读该全量工作库，但在审阅前时间敏感状态仍会判不确定。详见 [canon 时间线与事实有效期](canon-temporal-facts.md)。

> **续跑前先确认模型。** 事件缓存按 `(scene_key, scene_hash, prompt_version)` 命中，与模型无关；事实缓存 `fact_extractions` 的主键还包含模型。`run_canon_dev.py` 的模型类型可由 `CANON_MODEL_TYPE` 或 `MODEL_TYPE` 指定，但模型名只从本机 `run_config.py` 读取（KCL 时是 `KCL_MODEL`），没有环境变量覆盖。换了模型再续跑，事件阶段照常命中缓存，事实阶段却会全部重抽。2026-09-25 就因续跑前没核对模型，在 `arc:chat` 下重抽了约 215 个场景的事实候选。只想补跑个别场景时，用 `python -m core.canon.cli import ... --model <模型> --facts --only <场景>`：`--only` 只作用于事件阶段；事实阶段仍覆盖全部场景，其余场景只有在同一模型下才会命中缓存。

> **补跑 V11 场景的注意点。** `core.canon.cli` 不读 `run_config.py`：不设环境变量 `CANON_PROMPT_VERSION=canon-extract-v11` 时它按代码默认的 V10 抽取，事实阶段也随之退回 `canon-facts-v2`；它也不像 `build` 那样用 `temperature=0`，并且不保存失败回复。2026-09-28 的 V11 补跑改为导入 `run_canon_dev.py` 取得同一配置，再用带 observer 的 `Importer(only=…)` 把每次调用的原始回复写进构建目录的 `patch-*/attempts.jsonl`，事实阶段用 `run_fact_pipeline` 覆盖全部场景键（成功场景和分块走缓存）。`build` 本身同样不保存失败回复，出现连续失败时只能重调复现。
>
> 单块场景持续撞上网关 300 秒上限（HTTP 502 `cURL error 28`）时，重试不会改变结果：`level_main_07-16_end`（渲染后约 1.2 万字，低于 2 万字的分块阈值）以单块连续 6 次超时，把 `CHUNK_TRIGGER`/`CHUNK_LIMIT` 临时降到 7000 后按两块（161 行 + 242 行）各 32 秒、50 秒一次通过。分块走的是长场景的正常路径，缓存键不含分块方式。

## 增量规则

一个场景算已完成，要同时满足：库里的 `scene_hash` 等于包里的，且有当前 `PROMPT_VERSION` 下的成功抽取。场景行、台词行和全部抽取结果在同一个事务里写入，所以 hash 变化、prompt 版本变化、上次失败、上次中途中断的场景都会被重新处理，而已有成功缓存的场景不会再调用 API。

prompt 每升一版，旧版本的缓存都不再命中：试跑库 `.dev_data/canon/v1/import/canon.sqlite` 里的 20 条 v1 缓存和 v2 的单场景运行，仍然可以作为 `--replay` 的来源和对比基线。

时间事实候选的缓存另存在 `fact_extractions`，按 `(scene_key, scene_hash, prompt_version, model)` 命中：同一 prompt 版本换了模型不会命中，见上面“全库 canon 构建”的提示。

## 校验前的本地修正

这几种问题都在真实接口的试跑里出现过，而且都不值得整次重试。每次重试要重新生成整个场景，在 arc:lite 上一次要 1–1.6 万 token。所以先在本地修正，修正后照常经过 10 条校验。每次调用修了几处、丢了几条都记在 `results.jsonl`，报告总览里有合计。规格的 B4 也记录了这些修正。

- **未转义的引号**：模型常在 JSON 字符串里直接用英文双引号引用原话，比如 `"乙说"好"。"`，整段 JSON 因此解析失败。`parse_json` 直接解析失败时，把字符串内部后面不跟 `,` `:` `}` `]` 的引号改成 `\"` 再解析一次；能直接解析的 JSON 不做改动。引号后面紧跟半角逗号或冒号时判断不了，仍然按失败重试，重试的问题清单会提示引号的写法。
- **并列的字符串值**：arc:chat 常把证据数组写成 `"evidence":"L20","L25"`，这是 V10/V11 在 arc:chat 上最常见的 JSON 失败形态（保存下来的 29 次解析失败里 17 次）。引号修复后仍解析不了时，`repair_value_lists` 把键的冒号后面并列的字符串包成数组；后一个字符串后面跟着冒号时它是下一个键，不合并。修复处数与引号修复合并记入 `quote_fixes`。
- **嵌在事件里的视角**：arc:chat 有时不写顶层 `views`，而把每条视角作为对象写进对应事件的 `views` 字段，内容和 `event` 引用都正确。顶层没有 `views`，且每条嵌套视角都没写 `event` 或写的正是所在事件的 id 时，`normalize_output` 把它们提升到顶层；有一条对不上就原样交给校验。
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

## 抽取基准

`bench` 每次运行都新建一个运行目录和独立的 `canon.sqlite`，不读取也不写入正式库或试跑库的抽取缓存，走的是和正式导入完全相同的 `Importer → extract_scene → CanonStore` 路径。运行目录按抽取 prompt 版本、样本和运行方式分层放在 `.dev_data/canon/` 下：`v<N>/<样本>/api/` 是真实接口，`v<N>/<样本>/replay/` 是回放（放在被回放数据所属的版本下），`--repeats` 的一组运行在 `v<N>/<样本>/repeats/`（外加 `stability.md`）；外部模型（subagent）的原始输出在 `v<N>/sources/`，试聊用的数据库副本在 `v<N>/chat/`，全库构建在 `v<N>/all/build/`，v1 最早导入的库在 `v1/import/`。2026-09-24 从旧的 `bench/api`、`bench/replay` 布局迁移过来，运行目录名不变，新旧路径对照记在 `.dev_data/canon/moves-20260924.json`。`--out` 可以指定别的上级目录，这时不按版本和样本分层。

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
| `report.md` | 事件指标与时间事实候选阶段的完成数、失败数、调用量、耗时及审阅产物；另有探针、质量检查和逐场景表 |
| `summary.json` | 两阶段数字及事实阶段状态，可作为下一次运行的 `--baseline` |
| `results.jsonl` | 每个场景一行：状态、块数、每次调用的耗时 / token / 校验问题、质量指标、自动检查结果 |
| `review.html` | 原文、事件和本轮待审阅时间事实候选；候选可点击证据行定位 |
| `failures/` | 校验不通过的原始回复，每次调用一个文件 |
| `judge.jsonl` | 跑过 `judge` 才有：逐事件的裁判结果（含每次重复的判断） |
| `console.log`、`judge.log` | 用 `run_canon_dev.py` 跑才有：运行和裁判时的逐次调用记录 |
| `canon.sqlite` | 这次运行的库，可以用 `status` / `dump` 查看，也可以作为 `--replay` 或 `compare` 的输入 |
| `facts-candidates.jsonl` / `facts-candidates.review.json` / `facts-candidates.report.json` | 真实接口运行默认生成：待审阅候选、可编辑审阅包和失败报告；回放模式不调用事实模型 |

### 开发工具 run_canon_dev.py

插件根目录下的 `run_canon_dev.py` 用来手动跑基准，写法和 `run_realtime_dev.py` 一样：模型、地址和 key 取自本机的 `run_config.py`（`MODEL_TYPE`，可以用 `CANON_MODEL_TYPE`、`CANON_JUDGE_MODEL_TYPE` 单独指定），story_pack、探针、场景清单、基线和单价都在 `run_config.py` 的 `CANON_*` 里设置，模板见 `run_config.py.example`。它直接调用 `run_bench` 和 `judge_into`，所以结果和命令行的 `bench` / `judge` 完全一样。

```bash
python run_canon_dev.py                          # 列出已有的运行和主要指标
python run_canon_dev.py estimate [20|100|all]    # 估算，不调用接口
python run_canon_dev.py build                    # 全库事件与事实候选续跑，并生成 review.html
python run_canon_dev.py run [20|100|all]         # 真实接口：事件与时间事实候选；开始前确认（-y 跳过），样本默认 CANON_SCENES
python run_canon_dev.py run 20 --replay pilot    # 回放 v1 的 Luna 试跑
python run_canon_dev.py run --repeats 3          # 重测信度
python run_canon_dev.py judge [运行]              # LLM 裁判，默认最近一次真实接口的运行；开始前确认
python run_canon_dev.py compare <运行> <运行> [...]
python run_canon_dev.py open [运行] [--report]    # 用浏览器打开审阅页或报告
```

真实接口的 `run` 默认抽取时间事实候选；只测 V7 事件时加 `--no-facts`。每个事件分块或事实分块连续失败最多 4 次，成功即停止重试；失败场景保留原因，整批继续。样本是 story_pack 的 `samples/` 里的场景清单，由 Arknights-Texts 的 `config/samples.json` 定义：`20` 是分层抽样，`100` 是整块连贯的章节和活动（主线第 0 章、第 4–6 章、「如我所见」「长夜临光」和三篇密录），`all` 是全部场景；`--scenes` 可以改用别的清单文件。`<运行>` 可以写目录名、名字里的一段、路径，或 `latest` / `latest-api` / `latest-replay`；回放来源、基线和 `compare` 还可以写 `pilot`。

运行时每次模型调用打一行（场景、第几次、耗时、token、校验问题和原始回复文件），每个场景结束打一行；终端底部的状态行每秒刷新，显示用时、完成数、预计剩余时间、累计 token 和费用，以及正在进行的调用各自等了多久。输出不是终端时，状态改为每 30 秒打一行。这些行同时写进日志：正常结束后移到运行目录的 `console.log`（裁判是 `judge.log`），中断时留在 `.dev_data/canon/logs/`。`compare` 的结果写到 `.dev_data/canon/compare/`。Ctrl+C 中断后，没跑完的运行目录在列表里标为"未完成"，已经花掉的调用不会重放。

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
- 有连续行不在任何事件里、事件范围重叠：v4 起这两条是校验规则 9、10，这里的提示用来看 v3 及更早的回放

另外还会统计：
- 渠道分布
- concept 类实体数
- 用 ta 指代博士的次数
- 她的台词被引用的比例（按精确引用算，按台词密度分段）
- 边的数量
- 事件覆盖的场景行比例，以及覆盖不到 90% 的场景数

"她"指代博士不做机械检查，因为摘要里的"她"几乎都指目标角色本人。

### 这几条路径只能用基准跑

| 路径 | 怎么跑 |
|---|---|
| 真实的 HTTP 调用、解析、落库 | `--replay pilot`（v1 的 Luna 试跑），零成本 |
| 真实模型的首次通过率、重试、耗时、token | `--api-url --model --only samples/20.txt`，会产生费用 |
| 长场景切块 | 在真实接口的运行里加 `--scene obt/main/level_st_13-03`（约 2.1 万字，切成 2 块） |
| AstrBot provider 的调用路径 | M2（B8、B9）接入后才有 |

> **数据外发**：规格 B11 规定剧情文本只在抽取时发给用户配置的接口。`judge` 会把被引用的原文行另外发给裁判接口，所以默认不运行，只在显式调用时执行。
