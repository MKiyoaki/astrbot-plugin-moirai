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
import dataclasses
import logging
import re
import time
from math import exp, log
from typing import TYPE_CHECKING, Any

from ..config import (
    FAKE_TOOL_CALL_ID_PREFIX,
    MEMORY_INJECTION_FOOTER,
    MEMORY_INJECTION_HEADER,
)
from ..domain.models import Event, EventType, MessageRef
from ..utils.formatter import (
    format_events_for_fake_tool_call,
    format_events_for_prompt_safe,
    format_persona_for_prompt,
)
from ..retrieval.rrf import rrf_scores
from .base import BaseRecallManager
from ..utils.injection_compat import resolve_injection_position
from ..social.soul_state import SoulState, format_soul_for_prompt, from_config, update_from_signals

if TYPE_CHECKING:
    from ..config import InjectionConfig, RetrievalConfig, SoulConfig
    from ..retrieval.hybrid import HybridRetriever
    from ..repository.base import ImpressionRepository, PersonaRepository, RawMessageRepository

_LOG2 = log(2)
_RAW_DETAIL_PER_EVENT = 8

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


def _impression_score(imp: object) -> float:
    try:
        confidence = float(getattr(imp, "confidence", 0.0) or 0.0)
        affect = abs(float(getattr(imp, "affect_intensity", 0.0) or 0.0))
        benevolence = abs(float(getattr(imp, "benevolence", 0.0) or 0.0))
        power = abs(float(getattr(imp, "power", 0.0) or 0.0))
    except (TypeError, ValueError):
        return 0.0
    return confidence * 0.55 + affect * 0.2 + benevolence * 0.15 + power * 0.1


