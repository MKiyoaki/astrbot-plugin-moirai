"""Persona synthesis and impression maintenance tasks."""
from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import re
import time
from collections import Counter
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import SynthesisConfig
    from ..managers.llm_manager import LLMTaskManager
    from ..repository.base import (
        EventRepository,
        ImpressionRepository,
        PersonaGroupRepository,
        PersonaRepository,
    )

logger = logging.getLogger(__name__)


def _safe_parse(text: str) -> dict | None:
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        return None


async def _synthesize_one_persona(
    *,
    persona,
    events: list,
    persona_repo,
    provider,
    cfg,
    llm_manager=None,
    log_prefix: str = "Synthesis",
    total_message_count: int | None = None,
    force: bool = False,
) -> bool:
    last_synth = persona.persona_attrs.get("last_synthesized_at", 0)
    if not force and persona.last_active_at <= last_synth and last_synth > 0:
        return False

    events = events[:cfg.max_events]
    if not events:
        return False

    tag_counter: Counter = Counter()
    for event in events:
        tag_counter.update(event.chat_content_tags)
    top_tags = [tag for tag, _ in tag_counter.most_common(5)]

    event_summaries = "\n".join(f"- {event.topic}" for event in events)

    # Gather per-event speaking-style observations for THIS persona. The extractor
    # keys participant_style by display name; match on primary_name, tolerating a
    # "#2" disambiguation suffix.
    style_lines: list[str] = []
    for event in events:
        ps = getattr(event, "participant_style", None) or {}
        entry = ps.get(persona.primary_name)
        if entry is None:
            for k, v in ps.items():
                if k.split("#", 1)[0] == persona.primary_name:
                    entry = v
                    break
        if isinstance(entry, dict):  # tolerate legacy {note, quotes} shape
            note = str(entry.get("note", "")).strip()
            quotes = [str(q).strip() for q in (entry.get("quotes") or []) if str(q).strip()]
            entry = (note + ("，" + "、".join(f"「{q}」" for q in quotes) if quotes else "")) or None
        if not isinstance(entry, str) or not entry.strip():
            continue
        style_lines.append(f"- {entry.strip()}")

    style_block = ""
    if style_lines:
        style_block = (
            "\n该用户在这些事件中的说话风格观察：\n"
            + "\n".join(style_lines[:12])
            + "\n"
        )

    prompt = (
        f"User {persona.primary_name}, recent events:\n{event_summaries}\n"
        f"{style_block}"
        f"Current attributes: {json.dumps(persona.persona_attrs, ensure_ascii=False)}.\n"
        "Update the persona attributes as JSON."
    )

    try:
        if llm_manager:
            resp = await llm_manager.run(
                asyncio.wait_for,
                provider.text_chat(prompt=prompt, system_prompt=cfg.persona_system_prompt),
                timeout=cfg.llm_timeout,
                task_name="synthesis",
            )
        else:
            resp = await asyncio.wait_for(
                provider.text_chat(prompt=prompt, system_prompt=cfg.persona_system_prompt),
                timeout=cfg.llm_timeout,
            )
        parsed = _safe_parse(resp.completion_text)
        if parsed is None:
            logger.warning("[%s] unparseable response for %s", log_prefix, persona.uid)
            return False

        new_attrs = dict(persona.persona_attrs)
        changed = False
        if "description" in parsed:
            new_attrs["description"] = str(parsed["description"])[:80]
            changed = True

        if "big_five" in parsed and isinstance(parsed["big_five"], dict):
            old_bf = persona.persona_attrs.get("big_five", {})
            merged_bf: dict[str, float] = {}
            for key in ["O", "C", "E", "A", "N"]:
                raw_value = parsed["big_five"].get(key)
                if raw_value is None or not isinstance(raw_value, (int, float)):
                    continue
                new_value = max(-1.0, min(1.0, float(raw_value)))
                old_value = old_bf.get(key)
                if old_value is not None:
                    merged_bf[key] = round(
                        cfg.ema_alpha * new_value + (1 - cfg.ema_alpha) * float(old_value),
                        4,
                    )
                else:
                    merged_bf[key] = new_value
            if merged_bf:
                new_attrs["big_five"] = merged_bf
                changed = True

            evidence = parsed.get("big_five_evidence")
            if isinstance(evidence, dict):
                final_bf: dict = new_attrs.get("big_five", {})
                cleaned: dict[str, str] = {}
                for key, value in evidence.items():
                    if key not in ("O", "C", "E", "A", "N") or not isinstance(value, str) or not value.strip():
                        continue
                    sentence = str(value)[:120]
                    if key in final_bf:
                        correct_pct = round((final_bf[key] + 1) / 2 * 100)
                        sentence = re.sub(r"\d+%", f"{correct_pct}%", sentence)
                    cleaned[key] = sentence
                new_attrs["big_five_evidence"] = cleaned
                changed = True
            elif isinstance(evidence, str) and evidence.strip():
                new_attrs["big_five_evidence"] = str(evidence)[:120]
                changed = True

        style = parsed.get("speaking_style")
        if isinstance(style, str) and style.strip():
            new_attrs["speaking_style"] = style.strip()[:200]
            changed = True
        quotes = parsed.get("style_quotes")
        if isinstance(quotes, list):
            clean_quotes = [str(q).strip()[:120] for q in quotes[:3] if str(q).strip()]
            if clean_quotes:
                new_attrs["style_quotes"] = clean_quotes
                changed = True

        if not changed:
            return False

        new_attrs["content_tags"] = top_tags
        new_attrs["last_synthesized_at"] = max(event.end_time for event in events)
        if total_message_count is not None:
            new_attrs["last_synthesized_message_count"] = int(total_message_count)
        new_attrs["last_synthesis_wall_time"] = time.time()

        merged_bf_for_quality: dict = new_attrs.get("big_five", {})
        quality = len(merged_bf_for_quality) / 5.0
        new_confidence = round(
            cfg.ema_alpha * quality + (1.0 - cfg.ema_alpha) * float(persona.confidence),
            4,
        )

        await persona_repo.upsert(
            dataclasses.replace(persona, confidence=new_confidence, persona_attrs=new_attrs)
        )
        return True

    except asyncio.TimeoutError:
        logger.warning("[%s] timeout for persona %s", log_prefix, persona.uid)
    except Exception as exc:
        logger.warning("[%s] failed for persona %s: %s", log_prefix, persona.uid, exc)
    return False


