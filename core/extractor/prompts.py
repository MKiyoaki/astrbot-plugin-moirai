"""Prompt templates for LLM event extraction."""
from __future__ import annotations

import math

from ..boundary.window import MessageWindow

SYSTEM_PROMPT = """\
你是一个聊天记录分析助手。根据对话内容提取结构化信息，严格按照指定 JSON 格式输出，不输出任何其他文字。

输出格式（仅输出此 JSON，无前缀、无后缀、无 markdown 代码块）：
{"topic": "...", "chat_content_tags": ["...", "..."], "salience": 0.5, "confidence": 0.8}

字段说明：
- topic: 对话核心主题，简洁明了，30字以内
- chat_content_tags: 2~5个关键词标签，用于检索和分类
- salience: 重要性分值 0.0~1.0（重要事件/情绪事件偏高，日常闲聊偏低）
- confidence: 本次提取结果的置信度 0.0~1.0\
"""


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
    for m in messages:
        label = uid_label[m.uid]
        lines.append(f"{label}: {m.text}")

    return "\n".join(lines)
