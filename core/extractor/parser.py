"""Parse LLM output into extraction fields; provide rule-based fallback."""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from .summary import normalize_summary

if TYPE_CHECKING:
    from ..boundary.window import MessageWindow

# Keys we require in a valid extraction result
_REQUIRED = {"topic", "summary", "chat_content_tags", "salience", "confidence"}
_BATCH_REQUIRED = _REQUIRED | {"start_idx", "end_idx"}

# Strip markdown code fences if the model wraps output in ```json ... ```
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)

# strict=False tolerates literal control characters (raw newlines, tabs) inside
# JSON strings. Small models transcribing chat text emit those constantly, and
# a stricter decoder turns one stray newline into a whole extra LLM round-trip.
_DECODER = json.JSONDecoder(strict=False)

# Minimum span (number of messages) for a stand-alone event. Single-message
# events are merged into the nearest neighbor unless that is the only event.
_MIN_EVENT_SPAN = 2

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


def _first_meaningful_message_text(messages: list) -> str:
    for msg in messages:
        t = (getattr(msg, "text", "") or "").strip()
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


def _sample_previews_from_messages(messages: list, limit: int = 6) -> list[str]:
    non_empty = [
        (i, msg)
        for i, msg in enumerate(messages)
        if (getattr(msg, "text", "") or "").strip()
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
        name = (getattr(msg, "display_name", "") or "").strip() or "user"
        previews.append(f"{name}: {_preview_text(getattr(msg, 'text', '') or '')}")
    return previews


def _participant_names_from_messages(messages: list, limit: int = 5) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for i, msg in enumerate(messages):
        name = (getattr(msg, "display_name", "") or "").strip() or f"user{i + 1}"
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
        if len(names) >= limit:
            break
    return names


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


def _fallback_tags_from_messages(messages: list) -> list[str]:
    all_text = " ".join((getattr(m, "text", "") or "") for m in messages)
    words = [w for w in re.split(r"[\s锛屻€傦紒锛熴€?!?]+", all_text) if _is_valid_fallback_tag(w)]
    freq: dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:5]]


def _fallback_summary_from_messages(messages: list, topic: str, tags: list[str]) -> str:
    names = _participant_names_from_messages(messages)
    participants = ", ".join(names) if names else "participants"
    if len(messages) > len(names) and len(names) >= 5:
        participants += ", ..."

    samples = _sample_previews_from_messages(messages)
    if not samples:
        return (
            f"This memory contains {len(messages)} messages, mostly non-text or empty content. "
            "No reliable text details were available."
        )

    parts = [f"{participants} discussed \"{topic}\" across {len(messages)} messages."]
    if tags:
        parts.append("Tags: " + ", ".join(tags) + ".")
    parts.append("Representative excerpts: " + " / ".join(samples))
    return " ".join(parts)


def _decode_at(text: str, idx: int) -> tuple[object, int] | None:
    """Decode one JSON value starting at ``idx``; None if it does not parse."""
    try:
        return _DECODER.raw_decode(text, idx)
    except ValueError:
        return None


def _salvage_objects(text: str) -> list[dict]:
    """Decode every top-level ``{...}`` independently.

    The point is partial recovery: when one object in an array has a mis-escaped
    quote, decoding the array as a whole discards its healthy siblings too. Here a
    bad object costs only itself. Nested objects are skipped automatically because
    a successful decode advances past them; when the *outer* object is the broken
    one we may surface an inner fragment instead, which the required-key check in
    the caller then drops.
    """
    found: list[dict] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        decoded = _decode_at(text, i)
        if decoded is None:
            i += 1
            continue
        value, end = decoded
        if isinstance(value, dict):
            found.append(value)
            i = end
        else:
            i += 1
    return found


def _extract_json_objects(text: str) -> list[dict]:
    """Pull candidate event objects out of a raw LLM completion.

    Handles the three ways weak models routinely deviate: wrapping the payload in
    prose or code fences, emitting a bare object where an array was requested (or
    vice versa), and breaking one object inside an otherwise fine array. Returns
    objects in document order; validation is the caller's job.
    """
    fence_match = _FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1)
    text = text.strip()
    if not text:
        return []

    # Whole-payload decode: scan for the first position that yields a usable
    # value. Scanning (rather than assuming position 0) skips any preamble prose.
    whole: list[dict] = []
    for i, ch in enumerate(text):
        if ch not in "[{":
            continue
        decoded = _decode_at(text, i)
        if decoded is None:
            continue
        value = decoded[0]
        if isinstance(value, dict):
            whole = [value]
            break
        if isinstance(value, list):
            items = [v for v in value if isinstance(v, dict)]
            if items:
                whole = items
                break
        # Decodable but useless — e.g. the ["tag", "tag"] inside a broken
        # object. Keep scanning rather than settling for it.

    # A broken array still decodes object-by-object, so prefer whichever
    # strategy recovered more.
    salvaged = _salvage_objects(text)
    return whole if len(whole) >= len(salvaged) else salvaged


def _merge_into(target: dict, source: dict) -> dict:
    """Merge source event-dict into target (in-place on target, returns target)."""
    target["start_idx"] = min(int(target["start_idx"]), int(source["start_idx"]))
    target["end_idx"] = max(int(target["end_idx"]), int(source["end_idx"]))
    t_topic = str(target.get("topic", "")).strip()
    s_topic = str(source.get("topic", "")).strip()
    if s_topic and s_topic not in t_topic.split(" / "):
        topics = [topic for topic in t_topic.split(" / ") if topic]
        topics.append(s_topic)
        target["topic"] = " / ".join(topics[:3])[:60]
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
    # participant_style: union by display name, target wins on collision
    src_style = source.get("participant_style") or {}
    if src_style:
        merged_style = dict(src_style)
        merged_style.update(target.get("participant_style") or {})
        target["participant_style"] = merged_style
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


