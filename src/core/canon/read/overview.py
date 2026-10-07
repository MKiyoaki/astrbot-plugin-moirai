"""Bounded, source-linked selection of events for broad canon questions."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .lexical import terms
from ..settings import SETTINGS


ACCOUNT = re.compile(
    r"来龙去脉|前因后果|从头|整体经过|一步步|整件事"
    r"|(?:经历|遭遇)(?:了|过)?些?(?:什么|哪些)|(?:如何|怎么|怎样)(?:发展|展开|变化|演变)"
)
TOPIC_ACCOUNT = re.compile(
    r"讲讲|说说|聊聊|概括|大概|大体|经过|经历|那段时间|那阵子|那些年|这些年|那几年|最后怎么样|结局"
    r"|后来(?:怎么样|怎样|如何|又)|发生(?:了|过)?些?什么(?:事情?)?[？?。]*$|出了?什么事"
    r"|都(?:做|干)(?:了|过)?些?(?:什么|哪些)|(?:做|干)(?:了|过)?些(?:什么|哪些)"
    r"|(?:遇到|碰到|面临|卷入|采取)(?:了|过)?些?(?:什么|哪些)"
    r"|哪些(?:事|冲突|危机|行动|交锋|转折|选择|决定|经历|变化)|过得(?:怎么样|如何)"
)
SPECIFIC = re.compile(r"谁|叫什么|名字|全名|哪天|几号|几点|什么时候|说了什么|说过什么|用什么|什么颜色|头衔|生日|几岁|多大|具体")
OVERVIEW_MAX_EVENTS = SETTINGS.overview.max_events
STORY_MAX_EVENTS = SETTINGS.overview.story_max_events
OVERVIEW_MAX_SCENES = SETTINGS.overview.max_scenes
OVERVIEW_MAX_CANDIDATES = SETTINGS.overview.max_candidates


def is_overview(query: str, topic: bool = True) -> bool:
    """Recognize requests for a multi-event account without an extra model call.

    Account wording alone qualifies; looser wording such as 讲讲 or 后来 needs a named topic, and a request
    for one specific datum never does. Callers that already routed the turn keep the default topic=True.
    """
    clean = re.sub(r"\s+", "", query)
    if SPECIFIC.search(clean):
        return False
    return bool(ACCOUNT.search(clean)) or (topic and bool(TOPIC_ACCOUNT.search(clean)))


def is_account(query: str) -> bool:
    return bool(ACCOUNT.search(re.sub(r"\s+", "", query)))


def topic_terms(query: str, generic: frozenset[str]) -> list[str]:
    """Remove broad-question wording before scoring its story topic."""
    clean = TOPIC_ACCOUNT.sub(" ", ACCOUNT.sub(" ", query))
    for phrase in ("那场事件", "是怎么", "是怎样", "怎么", "如何", "哪些",
                   "什么", "事件", "那场", "在", "的", "了", "后", "又"):
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
            return (item.relevance + 0.25 * (novelty - 0.24 * similarity),
                    item.relevance, item.event_id)

        eligible = [item for item in remaining if scenes[item.scene_key] < 3]
        if not eligible:
            break
        picked = max(eligible, key=score)
        chosen.append(picked)
        scenes[picked.scene_key] += 1
        collections[picked.collection_id] += 1
        phases.add((picked.collection_id, picked.phase))
        remaining.remove(picked)
    return [item.event_id for item in chosen]
