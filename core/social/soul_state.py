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

    # creativity: time spread + salience variance + tag diversity
    if events:
        if len(events) >= 2:
            times = [getattr(e, "end_time", 0.0) for e in events]
            spread_days = (max(times) - min(times)) / 86400.0
            # 7 days to reach max spread contribution (was 30 days, too conservative)
            spread_bonus = min(spread_days / 7.0, 1.0) * 2.0
        else:
            spread_bonus = 0.0

        saliences = [getattr(e, "salience", 0.5) for e in events]
        if len(saliences) >= 2:
            mean_s = sum(saliences) / len(saliences)
            variance = sum((s - mean_s) ** 2 for s in saliences) / len(saliences)
            # variance of 0.08 reaches max; high contrast between mundane/significant events
            variance_bonus = min(variance / 0.08, 1.0) * 1.5
        else:
            variance_bonus = 0.0

        all_tags: set[str] = set()
        for e in events:
            all_tags.update(getattr(e, "chat_content_tags", []) or [])
        # 5 unique tags across recalled events reaches max
        tag_bonus = min(len(all_tags) / 5.0, 1.0) * 1.5

        delta_creativity = spread_bonus + variance_bonus + tag_bonus
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


_LOW_THRESHOLD = 1.0   # minimum absolute value to produce any instruction
_HIGH_THRESHOLD = 7.0  # threshold for stronger behavioral phrasing

# Behavioral instructions keyed by (dimension, direction_strength).
# Tell the LLM *what to do*, not what a number means.
_INSTRUCTIONS: dict[str, dict[str, str]] = {
    "recall_depth": {
        "high_strong": "回忆感较强，回复时可主动联系过去的经历或对话",
        "high_mild":   "可适当联系过去经历，不必刻意引用",
        "low_mild":    "专注当下话题，不必主动翻找旧事",
        "low_strong":  "专注当下，避免主动引入历史经历",
    },
    "impression_depth": {
        "high_strong": "高度关注当前对话者，留意情绪细节，回复可体现察觉",
        "high_mild":   "对当前对话者保持一定关注",
        "low_mild":    "保持基本礼貌，不必过度关注对方反应",
        "low_strong":  "当前社交投入偏低，简短应对即可",
    },
    "expression_desire": {
        "high_strong": "表达欲强，可主动展开话题，回复可以详细",
        "high_mild":   "表达欲稍强，回复可适当延伸",
        "low_mild":    "不太想多说，回复简短即可",
        "low_strong":  "表达欲极低，回复尽量精简",
    },
    "creativity": {
        "high_strong": "思维活跃，可使用比喻或联想，话题可适度跳跃",
        "high_mild":   "思维略显发散，可适度使用类比",
        "low_mild":    "保持直白清晰的表达",
        "low_strong":  "专注直接表达，避免发散",
    },
}


def _instruction(dim: str, val: float) -> str | None:
    if abs(val) < _LOW_THRESHOLD:
        return None
    direction = "high" if val > 0 else "low"
    strength = "strong" if abs(val) >= _HIGH_THRESHOLD else "mild"
    return _INSTRUCTIONS[dim][f"{direction}_{strength}"]


def format_soul_for_prompt(state: SoulState) -> str:
    """Return a system-prompt segment with concrete behavioral instructions.

    Only dimensions that deviate meaningfully from neutral are included.
    Returns empty string when all dimensions are near zero.
    """
    parts: list[str] = []
    for dim, val in (
        ("recall_depth", state.recall_depth),
        ("impression_depth", state.impression_depth),
        ("expression_desire", state.expression_desire),
        ("creativity", state.creativity),
    ):
        inst = _instruction(dim, val)
        if inst:
            parts.append(inst)
    if not parts:
        return ""
    lines = ["[当前心理状态]\n（参考以下提示调整回复风格，勿在回复中直接提及）"] + [f"- {p}" for p in parts]
    return "\n".join(lines)
