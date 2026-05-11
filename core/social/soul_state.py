"""Soul Layer: short-term emotional state machine.

Four energy dimensions, each in [-20, +20], updated each conversation turn
with tanh-elastic clamping and exponential decay toward neutral.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import SoulConfig


@dataclass
class SoulState:
    recall_depth: float = 0.0       # drives memory retrieval depth
    impression_depth: float = 0.0   # attention toward social relationships
    expression_desire: float = 0.0  # verbosity / detail level
    creativity: float = 0.0         # metaphor use / topic exploration


def apply_tanh_elastic(old_val: float, delta: float) -> float:
    """Soft-ceiling update: keeps result within [-20, +20]."""
    return math.tanh((old_val + delta) / 20.0) * 20.0


def apply_decay(state: SoulState, decay_rate: float) -> SoulState:
    """Decay all dimensions toward zero by (1 - decay_rate) each turn."""
    factor = 1.0 - decay_rate
    return SoulState(
        recall_depth=state.recall_depth * factor,
        impression_depth=state.impression_depth * factor,
        expression_desire=state.expression_desire * factor,
        creativity=state.creativity * factor,
    )


def from_config(cfg: SoulConfig) -> SoulState:
    return SoulState(
        recall_depth=cfg.recall_depth_init,
        impression_depth=cfg.impression_depth_init,
        expression_desire=cfg.expression_desire_init,
        creativity=cfg.creativity_init,
    )


_THRESHOLD = 1.0  # minimum absolute value to bother mentioning in prompt


def format_soul_for_prompt(state: SoulState) -> str:
    """Return a brief system-prompt segment describing the bot's current state.

    Only dimensions that deviate meaningfully from neutral are included.
    Returns empty string when all dimensions are near zero.
    """
    parts: list[str] = []
    if abs(state.recall_depth) >= _THRESHOLD:
        level = "偏高" if state.recall_depth > 0 else "偏低"
        parts.append(f"记忆检索驱动 {state.recall_depth:+.1f}/20（{level}）")
    if abs(state.impression_depth) >= _THRESHOLD:
        level = "偏高" if state.impression_depth > 0 else "偏低"
        parts.append(f"社交关注度 {state.impression_depth:+.1f}/20（{level}）")
    if abs(state.expression_desire) >= _THRESHOLD:
        level = "偏高" if state.expression_desire > 0 else "偏低"
        parts.append(f"表达欲 {state.expression_desire:+.1f}/20（{level}）")
    if abs(state.creativity) >= _THRESHOLD:
        level = "偏高" if state.creativity > 0 else "偏低"
        parts.append(f"创意度 {state.creativity:+.1f}/20（{level}）")
    if not parts:
        return ""
    lines = ["[当前情绪状态]\n（以下状态参数供参考，影响回复风格，不要在回复中提及）"] + [f"- {p}" for p in parts]
    return "\n".join(lines)
