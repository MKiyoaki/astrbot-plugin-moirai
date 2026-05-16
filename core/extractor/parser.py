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


def parse_llm_output(text: str, max_idx: int) -> list[dict] | None:
    """Parse and validate JSON Array from LLM completion text."""
    text = text.strip()
    fence_match = _FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()

    start = text.find("[")
    end = text.rfind("]") + 1
    if start == -1 or end == 0:
        # Fallback to single item if it's not an array
        single = parse_single_item(text)
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

        results.append({
            "start_idx": start_idx,
            "end_idx": end_idx,
            "topic": str(item["topic"])[:60],
            "summary": str(item["summary"]),
            "chat_content_tags": [str(t)[:30] for t in item.get("chat_content_tags", [])[:5]],
            "salience": _clamp(item.get("salience", 0.5)),
            "confidence": _clamp(item.get("confidence", 0.5)),
            "inherit": bool(item.get("inherit", False)),
            "participants_personality": _parse_personality(item.get("participants_personality")),
        })

    return results if results else None


def parse_single_item(text: str) -> dict | None:
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

    return {
        "topic": str(data["topic"])[:60],
        "summary": str(data["summary"]),
        "chat_content_tags": [str(t)[:30] for t in data.get("chat_content_tags", [])[:5]],
        "salience": _clamp(data.get("salience", 0.5)),
        "confidence": _clamp(data.get("confidence", 0.5)),
        "inherit": bool(data.get("inherit", False)),
        "participants_personality": _parse_personality(data.get("participants_personality")),
    }


def fallback_extraction(window: MessageWindow) -> list[dict]:
    """Rule-based extraction used when the LLM call fails or is unavailable."""
    first_text = _first_meaningful_text(window)
    topic = first_text[:30] if first_text else "（无内容）"
    summary = f"对话包含 {window.message_count} 条消息，始于 '{topic}'。"

    # Collect all words, pick the most frequent (rough approximation)
    all_text = " ".join(m.text for m in window.messages)
    words = [w for w in re.split(r"[\s，。！？、,!?]+", all_text) if _is_valid_fallback_tag(w)]
    freq: dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    tags = [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:5]]

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
