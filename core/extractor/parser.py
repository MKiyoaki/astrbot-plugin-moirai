"""Parse LLM output into extraction fields; provide rule-based fallback."""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..boundary.window import MessageWindow

# Keys we require in a valid extraction result
_REQUIRED = {"topic", "chat_content_tags", "salience", "confidence"}

# Strip markdown code fences if the model wraps output in ```json ... ```
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def parse_llm_output(text: str) -> dict | None:
    """Parse and validate JSON from LLM completion text.

    Returns a dict with topic/chat_content_tags/salience/confidence on success,
    or None if the output cannot be parsed or fails validation.
    """
    text = text.strip()

    # Strip markdown fences
    fence_match = _FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()

    # Find the first {...} block
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

    topic = str(data["topic"])[:60]
    tags = data["chat_content_tags"]
    if not isinstance(tags, list):
        return None
    tags = [str(t)[:30] for t in tags[:5]]

    salience = _clamp(data.get("salience", 0.5))
    confidence = _clamp(data.get("confidence", 0.5))

    return {
        "topic": topic,
        "chat_content_tags": tags,
        "salience": salience,
        "confidence": confidence,
    }


def fallback_extraction(window: MessageWindow) -> dict:
    """Rule-based extraction used when the LLM call fails or is unavailable."""
    topic = window.first_text[:30] if window.first_text else "（无内容）"

    # Collect all words, pick the most frequent (rough approximation)
    all_text = " ".join(m.text for m in window.messages)
    words = [w for w in re.split(r"[\s，。！？、,!?]+", all_text) if len(w) >= 2]
    freq: dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    tags = [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:5]]

    salience = min(0.3 + 0.01 * window.message_count, 0.7)

    return {
        "topic": topic,
        "chat_content_tags": tags,
        "salience": round(salience, 3),
        "confidence": 0.2,  # low confidence indicates fallback was used
    }


def _clamp(value: object, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return 0.5
