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
import re
import time as _time

from typing import Awaitable, Callable, TYPE_CHECKING
from ..embedding.encoder import NullEncoder
from .parser import fallback_extraction, fallback_single_extraction, parse_llm_output, parse_single_item
from .persona_context import resolve_bot_persona_context
from .prompts import build_user_prompt, build_distillation_prompt
from .partitioner import LlmPartitioner, SemanticPartitioner, Partition

_NO_PROVIDER_WARN_INTERVAL = 60.0

# Patterns for tag values that look like IDs rather than semantic labels.
_NUMERIC_ID_RE = re.compile(r'^\d{5,}$')
_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
# Sentence-like tags: contain sentence-ending punctuation or are overly long
_SENTENCE_RE = re.compile(r'[，。！？,!?]|[，。！？,!?]')
_URL_RE = re.compile(r'https?://\S+|www\.\S+', re.IGNORECASE)
_SPACE_RE = re.compile(r'\s+')
_TAG_MAX_LEN = 12
_TOPIC_MAX_LEN = 40
_BAD_TAGS = {
    "早", "早安", "晚安", "你好", "您好", "嗨", "hi", "hello", "hey",
    "ok", "okay", "嗯", "啊", "哦", "哈", "哈哈", "草", "笑",
}


def _is_valid_tag(tag: str, blocked_terms: set[str] | None = None) -> bool:
    """Return False for strings that look like IDs or sentence fragments rather than topic labels."""
    t = tag.strip()
    if not t or len(t) > _TAG_MAX_LEN:
        return False
    lower = t.lower()
    if lower in _BAD_TAGS:
        return False
    if blocked_terms and lower in blocked_terms:
        return False
    if _URL_RE.search(t):
        return False
    if _SPACE_RE.search(t):
        return False
    if _NUMERIC_ID_RE.match(t):
        return False
    if _UUID_RE.match(t):
        return False
    if _SENTENCE_RE.search(t):
        return False
    return True


def _sanitize_topic(topic: object) -> str:
    value = str(topic or "").strip()
    value = _URL_RE.sub("", value)
    value = " ".join(value.split())
    value = value.strip(" -_，。！？、,!?：:；;（）()[]【】<>《》")
    if not value:
        return "未命名事件"
    return value[:_TOPIC_MAX_LEN]


def _latest_persona_name(messages: list) -> str | None:
    """Return the ``bot_persona_name`` carried by the most recent message that
    has one.

    Recency beats frequency: a window that straddles a persona switch must be
    attributed to whichever persona was active when the window closed, not the
    one that merely contributed more messages. Falls back to iteration order
    when timestamps are missing.
    """
    latest_key: tuple[float, int] | None = None
    latest_name: str | None = None
    for idx, msg in enumerate(messages):
        name = getattr(msg, "bot_persona_name", None)
        if not name:
            continue
        ts = getattr(msg, "timestamp", None)
        key = (float(ts) if ts is not None else 0.0, idx)
        if latest_key is None or key >= latest_key:
            latest_key = key
            latest_name = name
    return latest_name


_last_no_provider_warn_ts: float = 0.0


def _warn_no_provider() -> None:
    global _last_no_provider_warn_ts
    now = _time.monotonic()
    if now - _last_no_provider_warn_ts >= _NO_PROVIDER_WARN_INTERVAL:
        _last_no_provider_warn_ts = now
        logger.warning(
            "[EventExtractor] LLM provider is None; falling back to rule-based extraction"
        )


def _response_text(resp: object) -> str:
    for attr in ("completion_text", "text"):
        value = getattr(resp, attr, None)
        if value is None or callable(value):
            continue
        text = value if isinstance(value, str) else str(value)
        if text:
            return text
    return ""

