"""Bounded, source-linked selection of events for broad canon questions."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .lexical import terms


OVERVIEW_PATTERNS = (
    "大体发生了什么", "经历了哪些", "卷入了哪些", "面临哪些",
    "采取了哪些", "如何发展", "怎么变化", "如何展开", "如何一步步",
    "是怎样袭击", "是怎样推动", "怎么撤离", "面临什么处境",
    "采取了什么行动", "遭遇了什么", "怎样救助", "那段时间",
    "有哪些重大转折", "后来面临了哪些", "来龙去脉", "前因后果",
    "从头到尾", "整体经过", "主要转折", "都做了些什么", "整场战事",
    "整件事",
)
OVERVIEW_MAX_EVENTS = 10
OVERVIEW_MAX_SCENES = 18
OVERVIEW_MAX_CANDIDATES = 160


def is_overview(query: str) -> bool:
    """Recognize requests for a multi-event account without an extra model call."""
    clean = re.sub(r"\s+", "", query)
    return "具体" not in clean and any(pattern in clean for pattern in OVERVIEW_PATTERNS)


def topic_terms(query: str, generic: frozenset[str]) -> list[str]:
    """Remove broad-question wording before scoring its story topic."""
    clean = query
    for phrase in ("大体发生了什么", "那场事件", "那段时间", "发生了什么",
                   "经历了哪些", "是怎么", "是怎样", "怎么", "如何", "哪些",
                   "什么", "后来", "事件", "那场", "在", "的", "了", "后", "又"):
        clean = clean.replace(phrase, " ")
    return terms(clean, generic)


@dataclass(frozen=True)
class OverviewCandidate:
    event_id: str
    scene_key: str
    collection_id: str
    relevance: float
    phase: int
    text: str


def select_events(candidates: list[OverviewCandidate], *, limit: int = OVERVIEW_MAX_EVENTS,
                  pinned_collection: str | None = None) -> list[str]:
    """Prefer separate scenes and plot phases while keeping relevance decisive."""
    if pinned_collection:
        candidates = [item for item in candidates if item.collection_id == pinned_collection]
    chosen: list[OverviewCandidate] = []
    scenes: Counter[str] = Counter()
    collections: Counter[str] = Counter()
    phases: set[tuple[str, int]] = set()
    term_sets = {item.event_id: set(terms(item.text)) for item in candidates}
    remaining = list(candidates)
    while remaining and len(chosen) < limit:
        def score(item: OverviewCandidate) -> tuple[float, float, str]:
            novelty = (0.22 if not scenes[item.scene_key] else -0.35 * scenes[item.scene_key])
            novelty += 0.12 if not collections[item.collection_id] else 0.0
            novelty += 0.13 if (item.collection_id, item.phase) not in phases else 0.0
            words = term_sets[item.event_id]
            similarity = max((len(words & term_sets[other.event_id]) / max(1, len(words | term_sets[other.event_id]))
                              for other in chosen), default=0.0)
            return (item.relevance + novelty - 0.24 * similarity, item.relevance, item.event_id)

        eligible = [item for item in remaining if scenes[item.scene_key] < 2]
        if not eligible:
            break
        picked = max(eligible, key=score)
        chosen.append(picked)
        scenes[picked.scene_key] += 1
        collections[picked.collection_id] += 1
        phases.add((picked.collection_id, picked.phase))
        remaining.remove(picked)
    return [item.event_id for item in chosen]
