"""LLM-based event extractor — fills topic/tags/salience after a window closes.

Called as the on_event_close callback in MessageRouter. Uses the AstrBot
provider for one LLM call per closed event; falls back to rule-based
extraction when no provider is available or the call fails.

In main.py this callback is wrapped in asyncio.create_task so the LLM
call never blocks message ingestion on the hot path.

After LLM extraction, the extractor also stores the embedding (topic +
tags text) via event_repo.upsert_vector() if an encoder is provided.
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

logger = logging.getLogger(__name__)


class EventExtractor:
    """Fills Event.topic / chat_content_tags / salience / confidence via LLM,
    then stores the embedding for vector search.

    provider_getter: zero-arg callable returning an AstrBot Provider or None.
    encoder: optional Encoder; if provided, embeddings are stored after
             extraction so Phase 5 vector search works immediately.
    extractor_config: ExtractorConfig controlling prompt, timeout, context window.
    """

    def __init__(
        self,
        event_repo: EventRepository,
        provider_getter,  # Callable[[], Provider | None]
        encoder: Encoder | None = None,
        extractor_config: ExtractorConfig | None = None,
    ) -> None:
        from ..config import ExtractorConfig as _EC  # local import avoids circularity
        cfg = extractor_config or _EC()
        self._event_repo = event_repo
        self._provider_getter = provider_getter
        self._encoder: Encoder = encoder or NullEncoder()
        self._max_context_messages = cfg.max_context_messages
        self._llm_timeout = cfg.llm_timeout
        self._system_prompt = cfg.system_prompt

    async def __call__(self, event: Event, window: MessageWindow) -> None:
        """on_event_close callback: extract fields, persist, then index vector."""
        fields = await self._extract(window)
        updated = dataclasses.replace(event, **fields)
        await self._event_repo.upsert(updated)
        await self._index_vector(updated)

    async def _extract(self, window: MessageWindow) -> dict:
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
            result = parse_llm_output(resp.completion_text)
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