if TYPE_CHECKING:
    from ..boundary.window import MessageWindow
    from ..repository.base import EventRepository, PersonaRepository
    from ..embedding.encoder import Encoder
    from ..domain.models import Event
    from ..config import ExtractorConfig
    from ..social.big_five_scorer import BigFiveBuffer
    from ..social.orientation_analyzer import SocialOrientationAnalyzer
    from ..managers.llm_manager import LLMTaskManager
    from ..managers.raw_message_writer import RawMessageWriter
    from ..repository.base import RawMessageRepository

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
    llm_manager: optional LLMTaskManager for concurrency control.
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
        persona_repo: PersonaRepository | None = None,
        llm_manager: LLMTaskManager | None = None,
        events_persisted_callback: Callable[[list], Awaitable[None]] | None = None,
        raw_message_repo: RawMessageRepository | None = None,
        raw_message_writer: RawMessageWriter | None = None,
    ) -> None:
        from ..config import ExtractorConfig as _EC
        cfg = extractor_config or _EC()
        self._event_repo = event_repo
        self._persona_repo = persona_repo
        self._provider_getter = provider_getter
        self._encoder: Encoder = encoder or NullEncoder()
        self._llm_manager = llm_manager
        self._events_persisted_callback = events_persisted_callback
        self._raw_message_repo = raw_message_repo
        self._raw_message_writer = raw_message_writer
        self._max_context_messages = cfg.max_context_messages
        self._system_prompt = cfg.system_prompt
        self._distillation_system_prompt = cfg.distillation_system_prompt
        self._llm_timeout = cfg.llm_timeout
        self._llm_max_retries = max(0, int(getattr(cfg, "llm_max_retries", 2)))
        self._llm_timeout_growth = max(1.0, float(getattr(cfg, "llm_timeout_growth", 1.5)))
        self._strategy = cfg.strategy
        self._persona_influenced_summary = cfg.persona_influenced_summary
        # Explicit bot_persona_name bucket. When set, every Event is filed under
        # this exact name regardless of which persona the window's bot messages
        # carry — the deterministic cross-platform "pin" for one persona.
        self._bot_persona_override = (
            getattr(cfg, "bot_persona_name_override", "") or ""
        ).strip()
        self._tag_normalization_threshold = cfg.tag_normalization_threshold
        self._tag_promotion_min_df = cfg.tag_promotion_min_df
        self._tag_seeds = cfg.tag_seeds
        self._big_five_buffer = big_five_buffer
        self._orientation_analyzer = orientation_analyzer
        self._ipc_enabled = ipc_enabled and (big_five_buffer is not None) and (orientation_analyzer is not None)

        # Tag seeds are initialized lazily on first __call__ so that constructing
        # EventExtractor outside an async context (e.g., during import-time tests)
        # does not raise RuntimeError: no running event loop.
        self._seeds_initialized: bool = False

        from ..utils.cache import TTLCache
        self._frequent_tags_cache: TTLCache[list[str]] = TTLCache(ttl=60.0)
        self._personas_cache: TTLCache[list] = TTLCache(ttl=300.0)

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
        """Initialize canonical_tags from configuration seeds via a single batch encode."""
        if not self._tag_seeds:
            return
        try:
            embeddings = await self._encoder.encode_batch(self._tag_seeds)
        except Exception as exc:
            logger.debug("[EventExtractor] tag seed batch encoding failed: %s", exc)
            return
        for tag, embedding in zip(self._tag_seeds, embeddings):
            try:
                # df_delta=0: registering seeds at startup is not a sighting,
                # otherwise every restart would inflate their frequency.
                await self._event_repo.upsert_canonical_tag(tag, embedding, df_delta=0)
            except Exception as exc:
                logger.debug("[EventExtractor] tag seed upsert failed for %s: %s", tag, exc)

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

        _diag_t0 = _time.perf_counter()
        partitions: list[Partition] = []
        persisted_events: list[Event] = []
        # 0. Lazy-initialize tag seeds (safe: we are inside an async context here)
        if not self._seeds_initialized:
            self._seeds_initialized = True
            await self._init_tag_seeds()

        # 1. Determine bot persona context.
        #    Priority: persona names actually carried by bot messages in this window.
        #    Fallback: legacy "internal"-bound persona via _get_bot_persona().
        bot_name, bot_desc = await self._resolve_window_persona(window)

        # 2. Fetch existing tags and merge with seeds for few-shot steering
        frequent_tags = self._frequent_tags_cache.get()
        if frequent_tags is None:
            frequent_tags = await self._event_repo.list_frequent_tags(limit=20)
            self._frequent_tags_cache.put(frequent_tags)
        steering_tags = list(dict.fromkeys(self._tag_seeds + frequent_tags))[:30]

        # 3. Partitioning
        async with performance_timer("partition"):
            partitions = await self._partitioner.partition(window)

        # 3b. Noise filter (semantic strategy only): strip pure-emoji / 复读 messages
        #     before sending partitions to the LLM to reduce hallucination risk.
        if self._strategy != "llm":
            from .noise_filter import filter_partitions
            partitions = filter_partitions(partitions, window)

        # 4. Extract fields
        extracted_results: list[tuple[list[int], dict]] = []  # (indices, result_dict)

        if self._strategy == "llm":
            # One batch call: LLM handles both splitting and field extraction.
            async with performance_timer("extraction"):
                batch_results = await self._extract_batch(window, existing_tags=steering_tags, bot_persona_desc=bot_desc)
                if len(batch_results) == 1 and window.messages:
                    batch_results[0]["start_idx"] = 0
                    batch_results[0]["end_idx"] = len(window.messages) - 1
                for res in batch_results:
                    start, end = res.get("start_idx", 0), res.get("end_idx", len(window.messages)-1)
                    extracted_results.append((list(range(start, end + 1)), res))
        else:
            # Per-partition distillation: run all partitions concurrently.
            # LLMTaskManager caps actual LLM concurrency; asyncio.gather just
            # removes the artificial serialisation that was the main bottleneck.
            async def _distill_part(part: "Partition") -> "tuple[list[int], dict] | None":
                sub_messages = [window.messages[i] for i in part.indices]
                if not sub_messages:
                    return None
                async with performance_timer("distill"):
                    res = await self._distill(
                        sub_messages,
                        existing_tags=steering_tags,
                        bot_persona_desc=bot_desc,
                    )
                return (part.indices, res)

            distill_outcomes = await asyncio.gather(
                *[_distill_part(p) for p in partitions],
                return_exceptions=True,
            )
            for outcome in distill_outcomes:
                if isinstance(outcome, BaseException):
                    logger.warning("[EventExtractor] distill partition failed: %s", outcome)
                elif outcome is not None:
                    extracted_results.append(outcome)

        # 5. Batch tag normalization across all extracted events
        all_raw_tags = []
        for _, res in extracted_results:
            all_raw_tags.extend(res.get("chat_content_tags", []))
        
        normalized_map = await self._batch_align_tags(all_raw_tags)

        # 6. Persistence
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

            # Map raw tags to normalized tags (invalid tags are excluded here and in _batch_align_tags)
            raw_tags = res.get("chat_content_tags", [])
            blocked_terms = {
                str(part).strip().lower()
                for m in sub_messages
                for part in (
                    getattr(m, "display_name", ""),
                    getattr(m, "uid", ""),
                    getattr(m, "bot_persona_name", ""),
                )
                if str(part).strip()
            }
            aligned_tags = list(dict.fromkeys(
                normalized_map.get(tag, tag) for tag in raw_tags if _is_valid_tag(tag, blocked_terms)
            ))
            aligned_tags = [
                tag for tag in aligned_tags if _is_valid_tag(tag, blocked_terms)
            ]
            topic = _sanitize_topic(res.get("topic", ""))

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
                        content_hash=getattr(m, "content_hash", "") or "",
                        content_preview=m.text[:100],
                        message_id=getattr(m, "message_id", "") or "",
                    )
                    for m in sub_messages
                ],
                topic=topic,
                summary=res.get("summary", ""),
                chat_content_tags=aligned_tags,
                salience=res["salience"],
                confidence=res["confidence"],
                inherit_from=inherit_from,
                last_accessed_at=sub_messages[-1].timestamp,
            )

            if self._bot_persona_override:
                # Explicit override wins unconditionally: every Event lands in
                # the configured bucket, even windows with no bot message.
                event = dataclasses.replace(
                    event, bot_persona_name=self._bot_persona_override
                )
            elif self._persona_influenced_summary:
                # Prefer the persona of the most RECENT bot message in this
                # event's own sub_messages (recency, not frequency); fall back
                # to the window-level winner so events with no bot message
                # still get tagged.
                event_persona = _latest_persona_name(sub_messages) or bot_name
                if event_persona:
                    event = dataclasses.replace(event, bot_persona_name=event_persona)

            await self._event_repo.upsert(event)
            await self._link_raw_messages(event.event_id, sub_messages)
            persisted_events.append(event)

            if self._ipc_enabled:
                ipc_tasks.append(
                    self._run_ipc_analysis(
                        event, 
                        window, 
                        personality_data=res.get("participants_personality")
                    )
                )

        await self._batch_index_vectors(persisted_events)

        if ipc_tasks:
            await asyncio.gather(*ipc_tasks)

        if self._events_persisted_callback and persisted_events:
            try:
                await self._events_persisted_callback(persisted_events)
            except Exception as exc:
                logger.warning("[EventExtractor] events_persisted_callback failed: %s", exc)

        logger.info(
            "[EventExtractor] window extracted: session=%s strategy=%s messages=%d "
            "partitions=%d events=%d low_conf=%d duration=%.3fs ids=%s",
            window.session_id,
            self._strategy,
            window.message_count,
            len(partitions),
            len(persisted_events),
            sum(1 for event in persisted_events if float(event.confidence or 0.0) <= 0.3),
            _time.perf_counter() - _diag_t0,
            [event.event_id[:8] for event in persisted_events],
        )

    async def _batch_align_tags(self, raw_tags: list[str]) -> dict[str, str]:
        """Normalize a large list of tags in a single batch operation.
        
        Returns a mapping from raw_tag -> normalized_tag.
        """
        unique_raw = list(dict.fromkeys(t.strip() for t in raw_tags if _is_valid_tag(t)))
        if not unique_raw:
            return {}

        # 1. Batch encode all unique tags
        try:
            embeddings = await self._encoder.encode_batch(unique_raw)
        except Exception as exc:
            logger.debug("[EventExtractor] tag batch encoding failed: %s", exc)
            return {t: t for t in unique_raw}

        # 2. Concurrent canonical-tag search
        async def _resolve(tag: str, embedding: list[float]) -> tuple[str, str]:
            # Broad seed labels steer the LLM's abstraction level; they are not
            # lossy replacements for a specific topic label, so they are dropped
            # inside the query rather than after it — otherwise a handful of
            # seeds could fill the result limit and hide a real anchor.
            exclude = [seed for seed in self._tag_seeds if seed != tag]
            try:
                matches = await self._event_repo.search_canonical_tag(
                    embedding,
                    threshold=self._tag_normalization_threshold,
                    prefer_min_df=self._tag_promotion_min_df,
                    exclude=exclude,
                )
            except Exception as exc:
                logger.debug("[EventExtractor] canonical tag search failed: %s", exc)
                return tag, tag
            for canonical, _score in matches:
                if canonical == tag:
                    # Sighting of an established anchor by its own name.
                    await self._event_repo.upsert_canonical_tag(tag, embedding)
                else:
                    await self._event_repo.bump_canonical_tag_df(canonical)
                return tag, canonical
            # Nothing close enough. Record the tag as a candidate — it stays
            # prunable until it has recurred tag_promotion_min_df times, so a
            # one-off label never becomes a permanent part of the vocabulary.
            await self._event_repo.upsert_canonical_tag(tag, embedding)
            return tag, tag

        results = await asyncio.gather(
            *(_resolve(tag, emb) for tag, emb in zip(unique_raw, embeddings))
        )
        return dict(results)

    async def _resolve_window_persona(self, window: MessageWindow) -> tuple[str | None, str | None]:
        """Return (persona_name, persona_description) inferred from the window's bot messages.

        Picks the persona carried by the **most recent** bot message in the
        window (recency, not frequency): a window that straddles a persona
        switch must be attributed to whichever persona was active when the
        window closed, not the one that merely has more messages.
        Falls back to the session's last known active persona, then to the
        legacy `_get_bot_persona()` (internal-bound persona).
        """
        if not self._persona_influenced_summary:
            return None, None

        best_name = _latest_persona_name(window.messages)
        if best_name:
            logger.debug(
                "[EventExtractor] [window-persona] %d msgs -> latest bot persona %r",
                len(window.messages), best_name,
            )
            desc = await self._lookup_persona_description(best_name)
            return best_name, desc or best_name

        # No bot message in this window — fall back to the session's last known
        # active persona (set by handle_llm_request via note_session_persona).
        last = getattr(window, "last_active_persona", None)
        if last:
            logger.debug(
                "[EventExtractor] [window-persona] no bot msg, using last_active_persona %r",
                last,
            )
            desc = await self._lookup_persona_description(last)
            return last, desc or last

        logger.debug(
            "[EventExtractor] [window-persona] no bot msg / no last persona, legacy fallback"
        )
        return await self._get_bot_persona()

    async def _lookup_persona_description(self, persona_name: str) -> str | None:
        """Best-effort lookup of a persona description by primary name."""
        if self._persona_repo is None:
            return None
        try:
            personas = self._personas_cache.get()
            if personas is None:
                personas = await self._persona_repo.list_all()
                self._personas_cache.put(personas)
        except Exception as exc:
            logger.debug("[EventExtractor] persona list_all failed: %s", exc)
            return None
        for p in personas:
            if (p.primary_name or "").strip() == persona_name:
                attrs = p.persona_attrs if isinstance(p.persona_attrs, dict) else {}
                desc = str(attrs.get("description") or "").strip()
                return desc or None
        return None

    async def _get_bot_persona(self) -> tuple[str | None, str | None]:
        """Return (primary_name, description) for the bot persona.

        Resolved fresh on every call — caching it permanently meant a global
        persona change was never picked up without a plugin reload.
        """
        try:
            return await resolve_bot_persona_context(
                self._persona_repo,
                self._persona_influenced_summary,
            )
        except Exception as exc:
            logger.debug("[EventExtractor] bot persona lookup failed: %s", exc)
        return None, None

    async def _align_tags(self, raw_tags: list[str]) -> list[str]:
        mapping = await self._batch_align_tags(raw_tags)
        return list(dict.fromkeys(mapping.get(tag, tag) for tag in raw_tags))

    async def _call_llm_with_retry(self, coro_factory, task_name: str) -> tuple[object, int]:
        """Run an LLM call with timeout + exponential retry on TimeoutError / provider exceptions.

        coro_factory: zero-arg callable returning a fresh provider coroutine on each attempt.
        Returns (response, retries_used). Raises the last exception when all attempts fail.
        """
        attempts = self._llm_max_retries + 1
        timeout = float(self._llm_timeout)
        last_exc: BaseException | None = None
        for i in range(attempts):
            try:
                if self._llm_manager:
                    resp = await self._llm_manager.run(
                        asyncio.wait_for,
                        coro_factory(),
                        timeout=timeout,
                        task_name=task_name,
                    )
                else:
                    resp = await asyncio.wait_for(coro_factory(), timeout=timeout)
                return resp, i
            except asyncio.TimeoutError as exc:
                last_exc = exc
                if i + 1 >= attempts:
                    break
                logger.warning(
                    "[EventExtractor] %s timed out after %.1fs (attempt %d/%d); retrying with longer timeout",
                    task_name, timeout, i + 1, attempts,
                )
                timeout *= self._llm_timeout_growth
            except Exception as exc:
                last_exc = exc
                if i + 1 >= attempts:
                    break
                logger.warning(
                    "[EventExtractor] %s failed (%s); attempt %d/%d, retrying",
                    task_name, exc, i + 1, attempts,
                )
                await asyncio.sleep(min(2.0 ** i, 5.0))
        assert last_exc is not None
        raise last_exc

    async def _extract_batch(self, window: MessageWindow, existing_tags: list[str] | None = None, bot_persona_desc: str | None = None) -> list[dict]:
        provider = self._provider_getter()
        if provider is None:
            _warn_no_provider()
            logger.warning(
                "[EventExtractor] event fell back to rule extraction: reason=provider_none, "
                "session=%s, message_count=%d",
                window.session_id, window.message_count,
            )
            return fallback_extraction(window)

        prompt = build_user_prompt(
            window,
            self._max_context_messages,
            bot_persona_desc=bot_persona_desc,
            existing_tags=existing_tags
        )
        fallback_reason = "parse_error"
        retries_used = 0
        try:
            resp, retries_used = await self._call_llm_with_retry(
                lambda: provider.text_chat(prompt=prompt, system_prompt=self._system_prompt),
                task_name="extraction",
            )
            result = parse_llm_output(
                _response_text(resp),
                len(window.messages) - 1,
                has_bot_persona=bool(bot_persona_desc),
                merge_to_single=True,
            )
            if result is not None:
                return result
            raw_text = _response_text(resp)
            logger.warning(
                "[EventExtractor] LLM extraction parse_error; attempting JSON repair "
                "(session=%s, message_count=%d, snippet=%r)",
                window.session_id,
                window.message_count,
                raw_text[:240],
            )
            repair_prompt = (
                "请把下面内容修复为严格 JSON Array。只输出 JSON Array，不要解释，不要 markdown。"
                "每个对象必须包含 start_idx、end_idx、topic、summary、chat_content_tags、salience、confidence。\n\n"
                f"{raw_text[:6000]}"
            )
            repair_resp, _ = await self._call_llm_with_retry(
                lambda: provider.text_chat(prompt=repair_prompt, system_prompt="你只负责修复 JSON。"),
                task_name="extraction_repair",
            )
            result = parse_llm_output(
                _response_text(repair_resp),
                len(window.messages) - 1,
                has_bot_persona=bool(bot_persona_desc),
                merge_to_single=True,
            )
            if result is not None:
                return result
            logger.warning(
                "[EventExtractor] JSON repair parse_error; falling back "
                "(session=%s, message_count=%d, repair_snippet=%r)",
                window.session_id,
                window.message_count,
                _response_text(repair_resp)[:240],
            )
        except asyncio.TimeoutError:
            fallback_reason = "timeout"
            logger.warning(
                "[EventExtractor] LLM batch extraction timed out (retries_used=%d)",
                self._llm_max_retries,
            )
            retries_used = self._llm_max_retries
        except Exception as exc:
            fallback_reason = "exception"
            logger.warning("[EventExtractor] LLM batch extraction failed: %s", exc)
            retries_used = self._llm_max_retries

        logger.warning(
            "[EventExtractor] event fell back to rule extraction: reason=%s, "
            "session=%s, message_count=%d, retries_used=%d",
            fallback_reason, window.session_id, window.message_count, retries_used,
        )
        return fallback_extraction(window)

    async def _distill(self, messages: list, existing_tags: list[str] | None = None, bot_persona_desc: str | None = None) -> dict:
        """Call LLM to summarize a specific cluster of messages."""
        provider = self._provider_getter()
        if provider is None:
            return fallback_single_extraction(messages)

        prompt = build_distillation_prompt(
            messages, 
            bot_persona_desc=bot_persona_desc,
            existing_tags=existing_tags
        )
        try:
            resp, _ = await self._call_llm_with_retry(
                lambda: provider.text_chat(prompt=prompt, system_prompt=self._distillation_system_prompt),
                task_name="distillation",
            )
            result = parse_single_item(_response_text(resp), has_bot_persona=bool(bot_persona_desc))
            if result is not None:
                return result
        except Exception as exc:
            logger.warning("[EventExtractor] LLM distillation failed: %s", exc)

        return fallback_single_extraction(messages)

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

                    # traits is {"scores": {...}, "evidence": str|None} (nested format)
                    # or legacy {"O": 0.6, ...} if parser fell back
                    scores = traits.get("scores", traits)
                    vector = BigFiveVector(
                        openness=scores.get("O", 0.0),
                        conscientiousness=scores.get("C", 0.0),
                        extraversion=scores.get("E", 0.0),
                        agreeableness=scores.get("A", 0.0),
                        neuroticism=scores.get("N", 0.0),
                    )
                    # Force update the cache with this fresh event-specific score
                    self._big_five_buffer._cache[uid] = vector
                    if traits.get("evidence"):
                        self._big_five_buffer._evidence[uid] = traits["evidence"]
                    logger.debug("[EventExtractor] primed cache for %s via unified extraction", uid[:8])

            # 3. Accumulate messages
            for msg in window.messages:
                self._big_five_buffer.add_message(msg.uid, msg.text or "")
            
            # 4. Trigger scoring and WAIT for them (only fires if NOT primed or x_messages reached)
            scoring_tasks = []
            for uid in window.participants:
                t = self._big_five_buffer.maybe_score(uid, self._provider_getter, self._llm_manager)
                if t:
                    scoring_tasks.append(t)
            
            if scoring_tasks:
                await asyncio.gather(*scoring_tasks)
            
            # 5. Analyze with fresh scores
            scope = event.group_id or "global"
            await self._orientation_analyzer.analyze(
                window, self._big_five_buffer, event.salience, scope,
                event_id=event.event_id,
                bot_persona_name=event.bot_persona_name,
            )
        except Exception as exc:
            logger.warning("[EventExtractor] IPC analysis failed: %s", exc)

    async def _batch_index_vectors(self, events: list) -> None:
        if self._encoder.dim == 0 or not events:
            return
        texts = []
        for event in events:
            text = event.topic
            if event.summary:
                text += " " + event.summary
            if event.chat_content_tags:
                text += " " + " ".join(event.chat_content_tags)
            texts.append(text.strip())
        valid_pairs = [(e, t) for e, t in zip(events, texts) if t]
        if not valid_pairs:
            return
        try:
            embeddings = await self._encoder.encode_batch([t for _, t in valid_pairs])
            await asyncio.gather(*[
                self._event_repo.upsert_vector(e.event_id, emb)
                for (e, _), emb in zip(valid_pairs, embeddings)
            ])
        except Exception as exc:
            logger.warning("[EventExtractor] batch vector indexing failed: %s", exc)

    async def _index_vector(self, event: Event) -> None:
        if self._encoder.dim == 0:
            return
        text = event.topic
        if event.summary:
            text += " " + event.summary
        if event.chat_content_tags:
            text += " " + " ".join(event.chat_content_tags)
        if not text.strip():
            return
        try:
            embedding = await self._encoder.encode(text)
            await self._event_repo.upsert_vector(event.event_id, embedding)
        except Exception as exc:
            logger.warning("[EventExtractor] vector indexing failed: %s", exc)

    async def _link_raw_messages(self, event_id: str, messages: list) -> None:
        if self._raw_message_repo is None:
            return
        message_ids = [
            str(getattr(message, "message_id", "") or "")
            for message in messages
            if getattr(message, "message_id", "")
        ]
        if not message_ids:
            return
        try:
            if self._raw_message_writer is not None:
                await self._raw_message_writer.ensure_flushed(message_ids)
            await self._raw_message_repo.link_event_messages(event_id, message_ids)
        except Exception as exc:
            logger.warning("[EventExtractor] raw message link failed: %s", exc)
