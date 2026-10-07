"""Core turn-annotation.v1 validation and Moirai-owned note/view projections."""
from __future__ import annotations

import copy
import json

DIMENSIONS = ("duty", "intellect", "adversity", "mating", "positivity", "negativity", "deception")
TEXT_FIELDS = ("what_happened", "feeling", "coping", "goal", "expectation")
NOTES_BLOCK = {"id": "notes", "start": "<!-- EM:NOTES:START -->", "end": "<!-- EM:NOTES:END -->"}
COMMITMENTS_BLOCK = {"id": "commitments", "start": "<!-- EM:COMMITMENTS:START -->", "end": "<!-- EM:COMMITMENTS:END -->"}


# ---------------------------------------------------------------------------
# 独立验证 Core 发布的闭合格式；不导入其他插件的源码
# ---------------------------------------------------------------------------

def validate_annotation(value: object) -> dict:
    keys = {"schema_version", "complete", "situation", "commitments", *TEXT_FIELDS}
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("每轮便签字段不符合 turn-annotation.v1。")
    if value["schema_version"] != "turn-annotation.v1" or type(value["complete"]) is not bool:
        raise ValueError("每轮便签版本或完整性字段无效。")
    for name in TEXT_FIELDS:
        if not isinstance(value[name], str) or len(value[name]) > 4000:
            raise ValueError("每轮便签文本必须是最多 4000 字符的字符串。")
    situation = value["situation"]
    if situation is not None:
        if not isinstance(situation, dict) or set(situation) != {"labels", "aimed_at"}:
            raise ValueError("每轮便签情境字段无效。")
        labels = situation["labels"]
        if (not isinstance(labels, dict) or set(labels) != set(DIMENSIONS)
                or any(type(level) is not int or level not in (0, 1, 2) for level in labels.values())
                or (situation["aimed_at"] is not None and type(situation["aimed_at"]) is not bool)):
            raise ValueError("每轮便签情境标签无效。")
    commitments = value["commitments"]
    if (not isinstance(commitments, list) or len(commitments) > 8
            or any(not isinstance(item, str) or not item.strip() or len(item) > 500 for item in commitments)):
        raise ValueError("记下必须是最多 8 条、每条最多 500 字符的非空文本。")
    return copy.deepcopy(value)


def annotation_from_metadata(metadata: dict | str) -> dict | None:
    try:
        metadata = json.loads(metadata) if isinstance(metadata, str) else metadata
        return validate_annotation(metadata.get("turn_annotation")) if isinstance(metadata, dict) else None
    except (ValueError, TypeError):
        return None


def notes_text(annotation: dict | None) -> str:
    if annotation is None:
        return ""
    labels = (("expectation", "我预计对方接下来"), ("feeling", "我此刻的情绪"), ("goal", "我想达到的目的"))
    rows = [f"{label}：{annotation[key]}" for key, label in labels if annotation[key].strip()]
    return "[上一轮你回复这个人时心里想的]\n" + "\n".join(rows) if rows else ""


def persona_views(messages: list, persona: str | None = None) -> list[dict]:
    result = []
    for message in messages:
        if message.role != "assistant" or (persona is not None and message.bot_persona_name != persona):
            continue
        annotation = annotation_from_metadata(message.metadata_json)
        if annotation is None:
            continue
        result.append({"message_id": message.message_id, "what_happened": annotation["what_happened"],
                       "feeling": annotation["feeling"], "goal": annotation["goal"]})
    return result
