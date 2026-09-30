"""Fitting retrieved canon events into one evidence pack under a shared token budget."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace

from .gateway import EvidencePack, Memory, full_sentences


CHANNEL_LABEL = {
    "experienced": "亲历",
    "witnessed": "在场目睹",
    "told": "听人讲述",
    "recalled": "回忆",
    "reported": "经汇报得知",
    "unstated": "文本未表明是否知情",
}
RATIONALE_CUES = ("动机", "来意", "理想", "原因", "因为", "为了", "目的是", "阻止", "避免", "而战")
_CJK = re.compile(r"[一-鿿]+")
@dataclass(frozen=True)
class Hit:
    event_id: str
    scene_key: str
    anchor: str
    topic: str
    summary: str
    channel: str
    score: float
    position: int
    evidence: tuple[tuple[int, str, str], ...]


def estimate_tokens(text: str) -> int:
    cjk = sum(1 for char in text if _CJK.fullmatch(char))
    return cjk + math.ceil((len(text) - cjk) / 4)


def clip(text: str, limit: int) -> str:
    return text[:limit] + ("……" if len(text) > limit else "")


def result_line(hit: Hit) -> Hit:
    """One storyline beat: the event's title and its summary's closing sentence, which states the outcome."""
    sentences = full_sentences(hit.summary)
    return replace(hit, summary=clip(hit.topic + "：" + (sentences[-1] if sentences else ""), 90), evidence=())


def fill(pack: EvidencePack, hits: list[Hit], episode: str | None, budget: int,
         *, total_budget: int | None = None, summary_limit: int | None = None) -> list[Memory]:
    """Add hits within both this fetch's share and the turn's cumulative evidence budget."""
    cap = budget if total_budget is None else total_budget
    added: list[Memory] = []
    for index, hit in enumerate(hits):
        if hit.channel == "unstated" or hit.event_id in pack:
            continue
        lines = list(hit.evidence)
        note = episode if index == 0 and episode else ""
        summary = hit.summary
        if summary_limit is not None:
            summary = clip(summary, summary_limit)
        while True:
            item = pack.add(hit.event_id, hit.anchor, hit.channel, summary,
                            tuple((speaker, text) for _, speaker, text in sorted(lines)), note)
            if (estimate_tokens(pack.render([*added, item])) <= budget
                    and estimate_tokens(pack.render()) <= cap):
                added.append(item)
                break
            pack.pop()
            if note:
                note = ""
            elif lines:
                lines.pop()
            else:
                break
    return added


def fill_fact_adaptive(pack: EvidencePack, hits: list[Hit], episode: str | None,
                       budget: int) -> tuple[list[Memory], int]:
    """Widen a crowded initial fact pack while retaining selected source lines."""
    if pack.items or not 900 <= budget < 1200:
        return fill(pack, hits, episode, budget, total_budget=budget), budget
    added = fill(pack, hits, episode, budget, total_budget=budget)
    available = {hit.event_id for hit in hits if hit.channel != "unstated"}
    if len(added) >= len(available):
        return added, budget
    original = pack.items[:]
    pack.items.clear()
    expanded = min(1200, budget + 300)
    compact = fill(pack, hits, None, expanded, total_budget=expanded, summary_limit=220)
    if len(compact) <= len(added):
        pack.items[:] = original
        return added, budget
    return compact, expanded


def rank_reason_hits(hits: list[Hit], topics: tuple[str, ...]) -> list[Hit]:
    """Prefer firsthand statements of purpose while retaining retrieval relevance."""
    def score(hit: Hit) -> float:
        body = hit.topic + " " + hit.summary
        cues = sum(cue in body for cue in RATIONALE_CUES)
        named = sum(name in body for name in topics)
        firsthand = hit.channel in ("experienced", "witnessed", "told", "recalled")
        return 2.0 * min(cues, 4) + 1.5 * min(named, 2) + (1.0 if firsthand else 0.0) + hit.score

    return sorted(hits, key=score, reverse=True)


def fill_overview(pack: EvidencePack, hits: list[Hit], budget: int) -> list[Memory]:
    """Fit short event summaries and original lines inside the shared turn budget."""
    added: list[Memory] = []
    for hit in hits:
        if hit.channel == "unstated" or hit.event_id in pack:
            continue
        for summary_limit, line_limit, line_count in ((65, 85, 2), (50, 65, 2),
                                                       (55, 85, 1), (40, 55, 1)):
            summary = clip(hit.topic + "：" + hit.summary, summary_limit)
            lines = tuple((speaker, clip(text, line_limit))
                          for _, speaker, text in hit.evidence[:line_count])
            item = pack.add(hit.event_id, hit.anchor, hit.channel, summary, lines)
            if estimate_tokens(pack.render()) <= budget:
                added.append(item)
                break
            pack.pop()
    return added


def fill_overview_adaptive(pack: EvidencePack, hits: list[Hit], budget: int) -> tuple[list[Memory], int]:
    """Expand a crowded broad evidence pack only when selected known events do not fit."""
    pending = sum(hit.channel != "unstated" and hit.event_id not in pack for hit in hits)
    added = fill_overview(pack, hits, budget)
    if 900 <= budget < 1200 and len(added) < pending:
        budget = min(1200, budget + 300)
        added.extend(fill_overview(pack, hits, budget))
    return added, budget


def _story_source(anchor: str) -> str:
    title = re.search(r"「([^」]+)」", anchor)
    parts = anchor.split(" · ")
    place = " · ".join(parts[-2:]) if len(parts) > 1 else anchor
    return clip((title.group(1) + " / " if title else "") + place, 36)


def fill_story_adaptive(pack: EvidencePack, hits: list[Hit], budget: int,
                        widen: bool = True) -> tuple[list[Memory], int]:
    """Fit a source-ordered story outline before spending remaining room on original lines."""
    if pack.items:
        return fill_overview_adaptive(pack, hits, budget)
    cap = min(2400, budget + 1500) if widen and 900 <= budget < 2400 else budget
    outline_cap = min(cap, 1600)
    known = [hit for hit in hits if hit.channel != "unstated"]
    collections = {hit.event_id: hit.anchor.split(" · ")[0] for hit in known}
    order = {collection: rank for rank, collection in enumerate(dict.fromkeys(collections.values()))}
    ordered = sorted(known, key=lambda hit: (order[collections[hit.event_id]], hit.position, hit.event_id))
    for hit in ordered:
        if hit.event_id in pack:
            continue
        summary = _story_source(hit.anchor) + "｜" + clip(
            hit.topic + "：" + hit.summary, 40)
        pack.add(hit.event_id, hit.anchor, hit.channel, summary, ())
        if estimate_tokens(pack.render()) > outline_cap:
            pack.pop()
    by_id = {hit.event_id: hit for hit in known}
    priorities = sorted(range(len(pack.items)),
                        key=lambda index: (-by_id[pack.items[index].event_id].score, index))
    blocked: set[str] = set()
    for line_number in (1, 2, 3, 4):
        for index in priorities:
            item = pack.items[index]
            hit = by_id[item.event_id]
            if (item.event_id in blocked or len(hit.evidence) < line_number
                    or len(item.lines) != line_number - 1):
                continue
            _, speaker, body = hit.evidence[line_number - 1]
            trial = replace(item, lines=(*item.lines, (speaker, clip(body, 95))))
            pack.items[index] = trial
            if estimate_tokens(pack.render()) > cap:
                pack.items[index] = item
                blocked.add(item.event_id)
    effective = cap if estimate_tokens(pack.render()) > budget else budget
    return pack.items[:], effective
