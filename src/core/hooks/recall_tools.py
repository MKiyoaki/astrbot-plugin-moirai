"""回忆工具的注册表：每个工具登记给模型的函数定义、这一轮是否提供，以及调用时由哪一轮的哪个方法处理。

一轮对话只遍历注册表：提供哪些工具、调用分派到哪里，都由登记的条目决定，新工具不必改动轮次代码。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class RecallTool:
    name: str
    schema: Callable[[Any], dict]
    handle: Callable[[Any, dict], str]
    offered: Callable[[Any], bool] = lambda turn: True


_REGISTRY: dict[str, RecallTool] = {}


def register(tool: RecallTool) -> RecallTool:
    """同一个处理方法重新登记（模块被重新导入）时替换旧条目；不同方法用了同一个名字则报错。"""
    existing = _REGISTRY.get(tool.name)
    if existing is not None and existing.handle.__qualname__ != tool.handle.__qualname__:
        raise ValueError(f"回忆工具 {tool.name!r} 已经登记给 {existing.handle.__qualname__}")
    _REGISTRY[tool.name] = tool
    return tool


def registered() -> tuple[RecallTool, ...]:
    return tuple(_REGISTRY.values())