# ---------------------------------------------------------------------------
# Persona-group (cross-platform account binding) aware synthesis
# ---------------------------------------------------------------------------

async def _group_member_uids(group_repo, persona) -> list[str]:
    """Return all uids bound to ``persona``'s group, or ``[persona.uid]``."""
    if group_repo is None or not getattr(persona, "group_id", None):
        return [persona.uid]
    members = await group_repo.list_member_uids(persona.group_id)
    if persona.uid not in members:
        members.append(persona.uid)
    return members


async def _mirror_group_attrs(persona_repo, source_uid: str, member_uids: list[str]) -> None:
    """Copy the synthesized persona_attrs/confidence of one member to the rest.

    A bound group exposes one unified personality; mirroring keeps every
    member Persona (and thus the graph node, /mrm persona, recall) consistent.
    """
    source = await persona_repo.get(source_uid)
    if source is None:
        return
    for uid in member_uids:
        if uid == source_uid:
            continue
        member = await persona_repo.get(uid)
        if member is None:
            continue
        await persona_repo.upsert(
            dataclasses.replace(
                member,
                persona_attrs=dict(source.persona_attrs),
                confidence=source.confidence,
            )
        )


async def _synthesize_persona_or_group(
    *,
    persona,
    persona_repo,
    event_repo,
    group_repo,
    provider,
    cfg,
    llm_manager,
    log_prefix: str,
    message_counts: dict,
    force: bool = False,
) -> bool:
    """Synthesize one persona, aggregating across its bound group when present.

    For a bound group: events of every member are unioned, message counts are
    summed, the most-recently-active member is used as the synthesis target,
    and the result is mirrored to all members.
    """
    from ..social.persona_group import aggregate_events

    members = await _group_member_uids(group_repo, persona)

    if len(members) > 1:
        member_personas = [await persona_repo.get(u) for u in members]
        member_personas = [p for p in member_personas if p is not None]
        if not member_personas:
            return False
        target = max(member_personas, key=lambda p: p.last_active_at)
        events = await aggregate_events(event_repo, members, cfg.max_events)
        total = sum(int(message_counts.get(u, 0) or 0) for u in members)
    else:
        target = persona
        events = await event_repo.list_by_participant(persona.uid, limit=cfg.max_events)
        total = message_counts.get(persona.uid)

    ok = await _synthesize_one_persona(
        persona=target,
        events=events,
        persona_repo=persona_repo,
        provider=provider,
        cfg=cfg,
        llm_manager=llm_manager,
        log_prefix=log_prefix,
        total_message_count=total,
        force=force,
    )
    if ok and len(members) > 1:
        await _mirror_group_attrs(persona_repo, target.uid, members)
    return ok


