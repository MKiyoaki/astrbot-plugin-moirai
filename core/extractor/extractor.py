"""LLM-based event extractor — fills topic/tags/salience after a window closes.

Called as the on_event_close callback in MessageRouter. Uses the AstrBot
provider for one LLM call per closed event; falls back to rule-based
extraction when no provider is available or the call fails.

In main.py this callback is wrapped in asyncio.create_task so the LLM
call never blocks message ingestion on the hot path.

After LLM extraction, the extractor also stores the embedding (topic +
tags text) via event_repo.upsert_vector() if an encoder is provided.
If IPC analysis is enabled, a background task runs SocialOrientationAnalyzer
to derive Big Five → IPC impression updates for every participant pair.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging

from typing import TYPE_CHECKING
from ..embedding.encoder import NullEncoder
from .parser import fallback_extraction, parse_llm_output
from .prompts import build_user_prompt

if TYPE_CHECKING:
    from ..boundary.window import MessageWindow
    from ..repository.base import EventRepository
    from ..embedding.encoder import Encoder
    from ..domain.models import Event
    from ..config import ExtractorConfig
    from ..social.big_five_scorer import BigFiveBuffer
    from ..social.orientation_analyzer import SocialOrientationAnalyzer

logger = logging.getLogger(__name__)


class EventExtractor:
    """Fills Event.topic / chat_content_tags / salience / confidence via LLM,
    then stores the embedding for vector search.

    provider_getter: zero-arg callable returning an AstrBot Provider or None.
    encoder: optional Encoder; if provided, embeddings are stored after
             extraction so Phase 5 vector search works immediately.
    extractor_config: ExtractorConfig controlling prompt, timeout, context window.
    big_five_buffer: optional BigFiveBuffer; if provided alongside orientation_analyzer,
                     IPC social orientation analysis runs as a background task.
    orientation_analyzer: optional SocialOrientationAnalyzer for IPC impression updates.
    ipc_enabled: master switch for IPC analysis (default True when both optional
                 components are provided).
    """

    def __init__(
        self,
        event_repo: EventRepository,
        provider_getter,  # Callable[[], Provider | None]
        encoder: Encoder | None = None,
        extractor_config: ExtractorConfig | None = None,
        big_five_buffer: BigFiveBuffer | None = None,
        orientation_analyzer: SocialOrientationAnalyzer | None = None,
        ipc_enabled: bool = True,
        impression_repo = None,
        plugin_config = None,
    ) -> None:
        from ..config import ExtractorConfig as _EC
        cfg = extractor_config or _EC()
        self._event_repo = event_repo
        self._impression_repo = impression_repo
        self._plugin_config = plugin_config
        self._provider_getter = provider_getter
        self._encoder: Encoder = encoder or NullEncoder()
        self._max_context_messages = cfg.max_context_messages
        self._system_prompt = cfg.system_prompt
        self._llm_timeout = cfg.llm_timeout
        self._big_five_buffer = big_five_buffer
        self._orientation_analyzer = orientation_analyzer
        self._ipc_enabled = ipc_enabled and (big_five_buffer is not None) and (orientation_analyzer is not None)

    async def __call__(self, window: MessageWindow) -> None:
        """on_event_close callback: extract fields, partition into multiple events, persist, then index vector."""
        results = await self._extract(window)
        
        from ..domain.models import Event, MessageRef
        import uuid

        for res in results:
            # Map index-based range back to messages
            start_idx = res["start_idx"]
            end_idx = res["end_idx"]
            sub_messages = window.messages[start_idx : end_idx + 1]
            if not sub_messages:
                continue

            # Handle inherit_from logic
            inherit_from = []
            if res.get("inherit") and window.group_id:
                last_events = await self._event_repo.list_by_group(window.group_id, limit=1)
                if last_events:
                    inherit_from.append(last_events[0].event_id)
            elif res.get("inherit") and not window.group_id:
                # For private chats, list by participant (bot + user)
                # This is a bit more complex, for now we just use the group_id=None list
                last_events = await self._event_repo.list_by_group(None, limit=1)
                if last_events:
                    # Check if it involves the same participant
                    if sub_messages[0].uid in last_events[0].participants:
                        inherit_from.append(last_events[0].event_id)

            event = Event(
                event_id=str(uuid.uuid4()),
                group_id=window.group_id,
                start_time=sub_messages[0].timestamp,
                end_time=sub_messages[-1].timestamp,
                participants=list(set(m.uid for m in sub_messages)),
                interaction_flow=[
                    MessageRef(
                        sender_uid=m.uid,
                        timestamp=m.timestamp,
                        content_hash="",
                        content_preview=m.text[:100],
                    )
                    for m in sub_messages
                ],
                topic=res["topic"],
                chat_content_tags=res["chat_content_tags"],
                salience=res["salience"],
                confidence=res["confidence"],
                inherit_from=inherit_from,
                last_accessed_at=sub_messages[-1].timestamp,
            )

            await self._event_repo.upsert(event)
            await self._index_vector(event)

            # Rule-based impression trigger
            if self._plugin_config and self._plugin_config.relation_enabled and \
               self._plugin_config.impression_event_trigger_enabled and self._impression_repo:
                from ..plugin_initializer import _maybe_trigger_impression
                asyncio.create_task(
                    _maybe_trigger_impression(
                        event, self._impression_repo, self._event_repo, self._plugin_config
                    )
                )

            if self._ipc_enabled:
                # We use a sub-window representation for IPC if possible, 
                # or just the original window messages filtered by time.
                # For simplicity, we pass the original window but it might 
                # lead to over-scoring. 
                # TODO: refine IPC analysis scope if needed
                asyncio.create_task(self._run_ipc_analysis(event, window))

    async def _extract(self, window: MessageWindow) -> list[dict]:
        provider = self._provider_getter()
        if provider is None:
            logger.debug("[EventExtractor] no provider — using fallback")
            return fallback_extraction(window)

        prompt = build_user_prompt(window, self._max_context_messages)
        try:
            resp = await asyncio.wait_for(
                provider.text_chat(prompt=prompt, system_prompt=self._system_prompt),
                timeout=self._llm_timeout,
            )
            result = parse_llm_output(resp.completion_text, len(window.messages) - 1)
            if result is not None:
                return result
            logger.warning(
                "[EventExtractor] LLM output could not be parsed, using fallback. "
                "Raw: %r",
                resp.completion_text[:200],
            )
        except asyncio.TimeoutError:
            logger.warning(
                "[EventExtractor] LLM call timed out, using fallback")
        except Exception as exc:
            logger.warning(
                "[EventExtractor] LLM call failed (%s), using fallback", exc)

        return fallback_extraction(window)

    async def _run_ipc_analysis(self, event: Event, window: MessageWindow) -> None:
        """Feed window messages to BigFiveBuffer, trigger scoring, run orientation analysis."""
        assert self._big_five_buffer is not None
        assert self._orientation_analyzer is not None
        try:
            for msg in window.messages:
                self._big_five_buffer.add_message(msg.uid, msg.text or "")
            for uid in window.participants:
                self._big_five_buffer.maybe_score(uid, self._provider_getter)
            scope = event.group_id or "global"
            await self._orientation_analyzer.analyze(
                window, self._big_five_buffer, event.salience, scope
            )
        except Exception as exc:
            logger.warning("[EventExtractor] IPC analysis failed: %s", exc)

    async def _index_vector(self, event: Event) -> None:
        if self._encoder.dim == 0:
            return
        text = event.topic
        if event.chat_content_tags:
            text += " " + " ".join(event.chat_content_tags)
        if not text.strip():
            return
        try:
            embedding = self._encoder.encode(text)
            await self._event_repo.upsert_vector(event.event_id, embedding)
        except Exception as exc:
            logger.warning("[EventExtractor] vector indexing failed: %s", exc)