def _build_injection_debug(
    *,
    position: str,
    events: list[Event],
    injected: bool,
    memory_injected: bool,
    persona: object | None = None,
    relation: dict | None = None,
    soul_state: object | None = None,
    configured_position: str | None = None,
    compat_reason: str = "",
) -> dict:
    result: dict = {"position": position}
    if configured_position and configured_position != position:
        result["configured_position"] = configured_position
        result["compat_downgrade"] = compat_reason
    return {
        **result,
        "injected": injected,
        "memory": {
            "injected": memory_injected,
            "count": len(events) if memory_injected else 0,
            "events": [_event_debug_summary(ev) for ev in events[:8]] if memory_injected else [],
        },
        "persona": _persona_debug_summary(persona),
        "relation": relation,
        "soul": _soul_debug_summary(soul_state),
        "hidden": [
            "完整 System Prompt",
            "后台任务 prompt",
            "完整 Persona 内容",
            "Full social impression evidence",
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
        impression_repo: ImpressionRepository | None = None,
        soul_config: SoulConfig | None = None,
        raw_message_repo: RawMessageRepository | None = None,
    ) -> None:
        super().__init__()
        self._retriever = retriever
        self._rcfg = retrieval_config
        self._icfg = injection_config
        self._persona_repo = persona_repo
        self._impression_repo = impression_repo
        self._raw_message_repo = raw_message_repo
        self._soul_cfg = soul_config
        self._soul_states: dict[str, SoulState] = {}
        self._soul_state_accessed: dict[str, float] = {}
        self._soul_states_ttl_hours: float = (
            soul_config.states_ttl_hours if soul_config is not None else 24.0
        )
        self._last_recall_debug: dict[str, dict] = {}
        self._last_injection_debug: dict[str, dict] = {}
        self._last_injected_ids: dict[str, list[str]] = {}

    async def _hydrate_raw_details(self, events: list[Event]) -> list[Event]:
        if self._raw_message_repo is None or not events:
            return events

        async def _hydrate(event: Event) -> Event:
            try:
                raw_messages = await self._raw_message_repo.list_by_event(event.event_id)
            except Exception:
                return event
            refs = [
                MessageRef(
                    sender_uid=message.sender_uid,
                    timestamp=message.created_at,
                    content_hash=message.content_hash,
                    content_preview=message.text[:160],
                    message_id=message.message_id,
                )
                for message in raw_messages[:_RAW_DETAIL_PER_EVENT]
                if (message.text or "").strip()
            ]
            if not refs:
                return event
            return dataclasses.replace(event, interaction_flow=refs)

        hydrated = await asyncio.gather(
            *(_hydrate(event) for event in events),
            return_exceptions=True,
        )
        result: list[Event] = []
        for original, item in zip(events, hydrated):
            result.append(original if isinstance(item, Exception) else item)
        return result

    def pop_recall_debug(self, session_id: str) -> dict | None:
        """Return and remove the last recall debug info for a session."""
        return self._last_recall_debug.pop(session_id, None)

    def pop_injection_debug(self, session_id: str) -> dict | None:
        """Return and remove the last sanitized injection debug info for a session."""
        return self._last_injection_debug.pop(session_id, None)

    def get_last_injected_ids(self, session_id: str) -> list[str]:
        """Return the event IDs injected in the most recent recall_and_inject for a session."""
        return self._last_injected_ids.get(session_id, [])

    async def bump_salience_on_use(
        self,
        event_ids: list[str],
        response_text: str,
        boost: float = 0.05,
    ) -> None:
        """Increase salience for events whose tags overlap with response_text.

        Events with empty chat_content_tags are always bumped (no filter basis).
        Events with tags that have no overlap with response_text are skipped.
        """
        import time as _time
        event_repo = self._retriever._event_repo
        now = _time.time()
        response_lower = response_text.lower()

        for eid in event_ids:
            event = await event_repo.get(eid)
            if event is None:
                continue
            tags = event.chat_content_tags
            if tags and not any(tag.lower() in response_lower for tag in tags):
                continue
            new_salience = min(1.0, event.salience + boost)
            await event_repo.update_salience(eid, new_salience)
            await event_repo.update_last_accessed(eid, now)
            await event_repo.increment_access_count(eid)

    def get_soul_states(self) -> dict[str, Any]:
        """Return all active soul states as a dict of dicts."""
        return {sid: state.__dict__.copy() for sid, state in self._soul_states.items()}

    def _evict_soul_states(self) -> None:
        """Remove soul states that have not been accessed within the TTL."""
        if not self._soul_states:
            return
        cutoff = time.time() - self._soul_states_ttl_hours * 3600
        stale = [
            sid for sid, t in self._soul_state_accessed.items() if t < cutoff
        ]
        for sid in stale:
            self._soul_states.pop(sid, None)
            self._soul_state_accessed.pop(sid, None)

    async def _persona_label(self, uid: str) -> str:
        if not uid:
            return "unknown"
        if self._persona_repo is not None:
            try:
                persona = await self._persona_repo.get(uid)
                if persona is not None:
                    name = getattr(persona, "primary_name", None)
                    if name:
                        return str(name)
            except Exception:
                pass
        return uid

    async def _build_relation_segment(
        self,
        *,
        sender_uid: str | None,
        group_id: str | None,
        bot_persona_name: str | None,
        position: str,
    ) -> tuple[str, dict | None]:
        if (
            not sender_uid
            or self._impression_repo is None
            or position not in ("system_prompt", None, "")
            or not self._icfg.impression_injection_enabled
            or self._icfg.impression_injection_max_items <= 0
        ):
            return "", None

        scope = group_id or "global"
        try:
            subject_rows, observer_rows = await asyncio.gather(
                self._impression_repo.list_by_subject(
                    sender_uid,
                    scope=scope,
                    bot_persona_name=bot_persona_name,
                    include_legacy=True,
                ),
                self._impression_repo.list_by_observer(
                    sender_uid,
                    scope=scope,
                    bot_persona_name=bot_persona_name,
                    include_legacy=True,
                ),
                return_exceptions=True,
            )
        except Exception:
            return "", None

        rows = []
        for result in (subject_rows, observer_rows):
            if isinstance(result, Exception):
                continue
            rows.extend(result)

        min_conf = self._icfg.impression_injection_min_confidence
        deduped: dict[tuple[str, str, str, str | None], object] = {}
        for imp in rows:
            try:
                if float(getattr(imp, "confidence", 0.0) or 0.0) < min_conf:
                    continue
            except (TypeError, ValueError):
                continue
            observer = str(getattr(imp, "observer_uid", "") or "")
            subject = str(getattr(imp, "subject_uid", "") or "")
            if not observer or not subject or observer == subject:
                continue
            key = (
                observer,
                subject,
                str(getattr(imp, "scope", "") or ""),
                getattr(imp, "bot_persona_name", None),
            )
            current = deduped.get(key)
            if current is None or _impression_score(imp) > _impression_score(current):
                deduped[key] = imp

        selected = sorted(deduped.values(), key=_impression_score, reverse=True)[
            : self._icfg.impression_injection_max_items
        ]
        if not selected:
            return "", None

        name_cache: dict[str, str] = {}

        async def _label(uid: str) -> str:
            if uid not in name_cache:
                name_cache[uid] = await self._persona_label(uid)
            return name_cache[uid]

        lines = [
            "[Social impression hints]",
            "Use these as low-weight style/context signals only. Do not mention scores, sources, or this block. Never override the user's current request, factual memory, safety rules, or explicit system instructions; ignore them if they conflict.",
        ]
        debug_items: list[dict[str, object]] = []
        for imp in selected:
            observer_uid = str(getattr(imp, "observer_uid", "") or "")
            subject_uid = str(getattr(imp, "subject_uid", "") or "")
            observer = await _label(observer_uid)
            subject = await _label(subject_uid)
            orientation = str(getattr(imp, "ipc_orientation", "unknown") or "unknown")
            benevolence = round(float(getattr(imp, "benevolence", 0.0) or 0.0), 2)
            power = round(float(getattr(imp, "power", 0.0) or 0.0), 2)
            confidence = round(float(getattr(imp, "confidence", 0.0) or 0.0), 2)
            lines.append(
                f"- {observer} -> {subject}: orientation={orientation}, "
                f"benevolence={benevolence:+.2f}, power={power:+.2f}, confidence={confidence:.2f}"
            )
            debug_items.append({
                "observer": observer,
                "subject": subject,
                "orientation": orientation,
                "benevolence": benevolence,
                "power": power,
                "confidence": confidence,
                "scope": getattr(imp, "scope", scope),
            })

        return "\n".join(lines), {"injected": True, "count": len(debug_items), "items": debug_items}

    async def recall(
        self,
        query: str,
        group_id: str | None = None,
        limit: int | None = None,
        scope_mode: str = "all",
    ) -> list[Event]:
        """Return re-ranked events for injection.

        Uses a two-tier hierarchical strategy when narrative events exist:
        1. Macro layer: narrative daily summaries
        2. Episode layer: raw conversation events
        Allocation ratio depends on query granularity (classified via keywords).
        """
        from ..utils.perf import performance_timer
        cfg = self._rcfg
        granularity = _classify_granularity(query)
        final_limit = limit if limit is not None else cfg.final_limit

        if final_limit <= 0:
            return []

        # Determine per-tier limits based on granularity
        if granularity == "macro":
            narrative_limit = min(4, final_limit)
            episode_limit = max(final_limit - 2, 1)
        elif granularity == "micro":
            narrative_limit = 1
            episode_limit = final_limit
        else:  # "both"
            narrative_limit = min(2, final_limit)
            episode_limit = final_limit

        async with performance_timer("recall_search"):
            _log = logging.getLogger(__name__)
            event_repo = self._retriever._event_repo
            encoder = self._retriever._encoder
            enc_dim = encoder.dim
            bm25_limit = self._retriever._bm25_limit
            vec_limit = self._retriever._vec_limit
            common = dict(
                active_only=cfg.active_only, group_id=group_id, scope_mode=scope_mode
            )

            # Fast pre-flight: skip encode + vector when the DB has no active events.
            # COUNT(*) on an empty SQLite table is ~0.1 ms vs 5 s for an API encode call.
            if enc_dim > 0:
                from ..domain.models import EventStatus
                active_count = await event_repo.count_by_status(EventStatus.ACTIVE)
                if active_count == 0:
                    narrative_bm25, narrative_vec, bm25, vec = [], [], [], []
                    _log.debug("[RecallManager] pre-flight: 0 active events, skipping encode+search")
                    # jump to rerank (which immediately returns [])
                    goto_rerank = True
                else:
                    goto_rerank = False
            else:
                goto_rerank = False

            if not goto_rerank:
                # Run BM25 for both tiers AND encoding in parallel — BM25 needs no embedding.
                async def _bm25(event_type: str) -> list[Event]:
                    return await event_repo.search_fts(
                        query, limit=bm25_limit, event_type=event_type, **common
                    )

                async def _null_encode() -> None:
                    return None
                encode_coro = encoder.encode(query) if enc_dim > 0 else _null_encode()
                (
                    narrative_bm25_raw,
                    episode_bm25_raw,
                    shared_embedding_raw,
                ) = await asyncio.gather(
                    _bm25(EventType.NARRATIVE),
                    _bm25(EventType.EPISODE),
                    encode_coro,
                    return_exceptions=True,
                )

                narrative_bm25 = narrative_bm25_raw if not isinstance(narrative_bm25_raw, Exception) else []
                bm25 = episode_bm25_raw if not isinstance(episode_bm25_raw, Exception) else []
                if isinstance(shared_embedding_raw, Exception):
                    _log.warning("[RecallManager] pre-encode failed: %s", shared_embedding_raw)
                    shared_embedding: list[float] | None = None
                else:
                    shared_embedding = shared_embedding_raw

                # Vector searches run in parallel after embedding is ready.
                if shared_embedding and enc_dim > 0:
                    async def _vec(event_type: str) -> list[Event]:
                        return await event_repo.search_vector(
                            shared_embedding, limit=vec_limit, event_type=event_type, **common
                        )

                    narrative_vec_raw, episode_vec_raw = await asyncio.gather(
                        _vec(EventType.NARRATIVE),
                        _vec(EventType.EPISODE),
                        return_exceptions=True,
                    )
                    narrative_vec = narrative_vec_raw if not isinstance(narrative_vec_raw, Exception) else []
                    vec = episode_vec_raw if not isinstance(episode_vec_raw, Exception) else []
                else:
                    narrative_vec, vec = [], []
        
        _log = logging.getLogger(__name__)
        _log.debug(
            "[RecallManager] query: %r, granularity: %s, group_id: %r, scope_mode: %s",
            query, granularity, group_id, scope_mode,
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
                # Fetch all parents and children in parallel instead of sequentially.
                parent_coros = [self._retriever._event_repo.get(pid) for pid in (top_ep.inherit_from or [])]
                async def _gather_parents() -> list:
                    if not parent_coros:
                        return []
                    return await asyncio.gather(*parent_coros, return_exceptions=True)

                parents_raw, children = await asyncio.gather(
                    _gather_parents(),
                    self._retriever._event_repo.get_children(top_ep.event_id),
                    return_exceptions=True,
                )
                if isinstance(parents_raw, Exception):
                    parents_raw = []
                if isinstance(children, Exception):
                    children = []
                for item in parents_raw:
                    if not isinstance(item, Exception) and item:
                        _add_event_sync(item)
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
        scope_mode: str = "all",
        bot_persona_name: str | None = None,
    ) -> int:
        """Recall and inject memory into req. Returns the number of events injected."""
        from ..utils.perf import performance_timer, tracker
        async with performance_timer("recall"):
            if self._icfg.auto_clear:
                self.clear_previous_injection(req)

            if self._rcfg.final_limit <= 0:
                return 0

            # Resolve position up-front (pure CPU) so we know whether to pre-fetch
            # persona / relation before recall finishes.
            model_name = getattr(req, "model", None)
            position, compat_reason = resolve_injection_position(
                model_name, self._icfg.position
            )
            if compat_reason:
                logger.debug(
                    "injection_compat: downgraded fake_tool_call → %s for model=%r (%s)",
                    position, model_name, compat_reason,
                )
            token_budget = self._icfg.token_budget

            # Pre-fetch persona and relation in parallel with the recall pipeline.
            # Both depend only on sender_uid / group_id which are already available,
            # and the DB queries complete during the encoder's wait time.
            _needs_persona_relation = position in ("system_prompt", None, "")

            async def _prefetch_persona() -> object:
                if not (_needs_persona_relation and sender_uid and self._persona_repo):
                    return None
                try:
                    return await self._persona_repo.get(sender_uid)
                except Exception:
                    return None

            events, persona_obj_pre, relation_result = await asyncio.gather(
                self.recall(query, group_id=group_id, scope_mode=scope_mode),
                _prefetch_persona(),
                self._build_relation_segment(
                    sender_uid=sender_uid,
                    group_id=group_id,
                    bot_persona_name=bot_persona_name,
                    position=position,
                ),
                return_exceptions=True,
            )
            if isinstance(events, Exception):
                events = []
            if isinstance(persona_obj_pre, Exception):
                persona_obj_pre = None
            if isinstance(relation_result, Exception) or not isinstance(relation_result, tuple):
                relation_segment, relation_debug = "", None
            else:
                relation_segment, relation_debug = relation_result

            events = await self._hydrate_raw_details(events)
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

            _inject_t0 = time.perf_counter()
            try:
                if position == "fake_tool_call":
                    if not events:
                        if store_injection_debug:
                            self._last_injection_debug[session_id] = _build_injection_debug(
                                position=position,
                                events=[],
                                injected=False,
                                memory_injected=False,
                                configured_position=self._icfg.position,
                                compat_reason=compat_reason,
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
                            configured_position=self._icfg.position,
                            compat_reason=compat_reason,
                        )
                    if messages:
                        contexts = getattr(req, "contexts", None)
                        if contexts is None:
                            return 0
                        contexts.extend(messages)
                    self._last_injected_ids[session_id] = [e.event_id for e in events]
                    return len(events) if messages else 0

                # Build memory body (may be empty if no events).
                body = format_events_for_prompt_safe(events, token_budget=token_budget) if events else ""

                # OCEAN persona injection — use pre-fetched result.
                persona_segment = ""
                persona_obj = None
                if _needs_persona_relation and persona_obj_pre:
                    try:
                        persona_segment = format_persona_for_prompt(persona_obj_pre)
                        persona_obj = persona_obj_pre if persona_segment else None
                    except Exception:
                        pass

                soul_segment = ""
                soul_state_for_debug = None
                if self._soul_cfg and self._soul_cfg.enabled:
                    self._evict_soul_states()
                    state = self._soul_states.get(session_id)
                    if state is None:
                        state = from_config(self._soul_cfg)
                    # Extract IPC signals from relation_debug (already prefetched).
                    _rel = relation_debug if isinstance(relation_debug, dict) else {}
                    _items = _rel.get("items") or []
                    _ben = (
                        sum(float(it.get("benevolence", 0.0) or 0.0) for it in _items) / len(_items)
                        if _items else 0.0
                    )
                    _pow = (
                        sum(float(it.get("power", 0.0) or 0.0) for it in _items) / len(_items)
                        if _items else 0.0
                    )
                    state = update_from_signals(
                        state,
                        decay_rate=self._soul_cfg.decay_rate,
                        events=events,
                        benevolence=_ben,
                        power=_pow,
                        relation_count=len(_items),
                    )
                    self._soul_states[session_id] = state
                    self._soul_state_accessed[session_id] = time.time()
                    soul_segment = format_soul_for_prompt(state)
                    if soul_segment:
                        soul_state_for_debug = state

                # Nothing to inject — exit early only if all three segments are empty.
                if not body and not persona_segment and not relation_segment and not soul_segment:
                    if store_injection_debug:
                        self._last_injection_debug[session_id] = _build_injection_debug(
                            position=position,
                            events=[],
                            injected=False,
                            memory_injected=False,
                            configured_position=self._icfg.position,
                            compat_reason=compat_reason,
                        )
                    return 0

                # Assemble injection block.
                segments: list[str] = []
                if body:
                    segments.append(body)
                if persona_segment:
                    segments.append(persona_segment)
                if relation_segment:
                    segments.append(relation_segment)
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
                        relation=relation_debug,
                        soul_state=soul_state_for_debug,
                        configured_position=self._icfg.position,
                        compat_reason=compat_reason,
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

                self._last_injected_ids[session_id] = [e.event_id for e in events]
                return len(events)
            finally:
                await tracker.record("recall_inject", time.perf_counter() - _inject_t0)

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
