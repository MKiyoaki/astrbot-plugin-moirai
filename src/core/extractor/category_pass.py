"""Deferred classification of event interactions, and the tags derived from them.

Interaction labels are derived per fact-only summary segment; multiple groups
may apply to one segment. The accepted leaves become the event's tags. TypeSafe
is the calibrated fast path; an LLM pass covers the same static and previously
approved custom taxonomy when no key is configured.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import TYPE_CHECKING, Iterable, Sequence

from ..tags import (
    CATEGORY_CRITERIA,
    category_for_option,
    learn_category,
    set_learned_categories,
)
from ..utils.typesafe import TypeSafeClient
from .custom_tag_pass import generate_custom_tag
from .interaction_taxonomy import (
    CUSTOM_INTERACTION_GROUP_ID,
    INTERACTION_ABSTAIN_OPTION,
    UNCATEGORISED_TAG,
    INTERACTION_GROUPS,
    INTERACTION_LEAF_CRITERIA,
    INTERACTION_LEAF_TAGS,
    INTERACTION_SCHEMA_VERSION,
    add_custom_interaction_tag,
    custom_group_question,
    custom_leaf_question,
    group_question,
    leaf_question,
    set_custom_interaction_tags,
    tag_for_leaf,
)
from .interaction_pass_llm import classify_segments as llm_classify_segments
from .summary import split_subtopics, strip_evals

if TYPE_CHECKING:
    from ..config import TypeSafeConfig
    from ..domain.models import Event
    from ..repository.base import EventRepository

logger = logging.getLogger(__name__)

_LLM_TAG_LIMIT = 3
_MAX_TAG_QUESTIONS = 24
_MAX_SUMMARY_CHARS = 6000
_MAX_INTERACTION_SEGMENTS = 12
_CONCURRENCY = 2
_BACKFILL_MAX_REQUESTS = 200
_EVENT_BACKFILL_MAX_EVENTS = 100
_BACKFILL_SCAN_EVENTS = 5000
_BACKFILL_MAX_CONSECUTIVE_FAILURES = 5
_CUSTOM_TAG_LIMIT = 50
_CUSTOM_TAG_ATTEMPTS = 2
_CUSTOM_TAG_JUDGE_KEY = "custom_tag_judge"


def _tag_key(index: int) -> str:
    return f"tag_{index}"


def _group_key(segment_index: int, group_id: str) -> str:
    return f"segment_{segment_index}_group_{group_id}"


def _leaf_key(segment_index: int, group_id: str) -> str:
    return f"segment_{segment_index}_leaf_{group_id}"



def _tag_instructions(tag: str) -> str:
    return (
        f'Which topic category does the tag "{tag}" belong to, judged in the '
        "context of this chat memory event? Choose 'other' only if no category fits."
    )


def build_segments(event: "Event") -> list[str]:
    """Return bounded fact-only summary segments used for interaction questions."""
    summary = strip_evals(event.summary or "").strip()[:_MAX_SUMMARY_CHARS]
    segments = split_subtopics(summary)
    if not segments and summary:
        segments = [summary]
    return segments[:_MAX_INTERACTION_SEGMENTS]


def build_state(event: "Event") -> str:
    """Build the exact topic, tags and fact-only summary sent to TypeSafe."""
    topic = (event.topic or "").strip()
    tags = ", ".join(str(tag) for tag in (event.chat_content_tags or []))
    segments = build_segments(event)
    summary = "\n".join(
        f"[Segment {index}] {segment}" for index, segment in enumerate(segments)
    )
    return f"Topic: {topic}\nTags: {tags}\nSummary:\n{summary}"


def build_custom_tag_state(event: "Event") -> str:
    """Build the narrower topic-and-summary state allowed for custom tagging."""
    topic = (event.topic or "").strip()
    summary = "\n".join(
        f"[Segment {index}] {segment}"
        for index, segment in enumerate(build_segments(event))
    )
    return f"Topic: {topic}\nSummary:\n{summary}"


def event_source_hash(event: "Event") -> str:
    """Identify the privacy-bounded input so stale classifications are detectable."""
    return hashlib.sha256(build_state(event).encode("utf-8")).hexdigest()


def derive_tags(payload: dict, *, limit: int | None = None) -> list[str]:
    """Rank accepted interaction leaves into their Chinese event tags.

    The TypeSafe pass already gates on a calibrated threshold, so every accepted
    leaf is kept. The LLM pass passes a limit because its confidence is not
    calibrated against the same scale.
    """
    best: dict[str, float] = {}
    for segment in payload.get("segments") or []:
        for label in segment.get("labels") or []:
            if not label.get("accepted"):
                continue
            subtype = str(label.get("subtype") or "").strip()
            if not subtype:
                continue
            if label.get("group") == CUSTOM_INTERACTION_GROUP_ID:
                tag = subtype
            else:
                tag = tag_for_leaf(subtype)
            if not tag:
                continue
            weight = float(label.get("score") or 0.0) * float(
                label.get("confidence") or 0.0
            )
            if weight > best.get(tag, -1.0):
                best[tag] = weight
    ranked = sorted(best, key=lambda tag: (-best[tag], tag))
    if limit is not None:
        ranked = ranked[:limit]
    if ranked:
        return ranked
    resolution = payload.get("custom_resolution") or {}
    if resolution.get("status") == "accepted":
        selected = str(resolution.get("selected_tag") or "").strip()
        if selected:
            return [selected]
    return [UNCATEGORISED_TAG]


class EventCategoryClassifier:
    """Own TypeSafe topic caching, interaction passes and background tasks."""

    def __init__(
        self,
        client: TypeSafeClient | None,
        event_repo: "EventRepository",
        *,
        provider_getter=None,
        min_confidence: float = 0.5,
        custom_tag_min_score: float = 0.7,
        concurrency: int = _CONCURRENCY,
        topic_enabled: bool = True,
        event_enabled: bool = True,
        topic_backfill: bool = True,
        event_backfill: bool = False,
    ) -> None:
        self._client = client
        self._provider_getter = provider_getter
        self._event_repo = event_repo
        self._min_confidence = min(max(float(min_confidence), 0.0), 1.0)
        self._custom_tag_min_score = min(
            max(float(custom_tag_min_score), 0.0), 1.0
        )
        self._topic_enabled = topic_enabled
        self._event_enabled = event_enabled
        self._topic_backfill = topic_backfill
        self._event_backfill = event_backfill
        self._semaphore = asyncio.Semaphore(max(1, concurrency))
        self._asked: set[str] = set()
        self._inflight: set[str] = set()
        self._tasks: set[asyncio.Task] = set()
        self._backfill_task: asyncio.Task | None = None

    @property
    def _typesafe_usable(self) -> bool:
        return self._client is not None and self._client.usable

    @property
    def _interaction_via_llm(self) -> bool:
        return (
            self._event_enabled
            and not self._typesafe_usable
            and self._provider_getter is not None
        )

    @property
    def active(self) -> bool:
        if self._typesafe_usable and (self._topic_enabled or self._event_enabled):
            return True
        return self._interaction_via_llm

    async def load(self) -> None:
        """Load stored topic answers and activate the confident tag mappings."""
        custom_tags = await self._event_repo.list_all_custom_interaction_tags()
        set_custom_interaction_tags(custom_tags)
        if not self._typesafe_usable:
            return
        rows = await self._event_repo.get_tag_categories()
        self._asked = set(rows)
        set_learned_categories({
            tag: category
            for tag, (category, confidence) in rows.items()
            if category and confidence >= self._min_confidence
        })

    def schedule(self, events: Iterable["Event"]) -> None:
        """Classify events in the background and return immediately."""
        if not self.active:
            return
        for event in events:
            task = asyncio.create_task(self._run(event))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def schedule_reclassify(self, event: "Event") -> None:
        """Clear stale interaction output and classify the changed event again."""
        if not self.active:
            return
        try:
            await self._event_repo.set_interaction_classification(event.event_id, {})
        except Exception as exc:
            logger.warning(
                "[CategoryPass] could not reset classifications for %s: %s",
                event.event_id[:8],
                exc,
            )
            return
        event.interaction_classification = {}
        self.schedule([event])

    async def _run(self, event: "Event") -> None:
        async with self._semaphore:
            await self.classify_event(event)

    def _claim(self, tags: Iterable[str]) -> list[str]:
        if not self._topic_enabled:
            return []
        pending: list[str] = []
        seen: set[str] = set()
        for tag in tags:
            text = str(tag or "").strip()
            if not text or text in seen or text in self._asked or text in self._inflight:
                continue
            seen.add(text)
            pending.append(text)
            if len(pending) == _MAX_TAG_QUESTIONS:
                break
        self._inflight.update(pending)
        return pending

    async def classify_event(
        self,
        event: "Event",
        *,
        include_event: bool = True,
        tags: Sequence[str] | None = None,
    ) -> bool:
        """Classify unseen tags and, when requested, the event summary segments."""
        if not self.active:
            return False
        custom_tags = await self._event_repo.list_custom_interaction_tags(
            event.bot_persona_name
        )
        if self._interaction_via_llm:
            return await self._classify_interaction_llm(event, custom_tags)
        pending = self._claim(event.chat_content_tags if tags is None else tags)
        want_event = (
            self._event_enabled
            and include_event
            and not event.interaction_classification
        )
        segments = build_segments(event) if want_event else []
        choices = {
            _tag_key(index): (_tag_instructions(tag), CATEGORY_CRITERIA)
            for index, tag in enumerate(pending)
        }
        nouls = {
            _group_key(segment_index, group_id): group_question(segment_index, group_id)
            for segment_index in range(len(segments))
            for group_id in INTERACTION_GROUPS
        }
        if custom_tags:
            nouls.update({
                _group_key(segment_index, CUSTOM_INTERACTION_GROUP_ID):
                    custom_group_question(segment_index, custom_tags)
                for segment_index in range(len(segments))
            })
        wrote = False
        try:
            if not choices and not nouls:
                if want_event:
                    payload = self._interaction_payload(event, [], {}, {}, complete=True)
                    await self._event_repo.set_interaction_classification(event.event_id, payload)
                    event.interaction_classification = payload
                    wrote = True
                return wrote
            answers = await self._client.ask(
                build_state(event), choices=choices, nouls=nouls,
            )
            rows: dict[str, tuple[str, float]] = {}
            for index, tag in enumerate(pending):
                answer = answers.choices.get(_tag_key(index))
                if answer is not None:
                    rows[tag] = (
                        category_for_option(answer.choice) or "",
                        answer.confidence,
                    )
            if rows:
                await self._event_repo.upsert_tag_categories(rows)
                self._asked.update(rows)
                for tag, (category, confidence) in rows.items():
                    if category and confidence >= self._min_confidence:
                        learn_category(tag, category)
                wrote = True

            if want_event and segments:
                expected = set(nouls)
                if not expected.issubset(answers.nouls):
                    logger.warning(
                        "[CategoryPass] incomplete interaction groups for %s; event result not stored",
                        event.event_id[:8],
                    )
                    return wrote
                group_scores = {
                    (segment_index, group_id): answers.nouls[
                        _group_key(segment_index, group_id)
                    ].value
                    for segment_index in range(len(segments))
                    for group_id in (
                        *INTERACTION_GROUPS,
                        *([CUSTOM_INTERACTION_GROUP_ID] if custom_tags else []),
                    )
                }
                active = [
                    (segment_index, group_id)
                    for (segment_index, group_id), score in group_scores.items()
                    if score >= self._min_confidence
                ]
                leaf_answers = {}
                complete = True
                if active:
                    leaf_choices = {
                        _leaf_key(segment_index, group_id): (
                            (
                                custom_leaf_question(segment_index)
                                if group_id == CUSTOM_INTERACTION_GROUP_ID
                                else leaf_question(segment_index, group_id)
                            ),
                            (
                                self._custom_leaf_criteria(custom_tags)
                                if group_id == CUSTOM_INTERACTION_GROUP_ID
                                else INTERACTION_LEAF_CRITERIA[group_id]
                            ),
                        )
                        for segment_index, group_id in active
                    }
                    try:
                        leaf_answers = (
                            await self._client.choices(build_state(event), leaf_choices)
                        )
                        complete = set(leaf_choices).issubset(leaf_answers)
                    except Exception as exc:
                        complete = False
                        logger.warning(
                            "[CategoryPass] interaction refinement failed for %s: %s",
                            event.event_id[:8],
                            exc,
                        )
                payload = self._interaction_payload(
                    event, segments, group_scores, leaf_answers, complete=complete,
                )
                payload = await self._resolve_uncategorised(
                    event, payload, segments, custom_tags
                )
                await self._event_repo.set_interaction_classification(event.event_id, payload)
                event.interaction_classification = payload
                await self._apply_derived_tags(event, payload)
                wrote = True
            elif want_event:
                payload = self._interaction_payload(event, [], {}, {}, complete=True)
                await self._event_repo.set_interaction_classification(event.event_id, payload)
                event.interaction_classification = payload
                wrote = True
            return wrote
        except Exception as exc:
            logger.warning(
                "[CategoryPass] classification failed for %s: %s",
                event.event_id[:8],
                exc,
            )
            return wrote
        finally:
            self._inflight.difference_update(pending)

    def _interaction_payload(
        self,
        event: "Event",
        segments: Sequence[str],
        group_scores: dict[tuple[int, str], float],
        leaf_answers: dict,
        *,
        complete: bool,
    ) -> dict:
        output_segments = []
        for segment_index, _ in enumerate(segments):
            group_ids = [*INTERACTION_GROUPS]
            if (segment_index, CUSTOM_INTERACTION_GROUP_ID) in group_scores:
                group_ids.append(CUSTOM_INTERACTION_GROUP_ID)
            scores = {
                group_id: group_scores[(segment_index, group_id)]
                for group_id in group_ids
                if (segment_index, group_id) in group_scores
            }
            labels = []
            for group_id, score in scores.items():
                if score < self._min_confidence:
                    continue
                answer = leaf_answers.get(_leaf_key(segment_index, group_id))
                subtype = ""
                confidence = None
                accepted = False
                if answer is not None:
                    confidence = answer.confidence
                    if answer.choice != INTERACTION_ABSTAIN_OPTION:
                        subtype = answer.choice
                        accepted = confidence >= self._min_confidence
                labels.append({
                    "group": group_id,
                    "score": score,
                    "subtype": subtype,
                    "confidence": confidence,
                    "accepted": accepted,
                })
            output_segments.append({
                "index": segment_index,
                "group_scores": scores,
                "labels": labels,
            })
        return {
            "version": INTERACTION_SCHEMA_VERSION,
            "source_hash": event_source_hash(event),
            "threshold": self._min_confidence,
            "complete": complete,
            "segments": output_segments,
        }

    @staticmethod
    def _custom_leaf_criteria(tags: Sequence[str]) -> dict[str, dict]:
        criteria = {
            tag: {
                "what": f"The segment's interaction function is '{tag}'.",
                "not_for": "A topic, named entity, one-off detail, or a different interaction.",
                "examples": [],
            }
            for tag in tags
        }
        criteria[INTERACTION_ABSTAIN_OPTION] = {
            "what": "None of the declared custom interaction tags fits clearly.",
            "not_for": "Any segment that clearly performs one declared custom interaction.",
            "examples": [],
        }
        return criteria

    async def _resolve_uncategorised(
        self,
        event: "Event",
        payload: dict,
        segments: Sequence[str],
        custom_tags: Sequence[str],
    ) -> dict:
        if (
            not payload.get("complete")
            or not segments
            or derive_tags(payload) != [UNCATEGORISED_TAG]
        ):
            return payload
        resolution = {
            "status": "unavailable",
            "attempts": [],
            "selected_tag": "",
            "source": "",
        }
        payload["custom_resolution"] = resolution
        try:
            provider = (
                self._provider_getter()
                if self._provider_getter is not None
                else None
            )
        except Exception as exc:
            logger.warning(
                "[CategoryPass] custom tag provider unavailable for %s: %s",
                event.event_id[:8],
                exc,
            )
            return payload
        if not self._typesafe_usable or provider is None:
            return payload

        existing = list(custom_tags)
        existing_set = set(existing)
        static_tags = set(INTERACTION_LEAF_TAGS.values())
        rejected: list[str] = []
        custom_state = build_custom_tag_state(event)
        resolution["status"] = "exhausted"
        for _ in range(_CUSTOM_TAG_ATTEMPTS):
            allow_new = len(existing_set) < _CUSTOM_TAG_LIMIT
            candidate = await generate_custom_tag(
                provider,
                custom_state,
                existing,
                rejected,
                allow_new=allow_new,
            )
            if (
                not candidate
                or candidate == UNCATEGORISED_TAG
                or candidate in rejected
            ):
                resolution["attempts"].append({
                    "tag": candidate,
                    "score": None,
                    "result": "invalid",
                    "source": "",
                })
                if candidate and candidate not in rejected:
                    rejected.append(candidate)
                continue
            if candidate in static_tags:
                source = "static"
            elif candidate in existing_set:
                source = "custom_existing"
            else:
                source = "custom_new"
            if source == "custom_new" and not allow_new:
                resolution["attempts"].append({
                    "tag": candidate,
                    "score": None,
                    "result": "capacity",
                    "source": source,
                })
                rejected.append(candidate)
                continue

            judge_state = (
                f"{custom_state}\nProposed reusable interaction tag: {candidate}"
            )
            judge_question = (
                f"To what extent does the proposed tag '{candidate}' accurately and "
                "reusably describe the central interaction function in this event? "
                "Score low for topics, named entities, one-off details, or labels that "
                "are too vague to distinguish an interaction."
            )
            attempt = {
                "tag": candidate,
                "score": None,
                "result": "judge_error",
                "source": source,
            }
            try:
                answers = await self._client.ask(
                    judge_state,
                    nouls={_CUSTOM_TAG_JUDGE_KEY: judge_question},
                )
            except Exception as exc:
                logger.warning(
                    "[CategoryPass] custom tag judge failed for %s: %s",
                    event.event_id[:8],
                    exc,
                )
                resolution["attempts"].append(attempt)
                resolution["status"] = "error"
                return payload
            answer = answers.nouls.get(_CUSTOM_TAG_JUDGE_KEY)
            if answer is None:
                resolution["attempts"].append(attempt)
                resolution["status"] = "error"
                return payload
            score = answer.value
            accepted = score >= self._custom_tag_min_score
            attempt["score"] = score
            attempt["result"] = "accepted" if accepted else "rejected"
            resolution["attempts"].append(attempt)
            if not accepted:
                rejected.append(candidate)
                continue

            if source == "custom_new":
                try:
                    registered = await self._event_repo.register_custom_interaction_tag(
                        event.bot_persona_name,
                        candidate,
                        limit=_CUSTOM_TAG_LIMIT,
                    )
                except Exception as exc:
                    logger.warning(
                        "[CategoryPass] custom tag registration failed for %s: %s",
                        event.event_id[:8],
                        exc,
                    )
                    attempt["result"] = "error"
                    resolution["status"] = "error"
                    return payload
                if registered == "full":
                    attempt["result"] = "capacity"
                    rejected.append(candidate)
                    continue
                if registered == "existing":
                    source = "custom_existing"
                    attempt["source"] = source
            if source in {"custom_existing", "custom_new"}:
                add_custom_interaction_tag(candidate)
            resolution.update({
                "status": "accepted",
                "selected_tag": candidate,
                "source": source,
            })
            return payload
        return payload

    async def _classify_interaction_llm(
        self, event: "Event", custom_tags: Sequence[str],
    ) -> bool:
        """Fill the interaction payload from one chat completion instead of TypeSafe."""
        if event.interaction_classification:
            return False
        segments = build_segments(event)
        if not segments:
            payload = self._interaction_payload(event, [], {}, {}, complete=True)
            await self._event_repo.set_interaction_classification(event.event_id, payload)
            event.interaction_classification = payload
            await self._apply_derived_tags(event, payload, limit=_LLM_TAG_LIMIT)
            return True
        labels = await llm_classify_segments(
            self._provider_getter(), build_state(event), segments, custom_tags,
        )
        if labels is None:
            return False
        output_segments = []
        for segment_index in range(len(segments)):
            entries = labels.get(segment_index) or []
            output_segments.append({
                "index": segment_index,
                "group_scores": {
                    entry["group"]: entry["confidence"] for entry in entries
                },
                "labels": [
                    {
                        "group": entry["group"],
                        "score": entry["confidence"],
                        "subtype": entry["subtype"],
                        "confidence": entry["confidence"],
                        "accepted": entry["confidence"] >= self._min_confidence,
                    }
                    for entry in entries
                ],
            })
        payload = {
            "version": INTERACTION_SCHEMA_VERSION,
            "source_hash": event_source_hash(event),
            "threshold": self._min_confidence,
            "complete": True,
            "backend": "llm",
            "segments": output_segments,
        }
        payload = await self._resolve_uncategorised(
            event, payload, segments, custom_tags
        )
        try:
            await self._event_repo.set_interaction_classification(event.event_id, payload)
        except Exception as exc:
            logger.warning(
                "[CategoryPass] could not store llm interaction result for %s: %s",
                event.event_id[:8],
                exc,
            )
            return False
        event.interaction_classification = payload
        await self._apply_derived_tags(event, payload, limit=_LLM_TAG_LIMIT)
        return True

    async def _apply_derived_tags(
        self, event: "Event", payload: dict, *, limit: int | None = None,
    ) -> None:
        """Replace the event's tags with the ranked accepted interaction leaves."""
        tags = derive_tags(payload, limit=limit)
        if not tags or list(event.chat_content_tags or []) == tags:
            return
        try:
            await self._event_repo.set_chat_content_tags(event.event_id, tags)
        except Exception as exc:
            logger.warning(
                "[CategoryPass] could not write derived tags for %s: %s",
                event.event_id[:8],
                exc,
            )
            return
        event.chat_content_tags = tags

    async def backfill(self, max_requests: int = _BACKFILL_MAX_REQUESTS) -> int:
        """Classify old tags that have no stored topic answer."""
        if not self._topic_enabled:
            return 0
        counts = await self._event_repo.count_tags()
        pending = {tag for tag in counts if tag not in self._asked}
        if not pending:
            return 0
        events = await self._event_repo.list_all(limit=_BACKFILL_SCAN_EVENTS)
        requests = failures = 0
        for event in events:
            if requests >= max_requests or not pending or not self.active:
                break
            wanted = [tag for tag in event.chat_content_tags if tag in pending]
            if not wanted:
                continue
            requests += 1
            await self.classify_event(event, include_event=False, tags=wanted)
            resolved = {tag for tag in wanted if tag in self._asked}
            pending -= resolved
            failures = 0 if resolved else failures + 1
            if failures >= _BACKFILL_MAX_CONSECUTIVE_FAILURES:
                logger.warning(
                    "[CategoryPass] topic backfill stopped after %d failed requests",
                    failures,
                )
                break
        logger.info(
            "[CategoryPass] topic backfill: %d request(s), %d tag(s) still unclassified",
            requests,
            len(pending),
        )
        return requests

    async def backfill_events(
        self, max_events: int = _EVENT_BACKFILL_MAX_EVENTS,
    ) -> int:
        """Classify recent stored events without interaction output, newest first."""
        if not self._event_enabled:
            return 0
        events = await self._event_repo.list_all(limit=_BACKFILL_SCAN_EVENTS)
        classified = failures = 0
        for event in events:
            if classified >= max_events or not self.active:
                break
            if event.interaction_classification:
                continue
            changed = await self.classify_event(event, tags=[])
            if changed and event.interaction_classification:
                classified += 1
                failures = 0
            else:
                failures += 1
            if failures >= _BACKFILL_MAX_CONSECUTIVE_FAILURES:
                logger.warning(
                    "[CategoryPass] event backfill stopped after %d failed events",
                    failures,
                )
                break
        logger.info("[CategoryPass] event backfill: %d event(s)", classified)
        return classified

    def start_backfill(self) -> None:
        if (
            not self.active
            or self._backfill_task is not None
            or not (self._topic_backfill or self._event_backfill)
        ):
            return
        self._backfill_task = asyncio.create_task(self._backfill_guarded())

    async def _backfill_guarded(self) -> None:
        try:
            if self._topic_backfill:
                await self.backfill()
            if self._event_backfill:
                await self.backfill_events()
        except Exception as exc:
            logger.warning("[CategoryPass] backfill failed: %s", exc)

    async def drain(self) -> None:
        """Wait for every scheduled classification to finish."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def close(self) -> None:
        """Cancel backfill, finish scheduled work and release the HTTP client."""
        if self._backfill_task is not None:
            self._backfill_task.cancel()
            await asyncio.gather(self._backfill_task, return_exceptions=True)
            self._backfill_task = None
        await self.drain()
        if self._client is not None:
            await self._client.aclose()


def build_category_classifier(
    cfg: "TypeSafeConfig",
    event_repo: "EventRepository",
    provider_getter=None,
) -> EventCategoryClassifier | None:
    """Build the classifier, or return None when no classification axis can run.

    With no usable TypeSafe key the interaction axis still runs on the extraction
    provider, so a missing key costs calibration and money rather than the tags
    the rest of the pipeline depends on.
    """
    use_llm = cfg.interaction_via_llm and provider_getter is not None
    if not cfg.active and not use_llm:
        return None
    client = None
    if cfg.active:
        client = TypeSafeClient(
            cfg.api_key,
            base_url=cfg.base_url,
            model=cfg.model,
            timeout=cfg.timeout,
        )
    return EventCategoryClassifier(
        client,
        event_repo,
        provider_getter=provider_getter,
        min_confidence=cfg.min_confidence,
        custom_tag_min_score=cfg.custom_tag_min_score,
        topic_enabled=cfg.topic_enabled,
        event_enabled=cfg.event_enabled,
        topic_backfill=cfg.topic_backfill,
        event_backfill=cfg.event_backfill,
    )
