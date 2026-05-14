"""RecallManager: retrieval + injection pipeline.

Owns the full hot-path from raw query to ProviderRequest mutation:
  1. Hybrid search (BM25 + vector via HybridRetriever.search_raw)
  2. RRF score computation
  3. Weighted re-ranking: relevance × RRF + salience + recency decay
  4. Token-budget-aware formatting
  5. Injection into req.system_prompt / req.prompt / req.contexts
  6. Auto-clear of previous injection markers
"""
from __future__ import annotations

import asyncio
import re
import time
from math import exp, log
from typing import TYPE_CHECKING, Any

from ..config import (
    FAKE_TOOL_CALL_ID_PREFIX,
    MEMORY_INJECTION_FOOTER,
    MEMORY_INJECTION_HEADER,
)
from ..domain.models import Event, EventType
from ..utils.formatter import format_events_for_fake_tool_call, format_events_for_prompt, format_persona_for_prompt
from ..retrieval.rrf import rrf_scores
from .base import BaseRecallManager
from ..social.soul_state import SoulState, apply_decay, apply_tanh_elastic, format_soul_for_prompt, from_config

if TYPE_CHECKING:
    from ..config import InjectionConfig, RetrievalConfig, SoulConfig
    from ..retrieval.hybrid import HybridRetriever
    from ..repository.base import PersonaRepository

_LOG2 = log(2)

# Keywords that signal a broad / temporal / summary-type query (macro layer).
_MACRO_KWS = frozenset([
    "最近", "这段时间", "这周", "本周", "这个月", "上周", "上个月",
    "总结", "概括", "整体", "大概", "发生了什么", "有什么事", "都做了什么",
    "最近怎么样", "一段时间", "过去", "回顾",
])

# Keywords that signal a specific / entity-focused query (micro layer).
_MICRO_KWS = frozenset([
    "具体", "说了什么", "怎么说", "什么时候", "为什么", "怎么了", "详细",
    "哪次", "那次", "上次", "那时候",
])


def _classify_granularity(query: str) -> str:
    """Return 'macro', 'micro', or 'both' based on keyword overlap."""
    macro_hits = sum(1 for kw in _MACRO_KWS if kw in query)
    micro_hits = sum(1 for kw in _MICRO_KWS if kw in query)
    if macro_hits > micro_hits:
        return "macro"
    if micro_hits > macro_hits:
        return "micro"
    return "both"

_INJECTION_RE = re.compile(
    re.escape(MEMORY_INJECTION_HEADER) + r".*?" + re.escape(MEMORY_INJECTION_FOOTER),
    re.DOTALL,
)

_DIM_NAMES = {"O": "开放性", "C": "尽责性", "E": "外向性", "A": "宜人性", "N": "神经质"}


