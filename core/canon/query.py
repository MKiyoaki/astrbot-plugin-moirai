"""Turn planning for canon questions: lane, subjects, intent and search wording, without IO beyond alias lookup."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from .context import resolve_name
from .lexical import terms
from .overview import SPECIFIC, is_account, is_overview

if TYPE_CHECKING:
    from .reader import CanonReader


GENERIC_CHARS = frozenset(
    "还记得是什么怎么样了吗呢吧啊呀的地得在有没这那你我他她它们个些时候事情知道觉得想要会能可以说过去上次当时一下"
)
QUERY_PAST = ("那次", "那一次", "上次", "当时", "那时", "那天", "那场", "还记得")
PERSON_REFERENCES = ("她", "他", "那个人")
OTHER_REFERENCES = ("它", "那里", "那座城", "那个地方")
EVENT_REFERENCES = ("那件事", "那次", "那一回")
REASON_MARKERS = ("为什么", "为何", "原因", "缘由", "动机", "目的")
IMPRESSION_MARKERS = ("印象", "看法", "怎么看", "感觉如何")
STATUS_TERMS = (
    "今天", "今晚", "现在", "目前", "最近", "近况", "还在", "还好吗",
    "如今", "怎么样了", "在哪",
)
MAX_SUBJECTS = 3
LOOKUP = ("档案", "资料", "履历", "生日", "身高", "种族", "体检", "病历", "病情", "感染情况", "出身", "作战情报")
RECOUNT = ("经过", "复述", "怎么回事", "之战", "之役", "那一战", "讲讲", "说说", "讲一下", "讲一遍", "详细")
def explicit_quote(query: str) -> str | None:
    """Extract a literal claim only when the question supplies concrete wording."""
    quoted = (re.findall(r'[“「『"]([^”」』"]{4,24})[”」』"]', query)
              if any(word in query for word in ('是不是', '有没有', '是否', '说过', '叫过', '原话', '称呼')) else [])
    marker = re.search(
        r'(?:管.{1,12}?叫|(?:是不是|是否|有没有)叫|被叫做|叫做|叫作|称作|称为|称呼|喊作|说成)'
        r'([一-鿿A-Za-z0-9·]{4,20})[吗呢吧了]?[？?。]*$', query)
    endings = [phrase.strip() for phrase in quoted]
    if marker:
        endings.append(marker.group(1).lstrip('是为作').rstrip('吗呢吧了'))
    for phrase in endings:
        if 4 <= len(phrase) <= 24 and not any(word in phrase for word in (
                '什么', '哪个', '哪句', '谁', '多少', '如何', '那天', '什么时候')):
            return phrase
    return None

def task_of(query: str) -> str:
    """How the evidence is shaped: a recount retells an incident, a lookup reads an archive, a reason names a motive.

    Account wording wins over archive wording, so asking to retell a battle's record is a recount.
    """
    clean = "".join(query.split())
    if is_overview(clean) or any(word in clean for word in RECOUNT):
        return "recount"
    if any(word in clean for word in LOOKUP):
        return "lookup"
    return "reason" if any(marker in clean for marker in REASON_MARKERS) else "fact"


def asks_status(query: str, home_terms: tuple[str, ...] = ()) -> bool:
    return any(term in query for term in (*STATUS_TERMS, *home_terms))

ROUTE_IDF_MASS = 4.2

def distinctive_mass(reader: CanonReader, query: str) -> float:
    """The query's corpus-rare vocabulary mass, scaled by this corpus's rarest term.

    Small talk reaches canon-level dense similarity by matching everyday words the
    corpus also uses; a story question carries terms that are rare within the
    corpus. The ratio stays on one scale across corpus sizes, where the raw
    similarity threshold does not.
    """
    idf = reader.lexical.idf
    if not idf:
        return 0.0
    total = sum(idf[term] for term in dict.fromkeys(terms(query, GENERIC_CHARS)) if term in idf)
    return total / max(idf.values())


@dataclass(frozen=True)
class TurnPlan:
    lane: str
    subjects: tuple[str, ...]
    focus: str | None
    search_query: str
    by_retrieval: bool = False
    overview: bool = False
    reason: bool = False
    impression: bool = False
    topics: tuple[str, ...] = ()
    intent: str = "fact"
    corrections: tuple[tuple[str, str], ...] = ()


def plan_turn(reader: CanonReader, query: str, focus: str | None, as_of: str | None,
              context: tuple[str, ...] = ()) -> TurnPlan:
    """Resolve a short follow-up against named topics before choosing evidence."""
    query, corrections = resolve_name(query, getattr(reader, "alias_names", []), reader.entity_type)
    explicit = reader.topic_mentions(query)
    conversational = any(term in query for term in ("刚才我们", "刚才我说", "我刚才说", "你刚才", "刚才你", "为什么这么觉得", "为啥这么觉得", "我一开始", "我最早", "我最开始"))
    prediction = any(term in query for term in ("接下来", "以后会", "将会", "下一步", "未来会"))
    reason = any(marker in query for marker in REASON_MARKERS)
    impression = any(marker in query for marker in (*IMPRESSION_MARKERS, "感受", "最难的", "你觉得"))
    person_pointer = any(marker in query for marker in PERSON_REFERENCES)
    other_pointer = any(marker in query for marker in OTHER_REFERENCES)
    event_pointer = any(marker in query for marker in EVENT_REFERENCES)
    focus_type = reader.entity_type.get(focus) if focus else None
    points_to_focus = (focus and (event_pointer or (person_pointer and focus_type == "person")
                                  or (other_pointer and focus_type != "person")))
    resolved = focus if points_to_focus and focus not in explicit else None
    mentioned = list(dict.fromkeys([*explicit, *([resolved] if resolved else [])]))
    explicit_person = any(reader.entity_type.get(name) == "person" for name in explicit)
    reason_context = ([name for name in context if name not in mentioned][:2]
                      if reason and len(query) <= 30 and not explicit_person else [])
    subjects = tuple(name for name in mentioned if reader.entity_type.get(name) == "person")[:MAX_SUBJECTS]
    past = any(term in query for term in QUERY_PAST)
    overview = ((is_overview(query, bool(mentioned)) or (impression and bool(mentioned)))
                and not SPECIFIC.search(query)
                and (is_account(query) or not any(term in query for term in ("那次", "那天", "当时"))))
    if conversational:
        lane = "chat"
        overview = False
    elif subjects and (asks_status(query, reader.profile.home_status_terms) or as_of) and not prediction:
        lane = "status"
        overview = False
    elif mentioned or past or overview or reason_context:
        lane = "canon"
    else:
        lane = "chat"
    named_people = [name for name in explicit if reader.entity_type.get(name) == "person"]
    next_focus = resolved or (focus if reason_context else None) or (named_people[0] if len(named_people) == 1 else
                              explicit[0] if len(explicit) == 1 else None)
    topics = tuple(dict.fromkeys([*mentioned, *reason_context]))
    additions = [name for name in [resolved, *reason_context] if name and name not in query]
    search_query = " ".join([query, *additions, *(["原因 目的 动机"] if reason and lane == "canon" else [])])
    intent = ("conversation" if conversational else "prediction" if prediction else
              "impression" if impression else "overview" if overview else "reason" if reason else
              "chat" if lane == "chat" else "fact")
    return TurnPlan(lane, subjects, next_focus, search_query,
                    overview=overview, reason=reason, impression=impression, topics=topics,
                    intent=intent, corrections=tuple(corrections.items()))


def needs_motive_rerank(reader: CanonReader, plan: TurnPlan) -> bool:
    """Use purpose ranking only when a question names both sides of a broad relationship."""
    return (plan.reason and not plan.subjects and len(plan.topics) >= 2
            and any(reader.entity_type.get(name) in ("place", "faction", "organization")
                    for name in plan.topics))


def route(reader: CanonReader, plan: TurnPlan, query: str, doctor: bool) -> TurnPlan:
    """A story question without names or time words still reaches canon when retrieval is confident."""
    if plan.lane != "chat" or plan.intent == "conversation" or reader.retrieval is None:
        return plan
    probe = reader.semantic(reader.without_self(query), doctor)
    if reader.retrieval.confident(probe) and distinctive_mass(reader, probe) >= ROUTE_IDF_MASS:
        return replace(plan, lane="canon", by_retrieval=True)
    return plan
