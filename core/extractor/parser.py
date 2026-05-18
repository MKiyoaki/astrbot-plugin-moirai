"""Parse LLM output into extraction fields; provide rule-based fallback."""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..boundary.window import MessageWindow

# Keys we require in a valid extraction result
_REQUIRED = {"topic", "summary", "chat_content_tags", "salience", "confidence"}
_BATCH_REQUIRED = _REQUIRED | {"start_idx", "end_idx"}

# Strip markdown code fences if the model wraps output in ```json ... ```
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)

# Minimum span (number of messages) for a stand-alone event. Single-message
# events are merged into the nearest neighbor unless that is the only event.
_MIN_EVENT_SPAN = 2

_EVAL_MISSING_PLACEHOLDER = "[Eval] 信息不足"
_EVAL_TOKEN_RE = re.compile(r"\[Eval\]", re.IGNORECASE)
_EVAL_CONFIDENCE_PENALTY = 0.7

# Fallback tag pollution filters
_TAG_MAX_LEN = 12
_TAG_STOP_PREFIXES = ("@", "#", "http://", "https://", "qq=")
_TAG_STOPWORDS = frozenset({
    "[图片]", "[表情]", "[语音]", "[视频]", "[卡片]", "@用户",
    "这个", "那个", "什么", "怎么", "可以", "已经", "还是", "但是",
    "因为", "所以", "如果", "或者", "我们", "你们", "他们",
})
_TAG_NUMERIC_RE = re.compile(r"^\d+$")


def _is_valid_fallback_tag(w: str) -> bool:
    if len(w) < 2 or len(w) > _TAG_MAX_LEN:
        return False
    if w in _TAG_STOPWORDS:
        return False
    if _TAG_NUMERIC_RE.match(w):
        return False
    if any(w.startswith(p) for p in _TAG_STOP_PREFIXES):
        return False
    return True


def _first_meaningful_text(window: MessageWindow) -> str:
    for m in window.messages:
        t = (m.text or "").strip()
        if t:
            return t
    return ""


def _preview_text(text: str, limit: int = 48) -> str:
    preview = re.sub(r"\s+", " ", text).strip()
    if len(preview) <= limit:
        return preview
    return preview[:limit].rstrip() + "..."


def _participant_names(window: MessageWindow, limit: int = 5) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for i, msg in enumerate(window.messages):
        name = (msg.display_name or "").strip() or f"用户{i + 1}"
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
        if len(names) >= limit:
            break
    return names


def _sample_message_previews(window: MessageWindow, limit: int = 6) -> list[str]:
    non_empty = [
        (i, msg)
        for i, msg in enumerate(window.messages)
        if (msg.text or "").strip()
    ]
    if not non_empty:
        return []

    if len(non_empty) <= limit:
        selected = non_empty
    else:
        mid = len(non_empty) // 2
        wanted_indices = [0, 1, mid - 1, mid, len(non_empty) - 2, len(non_empty) - 1]
        selected = []
        used: set[int] = set()
        for idx in wanted_indices:
            idx = max(0, min(len(non_empty) - 1, idx))
            original_idx, msg = non_empty[idx]
            if original_idx in used:
                continue
            used.add(original_idx)
            selected.append((original_idx, msg))

    previews: list[str] = []
    for _, msg in selected[:limit]:
        name = (msg.display_name or "").strip() or "用户"
        previews.append(f"{name}: {_preview_text(msg.text)}")
    return previews


def _fallback_summary(window: MessageWindow, topic: str, tags: list[str]) -> str:
    names = _participant_names(window)
    participants = "、".join(names) if names else "对话参与者"
    if len(window.messages) > len(names) and len(names) >= 5:
        participants += "等"

    samples = _sample_message_previews(window)
    if not samples:
        return (
            f"本段对话共 {window.message_count} 条消息，主要由图片、表情或非文本消息组成，"
            "未提取到足够文字内容。"
        )

    parts = [
        f"{participants}在本段对话中围绕“{topic}”展开交流，共 {window.message_count} 条消息。"
    ]
    if tags:
        parts.append(f"高频线索包括：{'、'.join(tags)}。")
    parts.append(f"代表片段：{' / '.join(samples)}")
    return "".join(parts)


