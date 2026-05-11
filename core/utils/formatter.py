"""Format retrieved events and persona data into injectable prompt content.

Greedy fill: sort by salience descending, add entries until token_budget
is exhausted. Conservative token estimate: len(text) // 2 (handles
Chinese where 1 char ≈ 1 token).
"""
from __future__ import annotations

import json
import time
import uuid
from typing import TYPE_CHECKING

from ..config import FAKE_TOOL_CALL_ID_PREFIX
from ..domain.models import Event

if TYPE_CHECKING:
    from ..domain.models import Persona

_TOKEN_BUDGET = 800
_CHARS_PER_TOKEN = 2


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _time_label(end_time: float, now: float) -> str:
    age = now - end_time
    if age < 3600:
        return f"{max(1, int(age / 60))}分钟前"
    if age < 86400:
        return f"{int(age / 3600)}小时前"
    return f"{int(age / 86400)}天前"


def format_events_for_prompt(
    events: list[Event],
    *,
    token_budget: int = _TOKEN_BUDGET,
    now: float | None = None,
) -> str:
    """Return the memory body string (no wrapper), or empty string if events is empty."""
    if not events:
        return ""
    if now is None:
        now = time.time()

    header = "## 相关历史记忆\n"
    budget_used = _estimate_tokens(header)
    lines: list[str] = []

    for event in sorted(events, key=lambda e: e.salience, reverse=True):
        label = _time_label(event.end_time, now)
        entry = f"- [{label}] {event.topic}"
        if event.chat_content_tags:
            entry += "（" + "、".join(event.chat_content_tags) + "）"
        cost = _estimate_tokens(entry + "\n")
        if budget_used + cost > token_budget:
            break
        lines.append(entry)
        budget_used += cost

    if not lines:
        return ""

    return header + "\n".join(lines)


_DIM_NAMES = {"O": "开放性", "C": "尽责性", "E": "外向性", "A": "宜人性", "N": "神经质"}


def format_persona_for_prompt(persona: Persona) -> str:
    """Return a brief system-prompt segment with the user's OCEAN personality profile.

    Injects personality data as a soft stylistic hint — the model should adjust
    its tone accordingly but must NOT mention or reference this data in its output.
    Returns empty string when no BigFive data is available.
    """
    attrs = persona.persona_attrs
    bf: dict = attrs.get("big_five", {})
    if not bf:
        return ""

    evidence = attrs.get("big_five_evidence", {})
    name = persona.primary_name or "用户"
    lines = [
        f"[用户画像参考] {name} 的性格倾向（据此调整措辞风格，不要在回复中提及）："
    ]
    for dim in ["O", "C", "E", "A", "N"]:
        val = bf.get(dim)
        if val is None:
            continue
        pct = round((float(val) + 1.0) / 2.0 * 100)
        label = _DIM_NAMES[dim]
        ev = evidence.get(dim, "") if isinstance(evidence, dict) else ""
        line = f"- {label} {pct}%"
        if ev:
            line += f"：{ev[:60]}"
        lines.append(line)

    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def format_events_for_fake_tool_call(
    events: list[Event],
    query: str,
    *,
    token_budget: int = _TOKEN_BUDGET,
    now: float | None = None,
) -> list[dict]:
    """Return two OpenAI-format messages simulating a tool call result.

    Message 1 (assistant): announces a recall_memory tool call.
    Message 2 (tool):      the memory content as tool output.

    Returns empty list if no content to inject.
    """
    content = format_events_for_prompt(events, token_budget=token_budget, now=now)
    if not content:
        return []
    tool_call_id = f"{FAKE_TOOL_CALL_ID_PREFIX}{uuid.uuid4().hex[:8]}"
    return [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": "recall_memory",
                        "arguments": json.dumps({"query": query}, ensure_ascii=False),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        },
    ]
