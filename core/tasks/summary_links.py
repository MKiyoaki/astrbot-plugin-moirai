"""Utilities for keeping summary event-list links in sync with Events.

Daily summaries are Markdown files, but their [事件列表] section contains stable
event id prefixes.  This module treats those prefixes as the source of truth and
refreshes the visible titles from the event repository.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..domain.models import Event
    from ..repository.base import EventRepository


EVENT_SECTION_MARKERS = ("[事件列表]", "[Event List]", "[イベントリスト]")
NEXT_SECTION_MARKERS = ("[情感动态]", "[Mood Dynamics]", "[感情動態]")
EVENT_REF_RE = re.compile(
    r"\[([^\]\n]{1,160})\]\s*-\s*\[([0-9a-fA-F][0-9a-fA-F-]{7,35})\]"
)


@dataclass(frozen=True)
class SummaryEventLink:
    ref: str
    title: str
    event_id: str | None
    topic: str | None
    resolved: bool

    def to_dict(self) -> dict[str, str | bool | None]:
        return {
            "ref": self.ref,
            "title": self.title,
            "event_id": self.event_id,
            "topic": self.topic,
            "resolved": self.resolved,
        }


def _safe_title(value: str | None) -> str:
    title = " ".join(str(value or "未命名事件").split())
    return title.replace("[", "（").replace("]", "）") or "未命名事件"


def _event_section_bounds(content: str) -> tuple[int, int] | None:
    marker_hits = [
        (idx, marker)
        for marker in EVENT_SECTION_MARKERS
        if (idx := content.find(marker)) >= 0
    ]
    if not marker_hits:
        return None
    marker_start, marker = min(marker_hits, key=lambda item: item[0])
    body_start = marker_start + len(marker)
    if body_start < len(content) and content[body_start] == "\r":
        body_start += 1
    if body_start < len(content) and content[body_start] == "\n":
        body_start += 1

    next_hits = [
        idx
        for next_marker in NEXT_SECTION_MARKERS
        if (idx := content.find(next_marker, body_start)) >= 0
    ]
    body_end = min(next_hits) if next_hits else len(content)
    return body_start, body_end


async def _resolve_event_refs(
    refs: set[str],
    event_repo: EventRepository,
) -> dict[str, Event | None]:
    if not refs:
        return {}

    resolved: dict[str, Event | None] = {}
    unresolved: set[str] = set()
    for ref in refs:
        exact = await event_repo.get(ref)
        if exact is not None:
            resolved[ref] = exact
        else:
            unresolved.add(ref.lower())

    if unresolved:
        events = await event_repo.list_all(limit=100_000)
        for ref in list(unresolved):
            matches = [ev for ev in events if ev.event_id.lower().startswith(ref)]
            resolved[ref] = matches[0] if len(matches) == 1 else None

    return resolved


async def refresh_summary_event_links(
    content: str,
    event_repo: EventRepository,
) -> tuple[str, list[SummaryEventLink], bool]:
    """Refresh event titles in the summary event-list section.

    Returns ``(new_content, links, changed)``.  Unresolved/colliding prefixes are
    kept as-is and surfaced in ``links`` with ``resolved=False``.
    """
    bounds = _event_section_bounds(content)
    if bounds is None:
        return content, [], False

    start, end = bounds
    section = content[start:end]
    matches = list(EVENT_REF_RE.finditer(section))
    if not matches:
        return content, [], False

    refs = {m.group(2) for m in matches}
    resolved = await _resolve_event_refs(refs, event_repo)
    links: list[SummaryEventLink] = []
    changed = False

    def replace(match: re.Match[str]) -> str:
        nonlocal changed
        old_title = match.group(1).strip()
        ref = match.group(2)
        event = resolved.get(ref) or resolved.get(ref.lower())
        if event is None:
            links.append(SummaryEventLink(ref, old_title, None, None, False))
            return match.group(0)

        topic = _safe_title(event.topic)
        links.append(SummaryEventLink(ref, old_title, event.event_id, topic, True))
        if topic != old_title:
            changed = True
        return f"[{topic}] - [{ref}]"

    refreshed_section = EVENT_REF_RE.sub(replace, section)
    if not changed:
        return content, links, False
    return content[:start] + refreshed_section + content[end:], links, True


async def refresh_summary_file_event_links(
    path: Path,
    event_repo: EventRepository,
) -> tuple[str, list[SummaryEventLink], bool]:
    content = path.read_text(encoding="utf-8")
    refreshed, links, changed = await refresh_summary_event_links(content, event_repo)
    if changed:
        path.write_text(refreshed, encoding="utf-8")
    return refreshed, links, changed


async def refresh_summary_files_for_event(
    data_dir: Path,
    event_repo: EventRepository,
    event_id: str,
) -> int:
    """Refresh all summary files that reference ``event_id`` or its 8-char prefix."""
    from .summary_paths import iter_summary_paths

    refs = {event_id, event_id[:8]}
    updated = 0
    for path in iter_summary_paths(data_dir):
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if not any(f"[{ref}]" in content for ref in refs):
            continue
        refreshed, _, changed = await refresh_summary_event_links(content, event_repo)
        if changed:
            path.write_text(refreshed, encoding="utf-8")
            updated += 1
    return updated
