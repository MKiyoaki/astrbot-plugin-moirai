"""Bounded generation of reusable Chinese interaction tags for uncategorised events."""
from __future__ import annotations

import json
import logging
import re
from typing import Sequence

logger = logging.getLogger(__name__)

_CUSTOM_TAG_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]{2,8}")


def _response_text(response: object) -> str:
    for attr in ("completion_text", "text"):
        value = getattr(response, attr, None)
        if value is None or callable(value):
            continue
        text = value if isinstance(value, str) else str(value)
        if text:
            return text
    return ""


def parse_custom_tag(text: str) -> str:
    """Return one validated Chinese interaction tag or an empty string."""
    try:
        payload = json.loads(str(text or "").strip())
    except ValueError:
        return ""
    if not isinstance(payload, dict) or set(payload) != {"tag"}:
        return ""
    tag = str(payload.get("tag") or "").strip()
    return tag if _CUSTOM_TAG_PATTERN.fullmatch(tag) else ""


def build_system_prompt(
    existing_tags: Sequence[str], rejected_tags: Sequence[str], *, allow_new: bool,
) -> str:
    existing = "、".join(existing_tags) if existing_tags else "无"
    rejected = "、".join(rejected_tags) if rejected_tags else "无"
    mode = (
        "可以优先复用已有自定义标签；没有合适项时创建一个新标签。"
        if allow_new
        else "词表已满，只能从已有自定义标签中选择，不得创建新标签。"
    )
    return (
        "你负责为未被既有交互分类树覆盖的聊天记忆事件选择一个交互行为标签。"
        "标签只描述可复用的交互功能，例如安慰、道歉、庆祝；不得描述话题、人物、"
        "实体、单次事件细节或完整句子。标签必须由2到8个中文字符组成。"
        f"{mode}\n已有自定义标签：{existing}\n已被Judge拒绝的候选：{rejected}\n"
        "不要再次选择被拒绝的候选。只输出一个JSON对象，不输出其他文字："
        '{"tag":"标签"}'
    )


async def generate_custom_tag(
    provider: object,
    state: str,
    existing_tags: Sequence[str],
    rejected_tags: Sequence[str],
    *,
    allow_new: bool,
) -> str:
    """Generate or reuse one custom tag; invalid or failed output becomes empty."""
    if provider is None:
        return ""
    try:
        response = await provider.text_chat(
            prompt=state,
            system_prompt=build_system_prompt(
                existing_tags, rejected_tags, allow_new=allow_new,
            ),
        )
    except Exception as exc:
        logger.warning("[CustomTagPass] generation failed: %s", exc)
        return ""
    return parse_custom_tag(_response_text(response))