def _truncate(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def _event_debug_summary(ev: Event) -> dict[str, str]:
    event_type = getattr(ev, "event_type", "")
    label = "叙事" if event_type == EventType.NARRATIVE or str(event_type) == "narrative" else "情节"
    summary = getattr(ev, "summary", "") or ""
    return {
        "type": str(event_type),
        "label": label,
        "topic": _truncate(getattr(ev, "topic", "") or "未命名记忆", 48),
        "summary": _truncate(summary, 80) if summary else "",
    }


def _persona_debug_summary(persona: object | None) -> dict | None:
    if persona is None:
        return None
    attrs = getattr(persona, "persona_attrs", {}) or {}
    if not isinstance(attrs, dict):
        return None
    bf = attrs.get("big_five", {})
    if not isinstance(bf, dict) or not bf:
        return None

    dimensions: list[dict[str, object]] = []
    for dim, label in _DIM_NAMES.items():
        value = bf.get(dim)
        if value is None:
            continue
        try:
            pct = round((float(value) + 1.0) / 2.0 * 100)
        except (TypeError, ValueError):
            continue
        dimensions.append({"key": dim, "label": label, "percent": pct})

    if not dimensions:
        return None
    return {
        "name": getattr(persona, "primary_name", None) or "用户",
        "dimensions": dimensions,
    }


def _soul_debug_summary(state: object | None) -> dict[str, float] | None:
    if state is None:
        return None
    keys = ("recall_depth", "impression_depth", "expression_desire", "creativity")
    values: dict[str, float] = {}
    for key in keys:
        value = getattr(state, key, None)
        if value is None:
            continue
        try:
            values[key] = round(float(value), 2)
        except (TypeError, ValueError):
            continue
    return values or None


def _build_injection_debug(
    *,
    position: str,
    events: list[Event],
    injected: bool,
    memory_injected: bool,
    persona: object | None = None,
    soul_state: object | None = None,
) -> dict:
    return {
        "position": position,
        "injected": injected,
        "memory": {
            "injected": memory_injected,
            "count": len(events) if memory_injected else 0,
            "events": [_event_debug_summary(ev) for ev in events[:8]] if memory_injected else [],
        },
        "persona": _persona_debug_summary(persona),
        "soul": _soul_debug_summary(soul_state),
        "hidden": [
            "完整 System Prompt",
            "后台任务 prompt",
            "完整 Persona 内容",
            "Skill Rules",
            "Big Five evidence 原文",
        ],
    }


class RecallManager(BaseRecallManager):
    """Retrieval + injection pipeline driven by RetrievalConfig and InjectionConfig."""

    def __init__(
        self,
        retriever: HybridRetriever,
        retrieval_config: RetrievalConfig,
        injection_config: InjectionConfig,
        persona_repo: PersonaRepository | None = None,
        soul_config: SoulConfig | None = None,
    ) -> None:
        super().__init__()
        self._retriever = retriever
        self._rcfg = retrieval_config
        self._icfg = injection_config
        self._persona_repo = persona_repo
        self._soul_cfg = soul_config
        self._soul_states: dict[str, SoulState] = {}
        self._last_recall_debug: dict[str, dict] = {}
        self._last_injection_debug: dict[str, dict] = {}

    def pop_recall_debug(self, session_id: str) -> dict | None:
        """Return and remove the last recall debug info for a session."""
        return self._last_recall_debug.pop(session_id, None)

    def pop_injection_debug(self, session_id: str) -> dict | None:
        """Return and remove the last sanitized injection debug info for a session."""
        return self._last_injection_debug.pop(session_id, None)

    def get_soul_states(self) -> dict[str, Any]:
        """Return all active soul states as a dict of dicts."""
        return {sid: state.__dict__.copy() for sid, state in self._soul_states.items()}

    async def recall(self, query: str, group_id: str | None = None) -> list[Event]:
        """Return re-ranked events for injection.

        Uses a two-tier hierarchical strategy when narrative events exist:
        1. Macro layer: narrative daily summaries
        2. Episode layer: raw conversation events
        Allocation ratio depends on query granularity (classified via keywords).
        """
        from ..utils.perf import performance_timer
        cfg = self._rcfg
        granularity = _classify_granularity(query)

        # Determine per-tier limits based on granularity
        if granularity == "macro":
            narrative_limit = min(4, cfg.final_limit)
            episode_limit = max(cfg.final_limit - 2, 1)
        elif granularity == "micro":
            narrative_limit = 1
            episode_limit = cfg.final_limit
        else:  # "both"
            narrative_limit = min(2, cfg.final_limit)
            episode_limit = cfg.final_limit

        async with performance_timer("recall_search"):
            # Parallel searches for each tier
            narrative_task = self._retriever.search_raw(
                query, active_only=cfg.active_only, group_id=group_id,
                event_type=EventType.NARRATIVE,
            )
            episode_task = self._retriever.search_raw(
                query, active_only=cfg.active_only, group_id=group_id,
                event_type=EventType.EPISODE,
            )
            (narrative_bm25, narrative_vec), (bm25, vec) = await asyncio.gather(
                narrative_task, episode_task
            )
        
        import logging
        _log = logging.getLogger(__name__)
        _log.debug(
            "[RecallManager] query: %r, granularity: %s, group_id: %r",
            query, granularity, group_id,
        )
        _log.debug("[RecallManager] BM25 hits: %d, Vec hits: %d", len(bm25), len(vec))

        async with performance_timer("recall_rerank"):
            now = time.time()

            def _rank_tier(
                bm25_tier: list[Event], vec_tier: list[Event], limit: int
            ) -> list[Event]:
                """RRF + multi-signal rerank for a single event type tier."""
                if not bm25_tier and cfg.vector_fallback_enabled and vec_tier:
                    tier_candidates = vec_tier
                    tier_scores: dict[str, float] = {
                        e.event_id: 1.0 / (cfg.rrf_k + 1) for e in vec_tier
                    }
                else:
                    tier_scores = rrf_scores([bm25_tier, vec_tier], k=cfg.rrf_k)
                    seen: set[str] = set()
                    tier_candidates = []
                    for e in bm25_tier + vec_tier:
                        if e.event_id not in seen:
                            seen.add(e.event_id)
                            tier_candidates.append(e)
                if not tier_candidates:
                    return []
                max_rrf = max(tier_scores.values()) if tier_scores else 1.0

                def _score(ev: Event) -> float:
                    days = (now - ev.end_time) / 86400.0
                    recency = exp(-_LOG2 * days / cfg.recency_half_life_days)
                    rrf = tier_scores.get(ev.event_id, 0.0)
                    return (
                        cfg.relevance_weight * rrf / max_rrf
                        + cfg.salience_weight * ev.salience
                        + cfg.recency_weight * recency
                    )

                return sorted(tier_candidates, key=_score, reverse=True)[:limit]

            narrative_anchors = _rank_tier(narrative_bm25, narrative_vec, narrative_limit)
            episode_anchors = _rank_tier(bm25, vec, episode_limit)

            if not narrative_anchors and not episode_anchors:
                return []

            # Build deduped result: narratives first, then episode thread expansion
            result_list: list[Event] = []
            seen_ids: set[str] = set()

            def _add_event_sync(ev: Event) -> None:
                if ev.event_id not in seen_ids:
                    result_list.append(ev)
                    seen_ids.add(ev.event_id)

            for n_ev in narrative_anchors:
                _add_event_sync(n_ev)

        # Episode thread expansion (async I/O outside performance_timer)
        if episode_anchors:
            top_ep = episode_anchors[0]
            _add_event_sync(top_ep)
            async with performance_timer("recall_expand"):
                if top_ep.inherit_from:
                    for parent_id in top_ep.inherit_from:
                        parent = await self._retriever._event_repo.get(parent_id)
                        if parent:
                            _add_event_sync(parent)
                children = await self._retriever._event_repo.get_children(top_ep.event_id)
                for child in children:
                    _add_event_sync(child)
            for anchor in episode_anchors[1:]:
                _add_event_sync(anchor)

        return result_list

    async def recall_and_inject(
        self,
        query: str,
        req: object,
        session_id: str,
        group_id: str | None = None,
        sender_uid: str | None = None,
        store_debug: bool = False,
        store_injection_debug: bool = False,
    ) -> int:
        """Recall and inject memory into req. Returns the number of events injected."""
        from ..utils.perf import performance_timer, tracker
        async with performance_timer("recall"):
            if self._icfg.auto_clear:
                self.clear_previous_injection(req)

            events = await self.recall(query, group_id=group_id)
            await tracker.record_hit("recall", len(events))

            if store_debug:
                self._last_recall_debug[session_id] = {
                    "query": query,
                    "granularity": _classify_granularity(query),
                    "total": len(events),
                    "events": [
                        {"topic": e.topic, "type": e.event_type}
                        for e in events[:8]
                    ],
                    "position": self._icfg.position,
                }

            async with performance_timer("recall_inject"):
                position = self._icfg.position
                token_budget = self._icfg.token_budget

            if position == "fake_tool_call":
                if not events:
                    if store_injection_debug:
                        self._last_injection_debug[session_id] = _build_injection_debug(
                            position=position,
                            events=[],
                            injected=False,
                            memory_injected=False,
                        )
                    return 0
                messages = format_events_for_fake_tool_call(
                    events, query, token_budget=token_budget
                )
                if store_injection_debug:
                    self._last_injection_debug[session_id] = _build_injection_debug(
                        position=position,
                        events=events,
                        injected=bool(messages),
                        memory_injected=bool(messages),
                    )
                if messages:
                    contexts = getattr(req, "contexts", None)
                    if contexts is None:
                        return 0
                    contexts.extend(messages)
                return len(events) if messages else 0

            # Build memory body (may be empty if no events).
            body = format_events_for_prompt(events, token_budget=token_budget) if events else ""

            # OCEAN persona injection — soft stylistic heuristic, system_prompt only.
            persona_segment = ""
            persona_obj = None
            if sender_uid and self._persona_repo and position in ("system_prompt", None, ""):
                try:
                    persona_obj = await self._persona_repo.get(sender_uid)
                    if persona_obj:
                        persona_segment = format_persona_for_prompt(persona_obj)
                except Exception:
                    pass

            # Soul Layer injection — short-term emotional state.
            soul_segment = ""
            soul_state_for_debug = None
            if self._soul_cfg and self._soul_cfg.enabled:
                state = self._soul_states.get(session_id)
                if state is None:
                    state = from_config(self._soul_cfg)
                # Decay first, then boost recall_depth based on how many events were found.
                state = apply_decay(state, self._soul_cfg.decay_rate)
                delta_recall = min(5.0, len(events) * 0.5)
                state = SoulState(
                    recall_depth=apply_tanh_elastic(state.recall_depth, delta_recall),
                    impression_depth=state.impression_depth,
                    expression_desire=state.expression_desire,
                    creativity=state.creativity,
                )
                self._soul_states[session_id] = state
                soul_segment = format_soul_for_prompt(state)
                if soul_segment:
                    soul_state_for_debug = state

            # Nothing to inject — exit early only if all three segments are empty.
            if not body and not persona_segment and not soul_segment:
                if store_injection_debug:
                    self._last_injection_debug[session_id] = _build_injection_debug(
                        position=position,
                        events=[],
                        injected=False,
                        memory_injected=False,
                    )
                return 0

            # Assemble injection block.
            segments: list[str] = []
            if body:
                segments.append(body)
            if persona_segment:
                segments.append(persona_segment)
            if soul_segment:
                segments.append(soul_segment)

            wrapped = (
                MEMORY_INJECTION_HEADER
                + "\n"
                + "\n\n".join(segments)
                + "\n"
                + MEMORY_INJECTION_FOOTER
            )

            if store_injection_debug:
                self._last_injection_debug[session_id] = _build_injection_debug(
                    position=position,
                    events=events,
                    injected=True,
                    memory_injected=bool(body),
                    persona=persona_obj if persona_segment else None,
                    soul_state=soul_state_for_debug,
                )

            if position == "system_prompt":
                sep = "\n\n" if getattr(req, "system_prompt", "") else ""
                req.system_prompt = getattr(req, "system_prompt", "") + sep + wrapped
            elif position == "user_message_before":
                req.prompt = wrapped + "\n\n" + getattr(req, "prompt", "")
            elif position == "user_message_after":
                req.prompt = getattr(req, "prompt", "") + "\n\n" + wrapped
            else:
                sep = "\n\n" if getattr(req, "system_prompt", "") else ""
                req.system_prompt = getattr(req, "system_prompt", "") + sep + wrapped

            return len(events)

    def clear_previous_injection(self, req: object) -> int:
        """Strip all injection markers from req. Returns count of blocks removed."""
        removed = 0

        # Clear system_prompt
        sp = getattr(req, "system_prompt", None)
        if sp:
            new_sp, n = _INJECTION_RE.subn("", sp)
            if n:
                req.system_prompt = new_sp.strip()
                removed += n

        # Clear prompt
        prompt = getattr(req, "prompt", None)
        if prompt:
            new_prompt, n = _INJECTION_RE.subn("", prompt)
            if n:
                req.prompt = new_prompt.strip()
                removed += n

        # Clear contexts: remove string injection blocks and fake tool call pairs
        contexts = getattr(req, "contexts", None)
        if contexts is not None:
            cleaned: list = []
            skip_next = False
            for msg in contexts:
                if skip_next:
                    skip_next = False
                    continue
                if isinstance(msg, dict):
                    role = msg.get("role")
                    # Detect assistant fake-tool-call message
                    if role == "assistant":
                        tool_calls = msg.get("tool_calls") or []
                        if any(
                            isinstance(tc, dict)
                            and tc.get("id", "").startswith(FAKE_TOOL_CALL_ID_PREFIX)
                            for tc in tool_calls
                        ):
                            skip_next = True
                            removed += 1
                            continue
                    # Detect orphaned tool result message
                    if role == "tool" and msg.get("tool_call_id", "").startswith(
                        FAKE_TOOL_CALL_ID_PREFIX
                    ):
                        removed += 1
                        continue
                    # Strip injection markers from string content fields
                    content = msg.get("content")
                    if isinstance(content, str) and MEMORY_INJECTION_HEADER in content:
                        new_content, n = _INJECTION_RE.subn("", content)
                        if n:
                            msg = dict(msg)
                            msg["content"] = new_content.strip()
                            removed += n
                cleaned.append(msg)

            contexts[:] = cleaned

        return removed
