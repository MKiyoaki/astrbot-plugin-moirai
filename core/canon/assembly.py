"""One turn's canon evidence: a shared pack and budget for prefetch, tool calls and evaluation."""

from __future__ import annotations

from dataclasses import dataclass

from .gateway import EvidencePack, Memory
from .overview import is_overview
from .packing import (Hit, fill, fill_fact_adaptive, fill_overview_adaptive, fill_story_adaptive,
                      rank_reason_hits)
from .query import TurnPlan, needs_motive_rerank
from .reader import CanonReader, fact_search


@dataclass(frozen=True)
class EvidenceSettings:
    doctor: bool = True
    top_k: int = 5
    evidence_lines: int = 4
    token_budget: int = 900
    as_of: str | None = None


class EvidenceAssembler:
    """Adaptive packing may widen the turn budget; later tool calls must see the widened budget."""

    def __init__(self, reader: CanonReader, plan: TurnPlan, settings: EvidenceSettings) -> None:
        self.reader, self.plan, self.settings = reader, plan, settings
        reader.last_expansion_trace = {}
        player = reader.profile.player
        self.pack = EvidencePack(f"对方（{player}）" if settings.doctor else player, settings.doctor, reader.profile)
        self.pack.when = reader.time_label
        self.pack.recent = reader.is_recent
        self.budget = settings.token_budget
        self.hits: list[Hit] = []
        self.overview_trace: dict | None = None

    def fetch(self, text: str, focus_person: str | None = None, budget: int | None = None,
              prefer_reason: bool = False, adaptive: bool = False) -> list[Memory]:
        settings, plan = self.settings, self.plan
        hits, episode = fact_search(self.reader, text,
                                    top_k=max(settings.top_k, 12) if prefer_reason else settings.top_k,
                                    evidence_lines=settings.evidence_lines,
                                    doctor=settings.doctor, focus_person=focus_person)
        if prefer_reason:
            hits = rank_reason_hits(hits, plan.topics)[:settings.top_k]
            episode = None
        if plan.intent == "reason" and not prefer_reason:
            context = self.reader.expand_context(hits[:2], text, limit=2)
            known = {hit.event_id for hit in hits}
            hits = [*hits[:2], *(hit for hit in context if hit.event_id not in known), *hits[2:]]
            episode = None
        self.hits.extend(hits)
        if adaptive:
            added, self.budget = fill_fact_adaptive(self.pack, hits, episode, self.budget)
            return added
        return fill(self.pack, hits, episode, self.budget if budget is None else budget,
                    total_budget=self.budget)

    def fetch_overview(self, text: str, budget: int | None = None) -> tuple[list[Memory], dict]:
        plan = self.plan
        hits, trace = self.reader.overview_search(
            text, doctor=self.settings.doctor,
            evidence_lines=min(4 if is_overview(text) and not plan.impression else 2,
                               self.settings.evidence_lines),
            personal=plan.impression, contextual=not plan.impression and not is_overview(text))
        self.hits.extend(hits)
        self.overview_trace = trace
        packer = (fill_story_adaptive if not plan.impression and is_overview(text)
                  else fill_overview_adaptive)
        added, self.budget = packer(self.pack, hits, self.budget if budget is None else budget)
        return added, trace

    def prefetch(self) -> None:
        plan = self.plan
        if plan.overview:
            self.fetch_overview(plan.search_query)
        elif plan.lane != "chat":
            subjects = plan.subjects if plan.lane == "status" and len(plan.subjects) > 1 else (None,)
            share = self.budget // len(subjects)
            for subject in subjects:
                self.fetch(plan.search_query, subject, share,
                           prefer_reason=needs_motive_rerank(self.reader, plan),
                           adaptive=len(subjects) == 1 and self.reader.retrieval is not None)

    def facts(self) -> tuple[str, bool]:
        if self.plan.lane != "status":
            return "", False
        contexts = [self.reader.fact_context(subject, as_of=self.settings.as_of)
                    for subject in self.plan.subjects]
        return "\n".join(block for block, _ in contexts if block), all(valid for _, valid in contexts)
