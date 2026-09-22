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
    CUSTOM_INTERACTION_GROUP_TAG,
    INTERACTION_ABSTAIN_OPTION,
    INTERACTION_GROUPS,
    INTERACTION_LEAF_CRITERIA,
)
from .parser import _extract_json_objects

if TYPE_CHECKING:
    from ..domain.models import Event

logger = logging.getLogger(__name__)

_MAX_LABELS_PER_SEGMENT = 4


def _response_text(resp: object) -> str:
    for attr in ("completion_text", "text"):
        value = getattr(resp, attr, None)
        if value is None or callable(value):
            continue
        text = value if isinstance(value, str) else str(value)
        if text:
            return text
    return ""


def build_system_prompt(custom_tags: Sequence[str] = ()) -> str:
    """Render the taxonomy into a single instruction block.

    Generated rather than written out so the prompt cannot drift from the
    criteria the TypeSafe backend asks with.
    """
    lines = [
        "You label chat-memory summary segments by the interaction each performs.",
        "",
        "For each segment, choose every interaction group that genuinely applies, "
        f"at most {_MAX_LABELS_PER_SEGMENT}. For each chosen group, pick the one "
        "subtype that fits best, and give a confidence in [0, 1] that reflects how "
        "certain you are. A segment with no clear interaction gets an empty label "
        "list. Do not force a group in order to produce output.",
        "",
        "Interaction groups:",
    ]
    for group_id, group in INTERACTION_GROUPS.items():
        lines.append(f"- {group_id} ({group['label']})")
        lines.append(f"    counts: {group['what']}")
        lines.append(f"    does not count: {group['not_for']}")
        leaves = [
            leaf for leaf in INTERACTION_LEAF_CRITERIA[group_id]
            if leaf != INTERACTION_ABSTAIN_OPTION
        ]
        for leaf in leaves:
            criterion = INTERACTION_LEAF_CRITERIA[group_id][leaf]
            lines.append(
                f"    * {leaf}: {criterion['what']} "
                f"Not for: {criterion['not_for']}"
            )
    if custom_tags:
        lines.append(
            f"- {CUSTOM_INTERACTION_GROUP_ID} ({CUSTOM_INTERACTION_GROUP_TAG})"
        )
        lines.append(
            "    counts: One of the declared Bot-persona-scoped custom interaction "
            "functions genuinely describes the segment."
        )
        lines.append(
            "    does not count: Topics, named entities, one-off details, or a custom "
            "tag that does not clearly fit."
        )
        for tag in custom_tags:
            lines.append(f"    * {tag}: The interaction function is '{tag}'.")
    lines += [
        "",
        "Output one JSON object and nothing else:",
        '{"segments": [{"index": 0, "labels": '
        '[{"group": "<group id>", "subtype": "<subtype id>", "confidence": 0.0}]}]}',
        "Use the exact ids above. Include every segment index, even with no labels.",
    ]
    return "\n".join(lines)


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
            if len(result[index]) == _MAX_LABELS_PER_SEGMENT:
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
            prompt=state, system_prompt=build_system_prompt(custom_tags),
        )
    except Exception as exc:
        logger.warning("[InteractionPassLLM] request failed: %s", exc)
        return None
    parsed = _parse(_response_text(response), len(segments), custom_tags)
    if parsed is None:
        logger.warning("[InteractionPassLLM] could not parse interaction labels")
    return parsed