async def synthesize_persona_group(
    persona_repo,
    group_repo,
    event_repo,
    provider_getter: Callable,
    group_id: str,
    synthesis_config: SynthesisConfig | None = None,
    llm_manager: LLMTaskManager | None = None,
) -> bool:
    """Force a fresh unified synthesis for one bound group.

    Called right after a bind/unbind so the merged personality reflects the
    new membership immediately.
    """
    from ..config import SynthesisConfig as _SC

    cfg = synthesis_config or _SC()
    provider = provider_getter()
    if provider is None:
        logger.debug("[Synthesis] no provider, skipping group synthesis for %s", group_id)
        return False

    member_uids = await group_repo.list_member_uids(group_id)
    member_personas = [await persona_repo.get(u) for u in member_uids]
    member_personas = [p for p in member_personas if p is not None]
    if not member_personas:
        return False

    message_counts = await event_repo.count_messages_by_uid_bulk()
    return await _synthesize_persona_or_group(
        persona=max(member_personas, key=lambda p: p.last_active_at),
        persona_repo=persona_repo,
        event_repo=event_repo,
        group_repo=group_repo,
        provider=provider,
        cfg=cfg,
        llm_manager=llm_manager,
        log_prefix="BindSynthesis",
        message_counts=message_counts,
        force=True,
    )


async def run_persona_synthesis(
    persona_repo: PersonaRepository,
    event_repo: EventRepository,
    provider_getter: Callable,
    synthesis_config: SynthesisConfig | None = None,
    llm_manager: LLMTaskManager | None = None,
    group_repo: "PersonaGroupRepository | None" = None,
) -> int:
    """Re-synthesize persona_attrs for all personas from recent events.

    When ``group_repo`` is provided, members of the same bound group are
    collapsed into a single unified synthesis.
    """
    from ..utils.perf import performance_timer

    async with performance_timer("task_synthesis"):
        from ..config import SynthesisConfig as _SC

        cfg = synthesis_config or _SC()

        provider = provider_getter()
        if provider is None:
            logger.debug("[Synthesis] no provider, skipping persona synthesis")
            return 0

        personas = await persona_repo.list_all()
        message_counts = await event_repo.count_messages_by_uid_bulk()

        seen_groups: set[str] = set()
        targets = []
        for persona in personas:
            if group_repo is not None and persona.group_id:
                if persona.group_id in seen_groups:
                    continue
                seen_groups.add(persona.group_id)
            targets.append(persona)

        async def _process_one(persona) -> bool:
            return await _synthesize_persona_or_group(
                persona=persona,
                persona_repo=persona_repo,
                event_repo=event_repo,
                group_repo=group_repo,
                provider=provider,
                cfg=cfg,
                llm_manager=llm_manager,
                log_prefix="Synthesis",
                message_counts=message_counts,
            )

        results = await asyncio.gather(*[_process_one(persona) for persona in targets])
        updated_count = sum(1 for result in results if result)

        logger.info("[Synthesis] persona synthesis: %d/%d updated", updated_count, len(targets))
        return updated_count


