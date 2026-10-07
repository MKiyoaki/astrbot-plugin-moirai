"""Moirai 实验与工具的 Hydra 入口：按 experiments.runner.id 运行一个任务。

用法（在插件根目录下）：
    python src/main.py                                         # 默认组合：canon 终端试聊
    python src/main.py experiments=canon_build                 # 全库续跑 canon 抽取
    python src/main.py experiments=canon_bench models=lmstudio_gemma4_26b
    python src/main.py experiments=realtime_replay 'experiments.args=[--self-test,--quiet]'
    python src/main.py -cd ~/runs -cn my_run                   # 读 ~/runs/my_run.yaml（其 defaults 先列 base）
    python src/main.py --cfg job                               # 只打印组合结果，不运行

AstrBot 插件的入口是插件根目录的 main.py，与这里无关。
"""
from __future__ import annotations

import asyncio
import importlib
import sys
from typing import Callable

import hydra
from omegaconf import DictConfig

from core.utils.config_utils import install, register_resolvers

register_resolvers()


def _tool(module: str, prog: str, *, call: str = "main", pass_argv: bool = False) -> Callable[[DictConfig], int]:
    def run(cfg: DictConfig) -> int:
        args = [str(arg) for arg in cfg.experiments.get("args", [])]
        sys.argv = [prog, *args]
        entry = getattr(importlib.import_module(module), call)
        result = entry(args) if pass_argv else entry()
        if asyncio.iscoroutine(result):
            result = asyncio.run(result)
        return int(result or 0)
    return run


def _canon_data(command: str) -> Callable[[DictConfig], int]:
    def run(cfg: DictConfig) -> int:
        from tools import canon_data as cli
        return int(cli.main([command, *(str(arg) for arg in cfg.experiments.get("args", []))]) or 0)
    return run


RUNNERS: dict[str, Callable[[DictConfig], int]] = {
    "canon-chat": _tool("tools.canon_chat", "canon_chat.py", pass_argv=True),
    "canon-build": _tool("tools.canon_dev", "canon_dev.py"),
    "canon-bench": _tool("tools.canon_dev", "canon_dev.py"),
    "canon-judge": _tool("tools.canon_dev", "canon_dev.py"),
    "canon-archive-import": _canon_data("archive-import"),
    "canon-facts-apply": _canon_data("facts-apply"),
    "canon-calendar-apply": _canon_data("calendar-apply"),
    "realtime-replay": _tool("tools.realtime_dev", "realtime_dev.py", call="run_cli"),
    "webui-dev": _tool("tools.webui_dev", "webui_dev.py"),
}


@hydra.main(version_base=None, config_path="../configs", config_name="base")
def main(cfg: DictConfig) -> int:
    runner = RUNNERS.get(cfg.experiments.runner.id)
    if runner is None:
        raise SystemExit(f"unknown runner {cfg.experiments.runner.id!r}; known: {', '.join(RUNNERS)}")
    install(cfg)
    return runner(cfg)


if __name__ == "__main__":
    sys.exit(main())