def _ensure_eval_field(item: dict) -> None:
    """If summary lacks any [Eval] segment, append a placeholder and discount confidence.

    Mutates item in place. Only call this when a bot persona was supplied to the LLM
    (i.e. the [Eval] field is required by the prompt). Each [What]/[Who]/[How] triple
    is separated by " | "; we add the placeholder per-triple where it is missing.
    """
    summary = str(item.get("summary", ""))
    if not summary:
        return
    if _EVAL_TOKEN_RE.search(summary):
        # At least one [Eval] present — accept; LLM may still skip some, but we
        # avoid aggressive per-triple rewriting to preserve readability.
        return
    # Whole summary missing [Eval] — append a single placeholder at the end.
    sep = "" if summary.endswith((" ", "。", "!", "?", "！", "？", ".")) else " "
    item["summary"] = f"{summary}{sep}{_EVAL_MISSING_PLACEHOLDER}"
    try:
        item["confidence"] = _clamp(float(item.get("confidence", 0.5)) * _EVAL_CONFIDENCE_PENALTY)
    except (TypeError, ValueError):
        item["confidence"] = 0.35


def _merge_into(target: dict, source: dict) -> dict:
    """Merge source event-dict into target (in-place on target, returns target)."""
    target["start_idx"] = min(int(target["start_idx"]), int(source["start_idx"]))
    target["end_idx"] = max(int(target["end_idx"]), int(source["end_idx"]))
    t_sum = str(target.get("summary", "")).strip()
    s_sum = str(source.get("summary", "")).strip()
    if t_sum and s_sum and t_sum != s_sum:
        target["summary"] = f"{t_sum} | {s_sum}"
    elif s_sum and not t_sum:
        target["summary"] = s_sum
    target["salience"] = max(float(target.get("salience", 0.0)), float(source.get("salience", 0.0)))
    target["confidence"] = max(float(target.get("confidence", 0.0)), float(source.get("confidence", 0.0)))
    merged_tags: list[str] = []
    seen: set[str] = set()
    for tag in list(target.get("chat_content_tags", [])) + list(source.get("chat_content_tags", [])):
        if tag not in seen:
            seen.add(tag)
            merged_tags.append(tag)
    target["chat_content_tags"] = merged_tags[:5]
    target["inherit"] = bool(target.get("inherit") or source.get("inherit"))
    # participants_personality: keep target's if present, else source's
    if not target.get("participants_personality") and source.get("participants_personality"):
        target["participants_personality"] = source["participants_personality"]
    return target


def _merge_short_spans(results: list[dict]) -> list[dict]:
    """Merge single-message events into the most appropriate neighbor.

    Selection rule (per plan):
      1. Prefer neighbor with chat_content_tags intersection or inherit=true.
      2. Otherwise the index-nearer neighbor; fallback to previous.

    A short event with no neighbor (only 1 event total) is kept as-is.
    """
    if len(results) <= 1:
        return results

    # Iterate; rebuild list to keep indices straightforward.
    merged: list[dict] = []
    pending: list[dict] = list(results)
    while pending:
        item = pending.pop(0)
        span = int(item["end_idx"]) - int(item["start_idx"]) + 1
        if span >= _MIN_EVENT_SPAN or (not merged and not pending):
            merged.append(item)
            continue

        prev = merged[-1] if merged else None
        nxt = pending[0] if pending else None

        def _tag_overlap(a: dict | None, b: dict) -> bool:
            if not a:
                return False
            return bool(set(a.get("chat_content_tags", [])) & set(b.get("chat_content_tags", [])))

        target = None
        # Rule 1: tag overlap or inherit
        if prev and (_tag_overlap(prev, item) or bool(item.get("inherit"))):
            target = prev
        elif nxt and (_tag_overlap(nxt, item) or bool(nxt.get("inherit"))):
            target = nxt
        # Rule 2: nearer neighbor by index distance
        elif prev and nxt:
            prev_dist = int(item["start_idx"]) - int(prev["end_idx"])
            nxt_dist = int(nxt["start_idx"]) - int(item["end_idx"])
            target = prev if prev_dist <= nxt_dist else nxt
        elif prev:
            target = prev
        elif nxt:
            target = nxt

        if target is prev and prev is not None:
            _merge_into(prev, item)
        elif target is nxt and nxt is not None:
            # Merge item into the next pending element so it propagates forward.
            _merge_into(nxt, item)
        else:
            # No neighbor at all — keep
            merged.append(item)

    return merged