async def run_persona_synthesis_for_uid(
    persona_repo: PersonaRepository,
    event_repo: EventRepository,
    provider_getter: Callable,
    uid: str,
    synthesis_config: SynthesisConfig | None = None,
    llm_manager: LLMTaskManager | None = None,
    min_events: int = 1,
    total_message_count: int | None = None,
    group_repo: "PersonaGroupRepository | None" = None,
    force: bool = False,
) -> bool:
    """Synthesize exactly one persona (or its bound group) given enough events."""
    from ..config import SynthesisConfig as _SC
    from ..social.persona_group import aggregate_events

    cfg = synthesis_config or _SC()
    provider = provider_getter()
    if provider is None:
        logger.debug("[Synthesis] no provider, skipping persona synthesis for %s", uid)
        return False

    persona = await persona_repo.get(uid)
    if persona is None:
        return False

    members = await _group_member_uids(group_repo, persona)
    limit = max(cfg.max_events, min_events)
    if len(members) > 1:
        events = await aggregate_events(event_repo, members, limit)
    else:
        events = await event_repo.list_by_participant(uid, limit=limit)
    if len(events) < min_events:
        return False

    message_counts = await event_repo.count_messages_by_uid_bulk()
    return await _synthesize_persona_or_group(
        persona=persona,
        persona_repo=persona_repo,
        event_repo=event_repo,
        group_repo=group_repo,
        provider=provider,
        cfg=cfg,
        llm_manager=llm_manager,
        log_prefix="SynthesisTrigger",
        message_counts=message_counts,
        force=force,
    )


