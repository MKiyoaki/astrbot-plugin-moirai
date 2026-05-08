"""Prompt templates for LLM event extraction."""
from __future__ import annotations

import math

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..boundary.window import MessageWindow


def build_user_prompt(window: MessageWindow, max_messages: int = 20) -> str:
    """Format the conversation window into a user prompt."""
    messages = window.messages[-max_messages:]
    duration_min = math.ceil(window.duration_seconds / 60)

    # Map uids to short readable labels for the prompt
    uid_label: dict[str, str] = {}
    counter = 1
    for m in messages:
        if m.uid not in uid_label:
            name = m.display_name.strip() if m.display_name.strip() else f"用户{counter}"
            uid_label[m.uid] = name
            counter += 1

    lines = [
        f"对话记录（共{len(messages)}条消息，时间跨度约{duration_min}分钟）：",
        "",
    ]
    for i, m in enumerate(messages):
        label = uid_label[m.uid]
        lines.append(f"[{i}] {label}: {m.text}")

    return "\n".join(lines)
