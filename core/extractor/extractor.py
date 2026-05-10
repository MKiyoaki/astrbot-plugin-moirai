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
    from ..repository.base import EventRepository, PersonaRepository
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
        persona_repo: PersonaRepository | None = None,
    ) -> None:
        from ..config import ExtractorConfig as _EC
        cfg = extractor_config or _EC()
        self._event_repo = event_repo
        self._impression_repo = impression_repo
        self._plugin_config = plugin_config
        self._persona_repo = persona_repo
        self._provider_getter = provider_getter
        self._encoder: Encoder = encoder or NullEncoder()
        self._max_context_messages = cfg.max_context_messages
        self._system_prompt = cfg.system_prompt
        self._distillation_system_prompt = cfg.distillation_system_prompt
        self._llm_timeout = cfg.llm_timeout
        self._strategy = cfg.strategy
        self._persona_influenced_summary = cfg.persona_influenced_summary
        self._tag_normalization_threshold = cfg.tag_normalization_threshold
        self._tag_seeds = cfg.tag_seeds
        self._big_five_buffer = big_five_buffer
        self._orientation_analyzer = orientation_analyzer
        self._ipc_enabled = ipc_enabled and (big_five_buffer is not None) and (orientation_analyzer is not None)

        # Initialize canonical tags from seeds asynchronously
        asyncio.create_task(self._init_tag_seeds())

        # Initialize partitioner
        if self._strategy == "semantic":
            eps = cfg.semantic_clustering_eps
            min_samples = cfg.semantic_clustering_min_samples
            self._partitioner = SemanticPartitioner(
                self._encoder, eps=eps, min_samples=min_samples
            )
        else:
            self._partitioner = LlmPartitioner()

    async def _init_tag_seeds(self) -> None:
        """Initialize canonical_tags from configuration seeds."""
        for tag in self._tag_seeds:
            try:
                # Only upsert if not exists to avoid re-encoding
                # Repository implementation already handles ON CONFLICT
                embedding = await self._encoder.encode(tag)
                await self._event_repo.upsert_canonical_tag(tag, embedding)
            except Exception as exc:
                logger.debug("[EventExtractor] tag seed initialization failed for %s: %s", tag, exc)

    async def __call__(self, window: MessageWindow) -> None:
        """on_event_close callback: partition, distill/extract, persist, then index vector.

        Both strategies share the same post-partition pipeline:
          - "llm":      LlmPartitioner returns the whole window as one partition;
                        _extract_batch does ONE LLM call that splits and extracts
                        multiple events simultaneously (most token-efficient for LLM mode).
          - "semantic": SemanticPartitioner returns N pre-clustered partitions;
                        _distill does ONE LLM call per partition using the dedicated
                        distillation prompt (consistent single-object output format).
        """
        from ..utils.perf import performance_timer

        # 0. Fetch existing tags and merge with seeds for few-shot steering
        frequent_tags = await self._event_repo.list_frequent_tags(limit=20)
        steering_tags = list(dict.fromkeys(self._tag_seeds + frequent_tags))[:30]

        # 1. Partitioning
        async with performance_timer("partition"):
            partitions = await self._partitioner.partition(window)

        # 2. Extract fields
        extracted_results: list[tuple[list[int], dict]] = []  # (indices, result_dict)

        if self._strategy == "llm":
            # One batch call: LLM handles both splitting and field extraction.
            async with performance_timer("extraction"):
                batch_results = await self._extract_batch(window, existing_tags=steering_tags)
                for res in batch_results:
                    start, end = res["start_idx"], res["end_idx"]
                    extracted_results.append((list(range(start, end + 1)), res))
        else:
            # Per-partition distillation: partitioner already handled splitting.
            for part in partitions:
                sub_messages = [window.messages[i] for i in part.indices]
                if not sub_messages:
                    continue
                async with performance_timer("distill"):
                    res = await self._distill(sub_messages, existing_tags=steering_tags)
                    extracted_results.append((part.indices, res))

        # 3. Persistence
        from ..domain.models import Event, MessageRef
        import uuid

        ipc_tasks = []

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

            # --- Tag Abstraction & Normalization ---
            raw_tags = res.get("chat_content_tags", [])
            aligned_tags = await self._align_tags(raw_tags)

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
                chat_content_tags=aligned_tags,
                salience=res["salience"],
                confidence=res["confidence"],
                inherit_from=inherit_from,
                last_accessed_at=sub_messages[-1].timestamp,
            )

            if self._persona_influenced_summary:
                bot_name = await self._get_bot_persona_name()
                if bot_name:
                    event = dataclasses.replace(event, bot_persona_name=bot_name)

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
                ipc_tasks.append(
                    self._run_ipc_analysis(
                        event, 
                        window, 
                        personality_data=res.get("participants_personality")
                    )
                )

        if ipc_tasks:
            await asyncio.gather(*ipc_tasks)

    async def _align_tags(self, raw_tags: list[str]) -> list[str]:
        """Normalize tags by aligning them to existing canonical tags via vector similarity."""
        if not raw_tags:
            return []
        
        aligned = []
        for tag in raw_tags:
            tag = tag.strip()
            if not tag:
                continue
            
            # 1. Vector encoding (local/CPU usually)
            try:
                embedding = await self._encoder.encode(tag)
            except Exception as exc:
                logger.debug("[EventExtractor] tag encoding failed: %s", exc)
                aligned.append(tag)
                continue
                
            # 2. Search for existing canonical tags in tags_vec
            matches = await self._event_repo.search_canonical_tag(
                embedding, threshold=self._tag_normalization_threshold
            )
            
            if matches:
                # Similarity is high enough, align to the existing one
                best_match, _ = matches[0]
                aligned.append(best_match)
            else:
                # No close match, this is a new canonical tag category
                await self._event_repo.upsert_canonical_tag(tag, embedding)
                aligned.append(tag)
                
        return list(dict.fromkeys(aligned)) # preserve order, remove duplicates

    async def _get_bot_persona_desc(self) -> str | None:
        """Return the bot persona description if persona-influenced summary is enabled."""
        if not self._persona_influenced_summary or self._persona_repo is None:
            return None
        try:
            personas = await self._persona_repo.list_all()
            bot = next(
                (p for p in personas if any(
                    (bi[0] if isinstance(bi, tuple) else getattr(bi, "platform", None)) == "internal"
                    for bi in (p.bound_identities or [])
                )),
                None,
            )
            if bot:
                desc = bot.persona_attrs.get("description", "") if isinstance(bot.persona_attrs, dict) else ""
                return desc or bot.primary_name or None
        except Exception as exc:
            logger.debug("[EventExtractor] bot persona lookup failed: %s", exc)
        return None

    async def _get_bot_persona_name(self) -> str | None:
        """Return the bot persona primary_name for display purposes."""
        if self._persona_repo is None:
            return None
        try:
            personas = await self._persona_repo.list_all()
            bot = next(
                (p for p in personas if any(
                    (bi[0] if isinstance(bi, tuple) else getattr(bi, "platform", None)) == "internal"
                    for bi in (p.bound_identities or [])
                )),
                None,
            )
            return bot.primary_name if bot else None
        except Exception as exc:
            logger.debug("[EventExtractor] bot persona name lookup failed: %s", exc)
        return None

    async def _extract_batch(self, window: MessageWindow, existing_tags: list[str] | None = None) -> list[dict]:
        provider = self._provider_getter()
        if provider is None:
            return fallback_extraction(window)

        bot_persona_desc = await self._get_bot_persona_desc()
        prompt = build_user_prompt(
            window, 
            self._max_context_messages, 
            bot_persona_desc=bot_persona_desc,
            existing_tags=existing_tags
        )
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

    async def _distill(self, messages: list, existing_tags: list[str] | None = None) -> dict:
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

        bot_persona_desc = await self._get_bot_persona_desc()
        prompt = build_distillation_prompt(
            messages, 
            bot_persona_desc=bot_persona_desc,
            existing_tags=existing_tags
        )
        try:
            resp = await asyncio.wait_for(
                provider.text_chat(prompt=prompt, system_prompt=self._distillation_system_prompt),
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

    async def _run_ipc_analysis(
        self, 
        event: Event, 
        window: MessageWindow, 
        personality_data: dict[str, dict[str, float]] | None = None
    ) -> None:
        """Feed window messages to BigFiveBuffer, trigger scoring, run orientation analysis.
        
        If personality_data is provided (Unified Extraction), it is used to prime
        the BigFiveBuffer cache before analysis, skipping the extra LLM call.
        """
        assert self._big_five_buffer is not None
        assert self._orientation_analyzer is not None
        
        from ..domain.models import BigFiveVector
        
        try:
            # 1. Map names in personality_data to UIDs from the window
            name_to_uid: dict[str, str] = {}
            for msg in window.messages:
                name_to_uid[msg.display_name] = msg.uid
                name_to_uid[msg.uid] = msg.uid

            # 2. Prime the buffer cache if data is available
            if personality_data:
                for name, traits in personality_data.items():
                    uid = name_to_uid.get(name)
                    if not uid:
                        continue
                    
                    vector = BigFiveVector(
                        openness=traits.get("O", 0.0),
                        conscientiousness=traits.get("C", 0.0),
                        extraversion=traits.get("E", 0.0),
                        agreeableness=traits.get("A", 0.0),
                        neuroticism=traits.get("N", 0.0),
                    )
                    # Force update the cache with this fresh event-specific score
                    self._big_five_buffer._cache[uid] = vector
                    logger.debug("[EventExtractor] primed cache for %s via unified extraction", uid[:8])

            # 3. Accumulate messages
            for msg in window.messages:
                self._big_five_buffer.add_message(msg.uid, msg.text or "")
            
            # 4. Trigger scoring and WAIT for them (only fires if NOT primed or x_messages reached)
            scoring_tasks = []
            for uid in window.participants:
                t = self._big_five_buffer.maybe_score(uid, self._provider_getter)
                if t:
                    scoring_tasks.append(t)
            
            if scoring_tasks:
                await asyncio.gather(*scoring_tasks)
            
            # 5. Analyze with fresh scores
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
            embedding = await self._encoder.encode(text)
            await self._event_repo.upsert_vector(event.event_id, embedding)
        except Exception as exc:
            logger.warning("[EventExtractor] vector indexing failed: %s", exc)