class PersonaSynthesisTrigger:
    """Message-count driven persona synthesis trigger with periodic fallback."""

    def __init__(
        self,
        *,
        persona_repo: PersonaRepository,
        event_repo: EventRepository,
        provider_getter: Callable,
        synthesis_config: SynthesisConfig,
        llm_manager: LLMTaskManager | None = None,
        min_messages: int = 30,
        min_events: int = 3,
        cooldown_hours: float = 3.0,
        fallback_staleness_hours: float = 72.0,
        group_repo: "PersonaGroupRepository | None" = None,
    ) -> None:
        self._persona_repo = persona_repo
        self._event_repo = event_repo
        self._provider_getter = provider_getter
        self._synthesis_config = synthesis_config
        self._llm_manager = llm_manager
        self._group_repo = group_repo
        self._min_messages = max(1, int(min_messages))
        self._min_events = max(1, int(min_events))
        self._cooldown_seconds = max(0.0, float(cooldown_hours) * 3600.0)
        self._fallback_staleness_seconds = max(60.0, float(fallback_staleness_hours) * 3600.0)
        self._running_uids: set[str] = set()

    async def handle_events(self, events: list) -> int:
        """Check affected UIDs after new Events are persisted."""
        affected: set[str] = set()
        for event in events:
            if getattr(event, "event_type", "episode") != "episode":
                continue
            for msg in getattr(event, "interaction_flow", []) or []:
                if getattr(msg, "sender_uid", None):
                    affected.add(msg.sender_uid)
            if not getattr(event, "interaction_flow", None):
                affected.update(getattr(event, "participants", []) or [])
        if not affected:
            return 0

        counts = await self._event_repo.count_messages_by_uid_bulk()
        return await self._run_for_uids(
            affected,
            counts,
            require_threshold=True,
            allow_stale=False,
        )

    async def run_fallback(self) -> int:
        """Low-frequency safety pass for missed triggers and stale dirty users."""
        counts = await self._event_repo.count_messages_by_uid_bulk()
        personas = await self._persona_repo.list_all()
        return await self._run_for_uids(
            {persona.uid for persona in personas},
            counts,
            require_threshold=False,
            allow_stale=True,
        )

    async def _run_for_uids(
        self,
        uids: set[str],
        counts: dict[str, int],
        *,
        require_threshold: bool,
        allow_stale: bool,
    ) -> int:
        updated = 0
        seen_groups: set[str] = set()
        for uid in sorted(uids):
            if uid in self._running_uids:
                continue
            persona = await self._persona_repo.get(uid)
            if persona is None:
                continue
            # Collapse bound-group members into a single unified synthesis,
            # counting messages across the whole group.
            if self._group_repo is not None and persona.group_id:
                if persona.group_id in seen_groups:
                    continue
                seen_groups.add(persona.group_id)
                members = await self._group_repo.list_member_uids(persona.group_id)
                if uid not in members:
                    members.append(uid)
                total_count = sum(int(counts.get(m, 0) or 0) for m in members)
            else:
                total_count = int(counts.get(uid, 0))
            if total_count <= 0:
                continue
            if not self._eligible(
                persona,
                total_count,
                require_threshold=require_threshold,
                allow_stale=allow_stale,
            ):
                continue
            if await self._run_one(persona, total_count):
                updated += 1
        return updated

    def _eligible(
        self,
        persona,
        total_count: int,
        *,
        require_threshold: bool,
        allow_stale: bool,
    ) -> bool:
        attrs = persona.persona_attrs or {}
        last_count = int(attrs.get("last_synthesized_message_count", 0) or 0)
        delta = total_count - last_count
        threshold_met = delta >= self._min_messages
        if require_threshold and not threshold_met:
            return False

        now = time.time()
        last_attempt = float(attrs.get("last_synthesis_attempt_at", 0) or 0)
        if last_attempt > 0 and now - last_attempt < self._cooldown_seconds:
            return False

        if allow_stale and not threshold_met:
            last_success = float(attrs.get("last_synthesis_wall_time", 0) or 0)
            stale = last_success <= 0 or now - last_success >= self._fallback_staleness_seconds
            if not stale or delta <= 0:
                return False

        return True

    async def _run_one(self, persona, total_count: int) -> bool:
        self._running_uids.add(persona.uid)
        try:
            now = time.time()
            member_uids = [persona.uid]
            if self._group_repo is not None and persona.group_id:
                member_uids = await self._group_repo.list_member_uids(persona.group_id)
                if persona.uid not in member_uids:
                    member_uids.append(persona.uid)
            # Stamp the attempt time on every member so the cooldown guard is
            # consistent across the whole bound group.
            for uid in member_uids:
                member = await self._persona_repo.get(uid)
                if member is None:
                    continue
                attrs = dict(member.persona_attrs or {})
                attrs["last_synthesis_attempt_at"] = now
                await self._persona_repo.upsert(
                    dataclasses.replace(member, persona_attrs=attrs)
                )
            return await run_persona_synthesis_for_uid(
                self._persona_repo,
                self._event_repo,
                self._provider_getter,
                persona.uid,
                synthesis_config=self._synthesis_config,
                llm_manager=self._llm_manager,
                min_events=self._min_events,
                total_message_count=total_count,
                group_repo=self._group_repo,
            )
        finally:
            self._running_uids.discard(persona.uid)


async def run_impression_recalculation(
    persona_repo: PersonaRepository,
    event_repo: EventRepository,
    impression_repo: ImpressionRepository,
) -> int:
    """Recalculate derived impression fields and evidence_event_ids."""
    from ..social.ipc_model import derive_fields

    personas = await persona_repo.list_all()
    all_impressions: list = []
    for persona in personas:
        all_impressions.extend(await impression_repo.list_by_observer(persona.uid))

    uids_needed: set[str] = set()
    for impression in all_impressions:
        uids_needed.add(impression.observer_uid)
        uids_needed.add(impression.subject_uid)

    uid_event_ids: dict[str, set[str]] = {}
    for uid in uids_needed:
        events = await event_repo.list_by_participant(uid, limit=200)
        uid_event_ids[uid] = {event.event_id for event in events}

    updated = 0
    for impression in all_impressions:
        try:
            ipc_orientation, affect, r_sq = derive_fields(
                impression.benevolence,
                impression.power,
            )
            observer_ids = uid_event_ids.get(impression.observer_uid, set())
            subject_ids = uid_event_ids.get(impression.subject_uid, set())
            shared = list(observer_ids & subject_ids)[-100:]

            await impression_repo.upsert(
                dataclasses.replace(
                    impression,
                    ipc_orientation=ipc_orientation,
                    affect_intensity=affect,
                    r_squared=r_sq,
                    confidence=r_sq,
                    evidence_event_ids=shared,
                )
            )
            updated += 1
        except Exception as exc:
            logger.warning(
                "[Recalculation] failed for %s->%s: %s",
                impression.observer_uid[:8],
                impression.subject_uid[:8],
                exc,
            )

    logger.info("[Recalculation] impression recalculation: %d updated", updated)
    return updated


