"""LLM fallback for the interaction axis when TypeSafe is unavailable.

The taxonomy and the stored payload shape are shared with the TypeSafe path, so
downstream tag derivation and recall cannot tell the two backends apart. One
chat completion covers every segment and group, where TypeSafe needs a scored
pass plus a refinement pass; the trade is cost and calibration, not structure.
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Sequence

from .interaction_taxonomy import (
    CUSTOM_INTERACTION_GROUP_ID,
    INTERACTION_ABSTAIN_OPTION,
    INTERACTION_GROUPS,
    INTERACTION_LEAF_CRITERIA,
    MAX_LABELS_PER_SEGMENT,
)
from .parser import _extract_json_objects
from ..utils.prompts.prompt_extractor_utils import build_interaction_system_prompt

if TYPE_CHECKING:
    from ..domain.models import Event

logger = logging.getLogger(__name__)


def _response_text(resp: object) -> str:
    for attr in ("completion_text", "text"):
        value = getattr(resp, attr, None)
        if value is None or callable(value):
            continue
        text = value if isinstance(value, str) else str(value)
        if text:
            return text
    return ""


def _parse(
    text: str, segment_count: int, custom_tags: Sequence[str] = (),
) -> dict[int, list[dict]] | None:
    """Map the completion onto {segment_index: [{group, subtype, confidence}]}."""
    candidates = [obj for obj in _extract_json_objects(text) if "segments" in obj]
    if not candidates:
        return None
    raw_segments = candidates[0].get("segments")
    if not isinstance(raw_segments, list):
        return None
    result: dict[int, list[dict]] = {index: [] for index in range(segment_count)}
    for entry in raw_segments:
        if not isinstance(entry, dict):
            continue
        try:
            index = int(entry.get("index"))
        except (TypeError, ValueError):
            continue
        if index not in result:
            continue
        labels = entry.get("labels")
        if not isinstance(labels, list):
            continue
        seen: set[str] = set()
        for label in labels:
            if not isinstance(label, dict):
                continue
            group_id = str(label.get("group") or "").strip()
            subtype = str(label.get("subtype") or "").strip()
            valid_group = group_id in INTERACTION_GROUPS or (
                group_id == CUSTOM_INTERACTION_GROUP_ID and bool(custom_tags)
            )
            if not valid_group or group_id in seen:
                continue
            if group_id == CUSTOM_INTERACTION_GROUP_ID:
                valid_subtype = subtype in custom_tags
            else:
                valid_subtype = subtype in INTERACTION_LEAF_CRITERIA[group_id]
            if subtype == INTERACTION_ABSTAIN_OPTION or not valid_subtype:
                continue
            try:
                confidence = float(label.get("confidence"))
            except (TypeError, ValueError):
                continue
            seen.add(group_id)
            result[index].append({
                "group": group_id,
                "subtype": subtype,
                "confidence": min(max(confidence, 0.0), 1.0),
            })
            if len(result[index]) == MAX_LABELS_PER_SEGMENT:
                break
    return result


async def classify_segments(
    provider: object,
    state: str,
    segments: Sequence[str],
    custom_tags: Sequence[str] = (),
) -> dict[int, list[dict]] | None:
    """Return per-segment interaction labels, or None when the call is unusable."""
    if provider is None or not segments:
        return None
    try:
        response = await provider.text_chat(
            prompt=state, system_prompt=build_interaction_system_prompt(custom_tags),
        )
    except Exception as exc:
        logger.warning("[InteractionPassLLM] request failed: %s", exc)
        return None
    parsed = _parse(_response_text(response), len(segments), custom_tags)
    if parsed is None:
        logger.warning("[InteractionPassLLM] could not parse interaction labels")
    return parsed
