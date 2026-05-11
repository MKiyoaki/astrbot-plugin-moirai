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

import re
import time
from math import exp, log
from typing import TYPE_CHECKING, Any

from ..config import (
    FAKE_TOOL_CALL_ID_PREFIX,
    MEMORY_INJECTION_FOOTER,
    MEMORY_INJECTION_HEADER,
)
from ..domain.models import Event
from ..utils.formatter import format_events_for_fake_tool_call, format_events_for_prompt, format_persona_for_prompt
from ..retrieval.rrf import rrf_scores
from .base import BaseRecallManager
from ..social.soul_state import SoulState, apply_decay, apply_tanh_elastic, format_soul_for_prompt, from_config

if TYPE_CHECKING:
    from ..config import InjectionConfig, RetrievalConfig, SoulConfig
    from ..retrieval.hybrid import HybridRetriever
    from ..repository.base import PersonaRepository

_LOG2 = log(2)

_INJECTION_RE = re.compile(
    re.escape(MEMORY_INJECTION_HEADER) + r".*?" + re.escape(MEMORY_INJECTION_FOOTER),
    re.DOTALL,
)


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

    def get_soul_states(self) -> dict[str, Any]:
        """Return all active soul states as a dict of dicts."""
        return {sid: state.__dict__.copy() for sid, state in self._soul_states.items()}

    async def recall(self, query: str, group_id: str | None = None) -> list[Event]:
        """Return re-ranked events for injection."""
        cfg = self._rcfg
        bm25, vec = await self._retriever.search_raw(
            query, active_only=cfg.active_only, group_id=group_id
        )
        
        import logging
        _log = logging.getLogger(__name__)
        _log.debug("[RecallManager] query: %r, group_id: %r", query, group_id)
        _log.debug("[RecallManager] BM25 hits: %d, Vec hits: %d", len(bm25), len(vec))
        if vec:
            _log.debug("[RecallManager] Top Vec Topic: %r", vec[0].topic)

        # Vector fallback: if BM25 returned nothing and fallback is enabled, use vec only.
        if not bm25 and cfg.vector_fallback_enabled and vec:
            candidates = vec
            scores: dict[str, float] = {e.event_id: 1.0 / (cfg.rrf_k + 1) for e in vec}
        else:
            scores = rrf_scores([bm25, vec], k=cfg.rrf_k)
            seen: set[str] = set()
            candidates: list[Event] = []
            for e in bm25 + vec:
                if e.event_id not in seen:
                    seen.add(e.event_id)
                    candidates.append(e)

        if not candidates:
            return []

        now = time.time()
        max_rrf = max(scores.values()) if scores else 1.0

        def _final_score(event: Event) -> float:
            days = (now - event.end_time) / 86400.0
            recency = exp(-_LOG2 * days / cfg.recency_half_life_days)
            rrf = scores.get(event.event_id, 0.0)
            return (
                cfg.relevance_weight * rrf / max_rrf
                + cfg.salience_weight * event.salience
                + cfg.recency_weight * recency
            )

        ranked = sorted(candidates, key=_final_score, reverse=True)
        return ranked[: cfg.final_limit]

    async def recall_and_inject(
        self,
        query: str,
        req: object,
        session_id: str,
        group_id: str | None = None,
        sender_uid: str | None = None,
    ) -> int:
        """Recall and inject memory into req. Returns the number of events injected."""
        from ..utils.perf import performance_timer
        async with performance_timer("recall"):
            if self._icfg.auto_clear:
                self.clear_previous_injection(req)

            events = await self.recall(query, group_id=group_id)

            position = self._icfg.position
            token_budget = self._icfg.token_budget

            if position == "fake_tool_call":
                if not events:
                    return 0
                messages = format_events_for_fake_tool_call(
                    events, query, token_budget=token_budget
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
            if sender_uid and self._persona_repo and position in ("system_prompt", None, ""):
                try:
                    persona = await self._persona_repo.get_by_uid(sender_uid)
                    if persona:
                        persona_segment = format_persona_for_prompt(persona)
                except Exception:
                    pass

            # Soul Layer injection — short-term emotional state.
            soul_segment = ""
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

            # Nothing to inject — exit early only if all three segments are empty.
            if not body and not persona_segment and not soul_segment:
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
