"""Format retrieved events and persona data into injectable prompt content.

Events keep their recall order. With a query vector and a vector for every
summary segment, the segments of all recalled events are ranked together by
meaning (cosine) plus a small rarity-weighted overlap and fill the budget;
otherwise each event gets an equal share of the budget that is left, and within
it the segments sharing the most query terms. An entry that does not fit is
clipped instead of ending the block. Token estimate: 1.3 per CJK character, a
third of a token per other character.
"""
from __future__ import annotations

import json
import time
import math
import uuid
from typing import TYPE_CHECKING

import re

from ..config import FAKE_TOOL_CALL_ID_PREFIX
from ..domain.models import Event
from ..extractor.summary import split_subtopics
from ..retrieval.terms import query_terms

if TYPE_CHECKING:
    from ..domain.models import Persona

_TOKEN_BUDGET = 800
_LEXICAL_WEIGHT = 0.3


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    # Match CJK unified ideographs (Chinese characters)
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", text)
    cjk_count = len(cjk_chars)
    
    # Remove CJK characters to isolate non-CJK text (Latin/numerical/punctuation)
    non_cjk_text = re.sub(r"[\u4e00-\u9fff]", "", text)
    non_cjk_tokens = max(0, len(non_cjk_text) // 3)
    
    # Estimate 1.3 tokens per Chinese character
    cjk_tokens = int(cjk_count * 1.3)
    
    return max(1, cjk_tokens + non_cjk_tokens)



def _time_label(end_time: float, now: float) -> str:
    try:
        age = now - float(end_time)
    except (TypeError, ValueError):
        return "unknown time"
    if age < 3600:
        return f"{max(1, int(age / 60))}分钟前"
    if age < 86400:
        return f"{int(age / 3600)}小时前"
    return f"{int(age / 86400)}天前"


def _safe_text(value: object, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _deterministic_memory_fallback(
    events: list[Event],
    *,
    token_budget: int,
    now: float,
) -> str:
    used = _estimate_tokens("## Retrieved memory\n")
    lines: list[str] = []
    for ev in events:
        topic = _safe_text(getattr(ev, "topic", ""), getattr(ev, "event_id", "memory"))
        summary = _safe_text(getattr(ev, "summary", ""))
        label = _time_label(getattr(ev, "end_time", now), now)
        entry = f"- [{label}] {topic}"
        if summary:
            entry += f": {summary[:120]}"
        cost = _estimate_tokens(entry + "\n")
        if used + cost > token_budget:
            break
        lines.append(entry)
        used += cost
    if not lines:
        return ""
    return "## Retrieved memory\n" + "\n".join(lines)


_MIN_ENTRY_TOKENS = 24


def _clip_to_tokens(text: str, budget: int) -> str:
    if budget <= 0:
        return ""
    if _estimate_tokens(text) <= budget:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _estimate_tokens(text[:mid] + "…") <= budget:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + "…" if lo else ""


def _segment_score(segment: str, words: list[str], chars: list[str]) -> int:
    lowered = segment.lower()
    return 2 * sum(1 for t in words if t in lowered) + sum(1 for c in chars if c in segment)


def _summary_body(summary: str, words: list[str], chars: list[str], room: int) -> str:
    """Summary segments that best match the query, kept in their original order, within room tokens.

    When any segment matches the query, only matching segments are used, so
    unused room passes to the next event instead of unrelated detail.
    """
    segments = split_subtopics(summary)
    if not segments or room <= 0:
        return ""
    scores = [_segment_score(s, words, chars) for s in segments]
    candidates = [i for i, s in enumerate(scores) if s > 0] if any(scores) else list(range(len(segments)))
    picked: list[int] = []
    for i in sorted(candidates, key=lambda i: (-scores[i], i)):
        trial = sorted(picked + [i])
        if _estimate_tokens(" | ".join(segments[j] for j in trial)) <= room:
            picked = trial
        elif not picked:
            return _clip_to_tokens(segments[i], room)
    return " | ".join(segments[j] for j in picked)


def _entry_head(ev: Event, now: float) -> str:
    entry = f"- [{_time_label(ev.end_time, now)}] {ev.topic}"
    if ev.chat_content_tags:
        entry += "（" + "、".join(ev.chat_content_tags) + "）"
    return entry


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _ranked_body(events: list[Event], *, token_budget: int, now: float, query: str,
                 query_vector: list[float], segment_vectors: dict[str, list[list[float]]]) -> str:
    """Rank the segments of all events together and fill the budget, keeping event and segment order."""
    words, chars = query_terms(query) if query else ([], [])
    terms = [(t, 2) for t in words] + [(c, 1) for c in chars]
    pool = [(ei, si, seg, segment_vectors[ev.event_id][si])
            for ei, ev in enumerate(events) for si, seg in enumerate(split_subtopics(ev.summary or ""))]
    if not pool:
        return ""
    weight = {t: math.log((len(pool) + 1) / (sum(1 for *_, seg, _ in pool if t in seg) + 0.5)) for t, _ in terms}
    overlap = [sum(b * weight[t] for t, b in terms if t in seg) for *_, seg, _ in pool]
    top = max(overlap) if overlap and max(overlap) > 0 else 1.0
    scored = sorted(((_cosine(query_vector, vec) + _LEXICAL_WEIGHT * max(o, 0.0) / top, ei, si, seg)
                     for (ei, si, seg, vec), o in zip(pool, overlap)), key=lambda x: (-x[0], x[1], x[2]))
    header = "## 相关历史记忆\n"
    used, chosen, heads = _estimate_tokens(header), set(), {}
    for _, ei, si, seg in scored:
        head = heads.get(ei) or _entry_head(events[ei], now) + "："
        cost = _estimate_tokens(seg) + 2 + (0 if ei in heads else _estimate_tokens(head) + 1)
        if used + cost <= token_budget:
            chosen.add((ei, si))
            heads[ei] = head
            used += cost
    lines = []
    for ei, ev in enumerate(events):
        picked = [seg for si, seg in enumerate(split_subtopics(ev.summary or "")) if (ei, si) in chosen]
        if picked:
            lines.append(heads[ei] + " | ".join(picked))
    return header + "\n".join(lines) if lines else ""


def _event_entry(ev: Event, now: float, words: list[str], chars: list[str], share: int) -> str:
    entry = _entry_head(ev, now)
    body = _summary_body(ev.summary or "", words, chars, share - _estimate_tokens(entry + "：\n") - 2)
    if body:
        return entry + "：" + body
    if ev.interaction_flow:
        previews = [
            ref.content_preview.strip()
            for ref in ev.interaction_flow[:4]
            if ref.content_preview and ref.content_preview.strip()
        ]
        if previews:
            entry += " | details: " + " / ".join(previews)
    return entry


def format_events_for_prompt(
    events: list[Event],
    *,
    token_budget: int = _TOKEN_BUDGET,
    now: float | None = None,
    query: str = "",
    query_vector: list[float] | None = None,
    segment_vectors: dict[str, list[list[float]]] | None = None,
) -> str:
    """Return the memory body string (no wrapper), or empty string if events is empty.

    Recall order is kept. Summaries are the facts the extractor stored; raw
    openings are shown only for events without a summary. With vectors for the
    query and every segment, segments are picked by meaning across events, and
    an event none of whose segments ranks within the budget is left out.
    """
    if not events:
        return ""
    if now is None:
        now = time.time()
    if query_vector and segment_vectors is not None and all(
            ev.event_id in segment_vectors and ev.summary for ev in events):
        ranked = _ranked_body(events, token_budget=token_budget, now=now, query=query,
                              query_vector=query_vector, segment_vectors=segment_vectors)
        if ranked:
            return ranked
    words, chars = query_terms(query) if query else ([], [])
    header = "## 相关历史记忆\n"
    used = _estimate_tokens(header)
    lines: list[str] = []
    for index, ev in enumerate(events):
        remaining = token_budget - used
        if remaining < _MIN_ENTRY_TOKENS:
            break
        share = max(remaining // (len(events) - index), _MIN_ENTRY_TOKENS)
        entry = _event_entry(ev, now, words, chars, share)
        cost = _estimate_tokens(entry + "\n")
        if cost > remaining:
            entry = _clip_to_tokens(entry, remaining - 1)
            if not entry:
                break
            cost = _estimate_tokens(entry + "\n")
        lines.append(entry)
        used += cost
    if not lines:
        return ""
    return header + "\n".join(lines)


_DIM_NAMES = {"O": "开放性", "C": "尽责性", "E": "外向性", "A": "宜人性", "N": "神经质"}


def format_events_for_prompt_safe(
    events: list[Event],
    *,
    token_budget: int = _TOKEN_BUDGET,
    now: float | None = None,
    query: str = "",
    query_vector: list[float] | None = None,
    segment_vectors: dict[str, list[list[float]]] | None = None,
) -> str:
    if not events:
        return ""
    if now is None:
        now = time.time()
    try:
        return format_events_for_prompt(events, token_budget=token_budget, now=now, query=query,
                                        query_vector=query_vector, segment_vectors=segment_vectors)
    except Exception:
        return _deterministic_memory_fallback(events, token_budget=token_budget, now=now)


def format_persona_for_prompt(persona: Persona) -> str:
    """Return a brief system-prompt segment with the user's OCEAN personality profile.

    Injects personality data as a soft stylistic hint — the model should adjust
    its tone accordingly but must NOT mention or reference this data in its output.
    Returns empty string when no BigFive data is available.
    """
    attrs = persona.persona_attrs
    bf: dict = attrs.get("big_five", {})
    speaking_style = attrs.get("speaking_style", "")
    has_style = isinstance(speaking_style, str) and bool(speaking_style.strip())
    if not bf and not has_style:
        return ""

    evidence = attrs.get("big_five_evidence", {})
    name = persona.primary_name or "用户"
    lines = [
        f"[用户画像参考] {name}（据此调整措辞风格，不要在回复中提及）："
    ]
    for dim in ["O", "C", "E", "A", "N"]:
        val = bf.get(dim)
        if val is None:
            continue
        pct = round((float(val) + 1.0) / 2.0 * 100)
        label = _DIM_NAMES[dim]
        ev = evidence.get(dim, "") if isinstance(evidence, dict) else ""
        line = f"- {label} {pct}%"
        if ev:
            line += f"：{ev[:60]}"
        lines.append(line)

    if has_style:
        line = f"- 说话风格：{speaking_style.strip()[:120]}"
        quotes = attrs.get("style_quotes", [])
        if isinstance(quotes, list) and quotes:
            line += "；口头禅 " + " ".join(f"「{str(q)[:40]}」" for q in quotes[:2])
        lines.append(line)

    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def format_events_for_fake_tool_call(
    events: list[Event],
    query: str,
    *,
    token_budget: int = _TOKEN_BUDGET,
    now: float | None = None,
    query_vector: list[float] | None = None,
    segment_vectors: dict[str, list[list[float]]] | None = None,
) -> list[dict]:
    """Return two OpenAI-format messages simulating a tool call result.

    Message 1 (assistant): announces a recall_memory tool call.
    Message 2 (tool):      the memory content as tool output.

    Returns empty list if no content to inject.
    """
    content = format_events_for_prompt_safe(events, token_budget=token_budget, now=now, query=query,
                                            query_vector=query_vector, segment_vectors=segment_vectors)
    if not content:
        return []
    tool_call_id = f"{FAKE_TOOL_CALL_ID_PREFIX}{uuid.uuid4().hex[:8]}"
    return [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": "recall_memory",
                        "arguments": json.dumps({"query": query}, ensure_ascii=False),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        },
    ]
