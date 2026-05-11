"""Persona synthesis and impression aggregation (weekly LLM tasks).

Both functions follow the same provider_getter pattern as EventExtractor:
a zero-arg callable so the provider can be resolved at call time.
On timeout or parse failure, the current record is left unchanged.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ..repository.base import EventRepository, ImpressionRepository, PersonaRepository
    from ..config import SynthesisConfig

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


async def run_persona_synthesis(
    persona_repo: PersonaRepository,
    event_repo: EventRepository,
    provider_getter: Callable,
    synthesis_config: SynthesisConfig | None = None,
) -> int:
    """Re-synthesise persona_attrs for all personas from recent events.

    content_tags: derived algorithmically from event tag frequency — no LLM needed
    since chat_content_tags are already canonical-normalised at write time.
    description + affect_type: still LLM-generated (require language understanding).

    Returns number of personas whose attrs were updated.
    """
    from collections import Counter
    from ..config import SynthesisConfig as _SC
    cfg = synthesis_config or _SC()

    provider = provider_getter()
    if provider is None:
        logger.debug("[Synthesis] no provider, skipping persona synthesis")
        return 0

    personas = await persona_repo.list_all()
    updated = 0

    for persona in personas:
        events = await event_repo.list_by_participant(persona.uid, limit=cfg.max_events)
        if not events:
            continue

        # --- Algorithmic: aggregate content_tags from event history ---
        tag_counter: Counter = Counter()
        for e in events:
            tag_counter.update(e.chat_content_tags)
        top_tags = [tag for tag, _ in tag_counter.most_common(5)]

        # --- LLM: generate description and affect_type only ---
        event_summaries = "\n".join(f"- {e.topic}" for e in events)
        prompt = (
            f"用户 {persona.primary_name}，近期参与事件：\n{event_summaries}\n"
            f"当前属性：{json.dumps(persona.persona_attrs, ensure_ascii=False)}。\n"
            "请更新属性。"
        )
        try:
            resp = await asyncio.wait_for(
                provider.text_chat(prompt=prompt, system_prompt=cfg.persona_system_prompt),
                timeout=cfg.llm_timeout,
            )
            parsed = _safe_parse(resp.completion_text)
            if parsed is None:
                logger.warning("[Synthesis] unparseable response for %s", persona.uid)
                continue

            new_attrs = dict(persona.persona_attrs)
            if "description" in parsed:
                new_attrs["description"] = str(parsed["description"])[:50]
            if "affect_type" in parsed:
                new_attrs["affect_type"] = str(parsed["affect_type"])
            # Always overwrite with the algorithmically-derived tags.
            new_attrs["content_tags"] = top_tags

            await persona_repo.upsert(dataclasses.replace(persona, persona_attrs=new_attrs))
            updated += 1

        except asyncio.TimeoutError:
            logger.warning("[Synthesis] timeout for persona %s", persona.uid)
        except Exception as exc:
            logger.warning("[Synthesis] failed for persona %s: %s", persona.uid, exc)

    logger.info("[Synthesis] persona synthesis: %d/%d updated", updated, len(personas))
    return updated


async def run_impression_recalculation(
    persona_repo: PersonaRepository,
    event_repo: EventRepository,
    impression_repo: ImpressionRepository,
) -> int:
    """Algorithmically recalculate derived impression fields and sync evidence_event_ids.

    No LLM call. For each impression:
      1. Recompute ipc_orientation / affect_intensity / r_squared / confidence
         from the current (benevolence, power) via ipc_model — keeps derived
         fields consistent if formula constants ever change.
      2. Rebuild evidence_event_ids by intersecting each pair's event sets
         (capped at 100 to bound DB growth).

    Returns the number of impressions updated.
    """
    from ..social.ipc_model import derive_fields

    personas = await persona_repo.list_all()
    all_impressions: list = []
    for persona in personas:
        all_impressions.extend(await impression_repo.list_by_observer(persona.uid))

    # Pre-load event sets for every uid that appears in any impression — one DB
    # query per uid instead of two per impression (avoids O(impressions) queries).
    uids_needed: set[str] = set()
    for imp in all_impressions:
        uids_needed.add(imp.observer_uid)
        uids_needed.add(imp.subject_uid)
    uid_event_ids: dict[str, set[str]] = {}
    for uid in uids_needed:
        events = await event_repo.list_by_participant(uid, limit=200)
        uid_event_ids[uid] = {e.event_id for e in events}

    updated = 0
    for imp in all_impressions:
        try:
            ipc_o, ai, rs = derive_fields(imp.benevolence, imp.power)

            # Rebuild evidence set from pre-loaded in-memory sets.
            obs_ids = uid_event_ids.get(imp.observer_uid, set())
            subj_ids = uid_event_ids.get(imp.subject_uid, set())
            shared = list(obs_ids & subj_ids)[-100:]

            new_imp = dataclasses.replace(
                imp,
                ipc_orientation=ipc_o,
                affect_intensity=ai,
                r_squared=rs,
                confidence=rs,
                evidence_event_ids=shared,
            )
            await impression_repo.upsert(new_imp)
            updated += 1
        except Exception as exc:
            logger.warning(
                "[Recalculation] failed for %s→%s: %s",
                imp.observer_uid[:8], imp.subject_uid[:8], exc,
            )

    logger.info("[Recalculation] impression recalculation: %d updated", updated)
    return updated
