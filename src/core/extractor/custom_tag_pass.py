"""Bounded generation of reusable Chinese interaction tags for uncategorised events."""
from __future__ import annotations

import json
import logging
import re
from typing import Sequence
from ..utils.prompts.prompt_extractor_utils import build_custom_tag_system_prompt

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
            system_prompt=build_custom_tag_system_prompt(
                existing_tags, rejected_tags, allow_new=allow_new,
            ),
        )
    except Exception as exc:
        logger.warning("[CustomTagPass] generation failed: %s", exc)
        return ""
    return parse_custom_tag(_response_text(response))
