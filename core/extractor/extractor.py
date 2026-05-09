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
from .parser import fallback_extraction, parse_llm_output, parse_single_item
from .prompts import build_user_prompt, build_distillation_prompt
from .partitioner import LlmPartitioner, SemanticPartitioner, Partition

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
        self._strategy = cfg.strategy
        self._big_five_buffer = big_five_buffer
        self._orientation_analyzer = orientation_analyzer
        self._ipc_enabled = ipc_enabled and (big_five_buffer is not None) and (orientation_analyzer is not None)

        # Initialize partitioner
        if self._strategy == "semantic":
            eps = 0.35
            if plugin_config:
                eps = plugin_config._float("semantic_clustering_eps", 0.35)
            self._partitioner = SemanticPartitioner(self._encoder, eps=eps)
        else:
            self._partitioner = LlmPartitioner()

    async def __call__(self, window: MessageWindow) -> None:
        """on_event_close callback: partition, distill/extract, persist, then index vector."""
        from ..utils.perf import performance_timer
        
        # 1. Partitioning
        async with performance_timer("partition"):
            partitions = await self._partitioner.partition(window)

        # 2. Extract Fields (Batch or per-partition)
        # If strategy is "llm", we do ONE call for the whole window and get multiple results.
        # If strategy is "semantic", we do ONE call PER partition.
        
        extracted_results: list[tuple[list[int], dict]] = [] # list of (indices, result_dict)

        if self._strategy == "llm":
            async with performance_timer("extraction"):
                batch_results = await self._extract_batch(window)
                # Map batch results back to message indices
                for res in batch_results:
                    start, end = res["start_idx"], res["end_idx"]
                    indices = list(range(start, end + 1))
                    extracted_results.append((indices, res))
        else:
            # Semantic strategy: process each partition individually
            for part in partitions:
                sub_messages = [window.messages[i] for i in part.indices]
                if not sub_messages:
                    continue
                async with performance_timer("distill"):
                    res = await self._distill(sub_messages)
                    extracted_results.append((part.indices, res))

        # 3. Persistence
        from ..domain.models import Event, MessageRef
        import uuid

        for indices, res in extracted_results:
            sub_messages = [window.messages[i] for i in indices]
            if not sub_messages:
                continue

            # Handle inherit_from logic
            inherit_from = []
            if res.get("inherit") and window.group_id:
                last_events = await self._event_repo.list_by_group(window.group_id, limit=1)
                if last_events:
                    inherit_from.append(last_events[0].event_id)
            elif res.get("inherit") and not window.group_id:
                last_events = await self._event_repo.list_by_group(None, limit=1)
                if last_events:
                    if sub_messages[0].uid in last_events[0].participants:
                        inherit_from.append(last_events[0].event_id)

            # Robust time range detection
            timestamps = [m.timestamp for m in sub_messages]
            start_time = min(timestamps)
            end_time = max(timestamps)

            event = Event(
                event_id=str(uuid.uuid4()),
                group_id=window.group_id,
                start_time=start_time,
                end_time=end_time,
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
                summary=res.get("summary", ""),
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
                asyncio.create_task(self._run_ipc_analysis(event, window))

    async def _extract_batch(self, window: MessageWindow) -> list[dict]:
        provider = self._provider_getter()
        if provider is None:
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
        except Exception as exc:
            logger.warning("[EventExtractor] LLM batch extraction failed: %s", exc)

        return fallback_extraction(window)

    async def _distill(self, messages: list) -> dict:
        """Call LLM to summarize a specific cluster of messages."""
        provider = self._provider_getter()
        if provider is None:
            # Fake a result from messages
            topic = messages[0].text[:30]
            return {
                "topic": topic,
                "summary": f"聚合了 {len(messages)} 条相关消息。",
                "chat_content_tags": [],
                "salience": 0.5,
                "confidence": 0.2,
                "inherit": False
            }

        prompt = build_distillation_prompt(messages)
        try:
            resp = await asyncio.wait_for(
                provider.text_chat(prompt=prompt, system_prompt=self._system_prompt),
                timeout=self._llm_timeout,
            )
            result = parse_single_item(resp.completion_text)
            if result is not None:
                return result
        except Exception as exc:
            logger.warning("[EventExtractor] LLM distillation failed: %s", exc)

        # Fallback for single item
        return {
            "topic": messages[0].text[:30],
            "summary": f"提炼失败，原始消息：{messages[0].text[:100]}...",
            "chat_content_tags": [],
            "salience": 0.4,
            "confidence": 0.1,
            "inherit": False
        }

    async def _extract(self, window: MessageWindow) -> list[dict]:
        """Legacy method, kept for compatibility if needed."""
        return await self._extract_batch(window)

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
