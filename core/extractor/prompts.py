"""Prompt templates for LLM event extraction."""
from __future__ import annotations

import math

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..boundary.window import MessageWindow, RawMessage


def _assign_unique_labels(messages: list) -> dict[str, str]:
    """Build uid → label map, disambiguating duplicate display names with #2/#3 suffix."""
    uid_label: dict[str, str] = {}
    used_labels: set[str] = set()
    counter = 1
    for m in messages:
        if m.uid in uid_label:
            continue
        base = m.display_name.strip() if m.display_name.strip() else f"用户{counter}"
        label = base
        suffix = 2
        while label in used_labels:
            label = f"{base}#{suffix}"
            suffix += 1
        uid_label[m.uid] = label
        used_labels.add(label)
        counter += 1
    return uid_label


def build_user_prompt(
    window: MessageWindow,
    max_messages: int = 20,
    bot_persona_desc: str | None = None,
    existing_tags: list[str] | None = None,
) -> str:
    """Format the conversation window into a user prompt."""
    messages = window.messages[-max_messages:]
    duration_min = math.ceil(window.duration_seconds / 60)

    uid_label = _assign_unique_labels(messages)

    header_parts = []
    if bot_persona_desc:
        header_parts.append(
            f"[Bot 视角人格] {bot_persona_desc}\n"
            f"注意：请在 summary 每个小话题三元组末尾加上 [Eval] 字段，以上述人格视角对该话题做一句话评价。"
        )

    if existing_tags:
        tags_str = ", ".join(existing_tags)
        header_parts.append(
            f"[现有标签体系] {tags_str}\n"
            f"注意：chat_content_tags 请优先从上述现有标签中选择。只有在现有标签均不适用时，才创建更宏观、抽象的新标签。"
        )

    persona_line = "\n\n".join(header_parts) + ("\n\n" if header_parts else "")
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
    existing_tags: list[str] | None = None,
) -> str:
    """Build a prompt for summarizing a pre-grouped cluster of messages."""
    header_parts = []
    if bot_persona_desc:
        header_parts.append(
            f"[Bot 视角人格] {bot_persona_desc}\n"
            f"注意：请在 summary 每个小话题三元组末尾加上 [Eval] 字段，以上述人格视角对该话题做一句话评价。"
        )

    if existing_tags:
        tags_str = ", ".join(existing_tags)
        header_parts.append(
            f"[现有标签体系] {tags_str}\n"
            f"注意：chat_content_tags 请优先从上述现有标签中选择。只有在现有标签均不适用时，才创建更宏观、抽象的新标签。"
        )

    persona_line = "\n\n".join(header_parts) + ("\n\n" if header_parts else "")
    lines = [
        f"{persona_line}以下是一组语义高度相关的对话记录（共{len(messages)}条）：",
        "",
    ]
    uid_label = _assign_unique_labels(messages)
    for i, m in enumerate(messages):
        lines.append(f"[{i}] {uid_label.get(m.uid, m.display_name or m.uid)}: {m.text}")

    lines.append(
        "\n请为这段对话提炼结构化信息，输出单个 JSON 对象，包含以下字段：\n"
        '{"topic": "核心主题(≤30字)", "summary": "摘要", '
        '"chat_content_tags": ["标签1", "标签2"], "salience": 0.5, "confidence": 0.8, "inherit": false, '
        '"participants_personality": {"Alice": {"O": 0.6, "C": 0.5, "E": 0.7, "A": 0.4, "N": -0.2}}}'
    )
    return "\n".join(lines)
