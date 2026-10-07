# configs

Moirai 的 Hydra 配置。`src/main.py` 组合 `base.yaml` 后按 `experiments.runner.id` 运行一个任务；`src/tools/` 下的脚本直接运行时组合同一份配置；AstrBot 插件启动时只读其中的 `canon/` 和 `data/`。

| 配置组 | 内容 |
|---|---|
| `models/` | 一个文件一个模型：`type` 是家族（lmstudio、deepseek、kcl、openai），`backend.api_key_env` 只写环境变量名，key 从不写进文件 |
| `data/` | 数据集：路径、样本清单，以及只属于它的角色档案、时间锚点、抽取收件人和年表标签 |
| `experiments/` | 任务：`runner.id` 选择运行什么，`args` 原样传给对应工具的命令行 |
| `retrieval/` | 普通记忆和 canon 共用的 embedding 与 rerank 入口 |
| `canon/` | canon 机制的全部超参数；`src/core/canon/settings.py` 按类型校验，未知键会报错 |
| `canon_tools/` | canon 开发工具的运行设置：模型家族、并发、超时、基线运行与单价 |
| `realtime/` | 本地回放的抽取模式与 TypeSafe 设置 |

常用写法（在插件根目录下）：

```bash
python src/main.py --cfg job                                   # 只打印组合结果
python src/main.py experiments=canon_build                     # 全库续跑 canon 抽取
python src/main.py experiments=canon_bench models=lmstudio_gemma4_26b canon_tools.concurrency=1
python src/main.py experiments=realtime_replay 'experiments.args=[--self-test,--quiet]'
python src/main.py -cd ~/runs -cn my_run                       # ~/runs/my_run.yaml 的 defaults 先列 base
MOIRAI_CONFIG_OVERRIDES="canon.recall.turn_budget=1500" python src/tools/canon_chat.py --dry-run --question "…"
```

需要的环境变量：`KCL_HUB_API_KEY`（KCL hub）、`DEEPSEEK_API_KEY`、`OPENAI_API_KEY`、`TYPESAFE_API_KEY`，按所用模型设置；`MOIRAI_RETRIEVAL_API_KEY` 可以单独给 embedding 与 rerank。LM Studio 的主机地址由 `FREETOKEN_HOST` 覆盖。

这里不放运行记录、数据库或密钥；运行输出写在 `paths.output_root`（默认插件根目录的 `.dev_data/`）。
