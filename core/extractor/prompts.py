"""Prompt templates for LLM event extraction."""
from __future__ import annotations

import math

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..boundary.window import MessageWindow, RawMessage


def build_user_prompt(
    window: MessageWindow,
    max_messages: int = 20,
    bot_persona_desc: str | None = None,
) -> str:
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

    if bot_persona_desc:
        persona_line = (
            f"[Bot 视角人格] {bot_persona_desc}\n"
            f"注意：请在 summary 每个小话题三元组末尾加上 [Eval] 字段，以上述人格视角对该话题做一句话评价。\n\n"
        )
    else:
        persona_line = ""
    lines = [
        f"{persona_line}对话记录（共{len(messages)}条消息，时间跨度约{duration_min}分钟）：",
        "",
    ]
    for i, m in enumerate(messages):
        label = uid_label[m.uid]
        lines.append(f"[{i}] {label}: {m.text}")

    return "\n".join(lines)


def build_distillation_prompt(
    messages: list[RawMessage],
    bot_persona_desc: str | None = None,
) -> str:
    """Build a prompt for summarizing a pre-grouped cluster of messages."""
    if bot_persona_desc:
        persona_line = (
            f"[Bot 视角人格] {bot_persona_desc}\n"
            f"注意：请在 summary 每个小话题三元组末尾加上 [Eval] 字段，以上述人格视角对该话题做一句话评价。\n\n"
        )
    else:
        persona_line = ""
    lines = [
        f"{persona_line}以下是一组语义高度相关的对话记录（共{len(messages)}条）：",
        "",
    ]
    for i, m in enumerate(messages):
        lines.append(f"[{i}] {m.display_name or m.uid}: {m.text}")

    lines.append(
        "\n请为这段对话提炼结构化信息，输出单个 JSON 对象，包含以下字段：\n"
        '{"topic": "核心主题(≤30字)", "summary": "摘要", '
        '"chat_content_tags": ["标签1", "标签2"], "salience": 0.5, "confidence": 0.8, "inherit": false}'
    )
    return "\n".join(lines)
