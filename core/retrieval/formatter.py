"""Format retrieved events into a system-prompt-injectable string.

Greedy fill: sort by salience descending, add entries until token_budget
is exhausted. Conservative token estimate: len(text) // 2 (handles
Chinese where 1 char ≈ 1 token).
"""
from __future__ import annotations

import time

from ..domain.models import Event

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
    """Return a prompt segment string, or empty string if events is empty."""
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