def parse_llm_output(text: str, max_idx: int, has_bot_persona: bool = False) -> list[dict] | None:
    """Parse and validate JSON Array from LLM completion text."""
    text = text.strip()
    fence_match = _FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()

    start = text.find("[")
    end = text.rfind("]") + 1
    if start == -1 or end == 0:
        # Fallback to single item if it's not an array
        single = parse_single_item(text, has_bot_persona=has_bot_persona)
        if single:
            # Add indices to make it compatible with batch processing
            single["start_idx"] = 0
            single["end_idx"] = max_idx
            return [single]
        return None

    try:
        raw_data = json.loads(text[start:end])
    except json.JSONDecodeError:
        return None

    if not isinstance(raw_data, list):
        return None

    results = []
    for item in raw_data:
        if not isinstance(item, dict) or not _BATCH_REQUIRED.issubset(item):
            continue

        try:
            start_idx = int(item["start_idx"])
            end_idx = int(item["end_idx"])
        except (ValueError, TypeError):
            continue

        if start_idx < 0 or end_idx > max_idx or start_idx > end_idx:
            continue

        parsed = {
            "start_idx": start_idx,
            "end_idx": end_idx,
            "topic": str(item["topic"])[:60],
            "summary": str(item["summary"]),
            "chat_content_tags": [str(t)[:30] for t in item.get("chat_content_tags", [])[:5]],
            "salience": _clamp(item.get("salience", 0.5)),
            "confidence": _clamp(item.get("confidence", 0.5)),
            "inherit": bool(item.get("inherit", False)),
            "participants_personality": _parse_personality(item.get("participants_personality")),
        }
        if has_bot_persona:
            _ensure_eval_field(parsed)
        results.append(parsed)

    if not results:
        return None

    # Sort by start_idx so neighbor lookups in merge are correct, then merge short spans.
    results.sort(key=lambda r: int(r["start_idx"]))
    results = _merge_short_spans(results)
    return results if results else None


def parse_single_item(text: str, has_bot_persona: bool = False) -> dict | None:
    """Parse a single JSON object (used for distillation)."""
    text = text.strip()
    fence_match = _FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()

    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        return None

    try:
        data = json.loads(text[start:end])
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict) or not _REQUIRED.issubset(data):
        return None

    parsed = {
        "topic": str(data["topic"])[:60],
        "summary": str(data["summary"]),
        "chat_content_tags": [str(t)[:30] for t in data.get("chat_content_tags", [])[:5]],
        "salience": _clamp(data.get("salience", 0.5)),
        "confidence": _clamp(data.get("confidence", 0.5)),
        "inherit": bool(data.get("inherit", False)),
        "participants_personality": _parse_personality(data.get("participants_personality")),
    }
    if has_bot_persona:
        _ensure_eval_field(parsed)
    return parsed


def fallback_extraction(window: MessageWindow) -> list[dict]:
    """Rule-based extraction used when the LLM call fails or is unavailable."""
    first_text = _first_meaningful_text(window)
    topic = first_text[:30] if first_text else "（无内容）"

    # Collect all words, pick the most frequent (rough approximation)
    all_text = " ".join(m.text for m in window.messages)
    words = [w for w in re.split(r"[\s，。！？、,!?]+", all_text) if _is_valid_fallback_tag(w)]
    freq: dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    tags = [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:5]]
    summary = _fallback_summary(window, topic, tags)

    salience = min(0.3 + 0.01 * window.message_count, 0.7)

    return [{
        "start_idx": 0,
        "end_idx": window.message_count - 1,
        "topic": topic,
        "summary": summary,
        "chat_content_tags": tags,
        "salience": round(salience, 3),
        "confidence": 0.2,
        "inherit": False,
        "participants_personality": None,
    }]


def _clamp(value: object, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return 0.5


def _parse_personality(raw: object) -> dict[str, dict] | None:
    """Validate and clamp O,C,E,A,N scores from the LLM.

    Supports nested format {"scores":{...}, "evidence":"..."} and legacy
    flat format {"O":0.6,...} for backward compatibility.
    Returns {name: {"scores": {trait: float}, "evidence": str|None}}.
    """
    if not isinstance(raw, dict):
        return None

    clean_p: dict[str, dict] = {}
    for name, traits in raw.items():
        if not isinstance(traits, dict):
            continue

        # Nested format: {"scores": {...}, "evidence": "..."}
        if "scores" in traits and isinstance(traits["scores"], dict):
            raw_scores = traits["scores"]
            evidence: str | None = str(traits["evidence"])[:200] if traits.get("evidence") else None
        else:
            # Legacy flat format: {"O": 0.6, "C": 0.5, ...}
            raw_scores = traits
            evidence = None

        scores: dict[str, float] = {}
        for trait in ["O", "C", "E", "A", "N"]:
            if trait in raw_scores:
                scores[trait] = _clamp(raw_scores[trait], lo=-1.0, hi=1.0)

        if scores:
            clean_p[str(name)] = {"scores": scores, "evidence": evidence}

    return clean_p if clean_p else None