async def run_consolidated_maintenance(
    persona_repo: PersonaRepository,
    event_repo: EventRepository,
    impression_repo: ImpressionRepository,
    provider_getter: Callable,
    synthesis_config: SynthesisConfig | None = None,
    llm_manager: LLMTaskManager | None = None,
    group_repo: "PersonaGroupRepository | None" = None,
) -> dict:
    """Run persona synthesis and impression recalculation with one shared preload."""
    from ..config import SynthesisConfig as _SC

    cfg = synthesis_config or _SC()
    provider = provider_getter()
    if provider is None:
        logger.debug("[ConsolidatedMaintenance] no provider, skipping synthesis")

    all_personas = await persona_repo.list_all()
    message_counts = await event_repo.count_messages_by_uid_bulk()

    uids: set[str] = {persona.uid for persona in all_personas}
    uid_events: dict[str, list] = {}
    for uid in uids:
        uid_events[uid] = await event_repo.list_by_participant(uid, limit=200)

    synthesized = 0
    if provider is not None:
        seen_groups: set[str] = set()
        synth_targets = []
        for persona in all_personas:
            if group_repo is not None and persona.group_id:
                if persona.group_id in seen_groups:
                    continue
                seen_groups.add(persona.group_id)
            synth_targets.append(persona)

        async def _synthesize_one(persona) -> bool:
            return await _synthesize_persona_or_group(
                persona=persona,
                persona_repo=persona_repo,
                event_repo=event_repo,
                group_repo=group_repo,
                provider=provider,
                cfg=cfg,
                llm_manager=llm_manager,
                log_prefix="ConsolidatedMaintenance",
                message_counts=message_counts,
            )

        results = await asyncio.gather(*[_synthesize_one(persona) for persona in synth_targets])
        synthesized = sum(1 for result in results if result)

    from ..social.ipc_model import derive_fields

    all_impressions: list = []
    for persona in all_personas:
        all_impressions.extend(await impression_repo.list_by_observer(persona.uid))

    uid_event_ids: dict[str, set[str]] = {
        uid: {event.event_id for event in events}
        for uid, events in uid_events.items()
    }
    extra_uids = {
        uid
        for impression in all_impressions
        for uid in (impression.observer_uid, impression.subject_uid)
        if uid not in uid_event_ids
    }
    for uid in extra_uids:
        events = await event_repo.list_by_participant(uid, limit=200)
        uid_event_ids[uid] = {event.event_id for event in events}

    recalculated = 0
    for impression in all_impressions:
        try:
            ipc_orientation, affect, r_sq = derive_fields(
                impression.benevolence,
                impression.power,
            )
            observer_ids = uid_event_ids.get(impression.observer_uid, set())
            subject_ids = uid_event_ids.get(impression.subject_uid, set())
            shared = list(observer_ids & subject_ids)[-100:]

            await impression_repo.upsert(
                dataclasses.replace(
                    impression,
                    ipc_orientation=ipc_orientation,
                    affect_intensity=affect,
                    r_squared=r_sq,
                    confidence=r_sq,
                    evidence_event_ids=shared,
                )
            )
            recalculated += 1
        except Exception as exc:
            logger.warning(
                "[ConsolidatedMaintenance] recalc failed for %s->%s: %s",
                impression.observer_uid[:8],
                impression.subject_uid[:8],
                exc,
            )

    logger.info(
        "[ConsolidatedMaintenance] done - synthesized: %d, recalculated: %d",
        synthesized,
        recalculated,
    )
    return {"synthesized": synthesized, "recalculated": recalculated}
