"""Soul Layer: short-term emotional state machine.

Four energy dimensions, each in [-20, +20], updated each conversation turn
with tanh-elastic clamping and exponential decay toward neutral.

Axes are driven by real signals rather than being static knobs:
  recall_depth      ← event count × avg salience  (cognitive engagement)
  expression_desire ← IPC benevolence              (relational warmth → verbosity)
  impression_depth  ← relation_count × power       (social investment)
  creativity        ← event time-spread + type mix (recall breadth → exploration)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

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


def update_from_signals(
    state: SoulState,
    *,
    decay_rate: float,
    events: list[Any],
    benevolence: float = 0.0,
    power: float = 0.0,
    relation_count: int = 0,
) -> SoulState:
    """Decay then boost all four axes from concrete signals.

    Args:
        state:          Current soul state.
        decay_rate:     Fraction to decay each axis toward 0 before boosting.
        events:         Recalled events (need .salience, .event_type, .end_time).
        benevolence:    Avg IPC benevolence from relation_debug [-1, 1].
        power:          Avg IPC power from relation_debug [-1, 1].
        relation_count: Number of impression records available.
    """
    state = apply_decay(state, decay_rate)

    # recall_depth: count × weighted salience
    if events:
        avg_salience = sum(getattr(e, "salience", 0.5) for e in events) / len(events)
        delta_recall = min(5.0, len(events) * 0.5 * (0.5 + avg_salience))
    else:
        delta_recall = 0.0

    # expression_desire: IPC benevolence → relational warmth
    delta_expression = benevolence * 3.0

    # impression_depth: relation_count × power bonus
    capped_count = min(relation_count, 5)
    delta_impression = capped_count * 0.4 * (1.0 + power * 0.5)

    # creativity: time spread of recalled events
    if len(events) >= 2:
        times = [getattr(e, "end_time", 0.0) for e in events]
        spread_days = (max(times) - min(times)) / 86400.0
        delta_creativity = min(spread_days / 30.0, 1.0) * 0.8
    else:
        delta_creativity = 0.0

    return SoulState(
        recall_depth=apply_tanh_elastic(state.recall_depth, delta_recall),
        impression_depth=apply_tanh_elastic(state.impression_depth, delta_impression),
        expression_desire=apply_tanh_elastic(state.expression_desire, delta_expression),
        creativity=apply_tanh_elastic(state.creativity, delta_creativity),
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
