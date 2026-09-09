"""Plain-text event summaries with topic-local subjective annotations."""
from __future__ import annotations

import html
import re


_FIELD = re.compile(r"\[(What|Who|How|Eval)\]\s*", re.IGNORECASE)
_TOPIC = re.compile(r"\s*\|\s*(?=\[What\])|(?=\[What\])", re.IGNORECASE)


def clean_summary_text(summary: str) -> str:
    value = html.unescape(summary).strip()
    value = re.sub(r"\\([_*\[\]])", r"\1", value)
    for marker in ("**", "__", "`"):
        if value.startswith(marker) and value.endswith(marker):
            value = value[len(marker):-len(marker)].strip()
    return value


def normalize_summary(summary: str, has_bot_persona: bool) -> str:
    """Keep absent evaluations distinct from facts without inventing event content."""
    value = clean_summary_text(summary)
    topics = []
    for part in _TOPIC.split(value):
        part = part.strip()
        if not part:
            continue
        fields = list(_FIELD.finditer(part))
        if not fields:
            topics.append(part)
            continue
        parts = [part[:fields[0].start()].strip()]
        has_what = False
        has_eval = False
        for i, match in enumerate(fields):
            key = match.group(1).title()
            end = fields[i + 1].start() if i + 1 < len(fields) else len(part)
            content = part[match.end():end].strip()
            if key == "Eval":
                if not has_bot_persona:
                    continue
                content = content or "未生成评价"
                has_eval = True
            has_what |= key == "What"
            parts.append(f"[{key}] {content}".rstrip())
        if has_bot_persona and has_what and not has_eval:
            parts.append("[Eval] 未生成评价")
        topic = " ".join(part for part in parts if part)
        if topic:
            topics.append(topic)
    return " | ".join(topics)


def split_subtopics(summary: str) -> list[str]:
    """Return the fact-only [What]/[Who]/[How] segments of a summary, one per topic.

    Any [Eval] already present is dropped: the second pass regenerates it.
    """
    stripped = normalize_summary(summary, has_bot_persona=False)
    return [part.strip() for part in _TOPIC.split(stripped) if part.strip()]


def apply_evals(summary: str, evals: list[str]) -> str:
    """Attach one [Eval] aside per topic segment, matched by position.

    Missing or blank entries become 「未生成评价」 so the stored summary and the
    WebUI stay uniform whether or not the second pass produced every aside.
    """
    subtopics = split_subtopics(summary)
    if not subtopics:
        return normalize_summary(summary, has_bot_persona=True)
    merged = []
    for i, sub in enumerate(subtopics):
        note = str(evals[i]).strip() if i < len(evals) and str(evals[i]).strip() else ""
        merged.append(f"{sub} [Eval] {note}" if note else f"{sub} [Eval] 未生成评价")
    return normalize_summary(" | ".join(merged), has_bot_persona=True)


def strip_evals(summary: str) -> str:
    """Return the summary with every [Eval] aside removed (fact-only text)."""
    return normalize_summary(summary, has_bot_persona=False)