def _merge_to_session_event(results: list[dict]) -> list[dict]:
    """Collapse parsed fragments back into one session-window event."""
    if len(results) <= 1:
        return results
    merged = dict(results[0])
    for item in results[1:]:
        _merge_into(merged, item)
    return [merged]


def parse_llm_output(
    text: str,
    max_idx: int,
    has_bot_persona: bool = False,
    merge_to_single: bool = False,
) -> list[dict] | None:
    """Parse and validate JSON Array from LLM completion text."""
    results = []
    for item in _extract_json_objects(text):
        if not _BATCH_REQUIRED.issubset(item):
            # A bare object (no indices) is still usable: it is the single-event
            # shape, which every caller collapses the array to anyway.
            if _REQUIRED.issubset(item):
                item = {**item, "start_idx": 0, "end_idx": max_idx}
            else:
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
            "summary": normalize_summary(str(item["summary"]), has_bot_persona),
            "chat_content_tags": _parse_tags(item.get("chat_content_tags")),
            "salience": _clamp(item.get("salience", 0.5)),
            "confidence": _clamp(item.get("confidence", 0.5)),
            "inherit": bool(item.get("inherit", False)),
            "participants_personality": _parse_personality(item.get("participants_personality")),
            "participant_style": _parse_participant_style(item.get("participant_style")),
        }
        results.append(parsed)

    if not results:
        return None

    # Sort by start_idx so neighbor lookups in merge are correct, then merge short spans.
    results.sort(key=lambda r: int(r["start_idx"]))
    results = _merge_short_spans(results)
    if merge_to_single:
        results = _merge_to_session_event(results)
    return results if results else None


def parse_single_item(text: str, has_bot_persona: bool = False) -> dict | None:
    """Parse a single JSON object (used for distillation)."""
    data = next(
        (obj for obj in _extract_json_objects(text) if _REQUIRED.issubset(obj)),
        None,
    )
    if data is None:
        return None

    parsed = {
        "topic": str(data["topic"])[:60],
        "summary": normalize_summary(str(data["summary"]), has_bot_persona),
        "chat_content_tags": _parse_tags(data.get("chat_content_tags")),
        "salience": _clamp(data.get("salience", 0.5)),
        "confidence": _clamp(data.get("confidence", 0.5)),
        "inherit": bool(data.get("inherit", False)),
        "participants_personality": _parse_personality(data.get("participants_personality")),
        "participant_style": _parse_participant_style(data.get("participant_style")),
    }
    return parsed


def parse_eval_map(text: str, expected: dict[str, int]) -> dict[str, list[str]]:
    """Parse the batched second-pass output into ``{label: [aside, ...]}``.

    Expects a JSON object keyed by event label -> list of asides. Each list is
    padded with "" / truncated to ``expected[label]``; missing labels yield an
    all-"" list (the caller backfills 「未生成评价」). Never raises.
    """
    result: dict[str, list[str]] = {label: [""] * n for label, n in expected.items()}
    if not text:
        return result
    fence = _FENCE_RE.search(text)
    if fence:
        text = fence.group(1)
    text = text.strip()

    obj: dict | None = None
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        decoded = _decode_at(text, i)
        if decoded is not None and isinstance(decoded[0], dict):
            obj = decoded[0]
            break
    if obj is None:
        return result

    for label, n in expected.items():
        raw = obj.get(label)
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            continue
        vals = [str(v).strip() for v in raw if not isinstance(v, (dict, list))]
        result[label] = (vals + [""] * n)[:n]
    return result


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
        "participant_style": {},
    }]


def fallback_single_extraction(messages: list) -> dict:
    """Rule-based extraction for one already-partitioned message cluster."""
    first_text = _first_meaningful_message_text(messages)
    topic = first_text[:30] if first_text else "(no text content)"
    tags = _fallback_tags_from_messages(messages)
    summary = _fallback_summary_from_messages(messages, topic, tags)
    salience = min(0.3 + 0.01 * len(messages), 0.7)
    return {
        "topic": topic,
        "summary": summary,
        "chat_content_tags": tags,
        "salience": round(salience, 3),
        "confidence": 0.2,
        "inherit": False,
        "participants_personality": None,
        "participant_style": {},
    }


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


def _parse_tags(raw: object) -> list[str]:
    """Coerce the tag field to a short list of strings.

    A model that answers with a bare string instead of a list used to be sliced
    character-by-character into five one-character "tags".
    """
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    tags: list[str] = []
    for t in raw:
        if isinstance(t, (dict, list)):
            continue
        text = str(t).strip()[:30]
        if text:
            tags.append(text)
        if len(tags) >= 5:
            break
    return tags


def _parse_participant_style(raw: object) -> dict[str, str]:
    """Validate {display_name: "one-line speaking-style description"} observations.

    A flat name→string map (not nested) so a weak model has far fewer ways to
    emit malformed JSON. Tolerates a legacy {"note": ..., "quotes": [...]} object
    per name by flattening it. Returns {} when nothing usable is present.
    """
    if not isinstance(raw, dict):
        return {}

    clean: dict[str, str] = {}
    for name, val in raw.items():
        if isinstance(val, str):
            text = val.strip()
        elif isinstance(val, dict):  # legacy nested shape
            note = str(val.get("note", "")).strip()
            quotes = val.get("quotes", [])
            if isinstance(quotes, list) and quotes:
                note = (note + "，" if note else "") + "、".join(
                    f"「{str(q).strip()}」" for q in quotes[:2] if str(q).strip()
                )
            text = note
        else:
            continue
        text = text.replace("\n", " ").strip()[:200]
        if text:
            clean[str(name)[:64]] = text

    return clean
