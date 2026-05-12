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
import re
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
    description + big_five: still LLM-generated (require language understanding).

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
    updated_count = 0
    
    # Use a semaphore to limit concurrent LLM calls
    sem = asyncio.Semaphore(3)

    async def _process_one(persona) -> bool:
        # Optimization: Skip personas with no new activity since last synthesis
        last_synth = persona.persona_attrs.get("last_synthesized_at", 0)
        if persona.last_active_at <= last_synth and last_synth > 0:
            return False

        events = await event_repo.list_by_participant(persona.uid, limit=cfg.max_events)
        if not events:
            return False

        # --- Algorithmic: aggregate content_tags from event history ---
        tag_counter: Counter = Counter()
        for e in events:
            tag_counter.update(e.chat_content_tags)
        top_tags = [tag for tag, _ in tag_counter.most_common(5)]

        # --- LLM: generate description and big_five only ---
        event_summaries = "\n".join(f"- {e.topic}" for e in events)
        prompt = (
            f"用户 {persona.primary_name}，近期参与事件：\n{event_summaries}\n"
            f"当前属性：{json.dumps(persona.persona_attrs, ensure_ascii=False)}。\n"
            "请更新属性。"
        )
        
        async with sem:
            try:
                resp = await asyncio.wait_for(
                    provider.text_chat(prompt=prompt, system_prompt=cfg.persona_system_prompt),
                    timeout=cfg.llm_timeout,
                )
                parsed = _safe_parse(resp.completion_text)
                if parsed is None:
                    logger.warning("[Synthesis] unparseable response for %s", persona.uid)
                    return False

                new_attrs = dict(persona.persona_attrs)
                if "description" in parsed:
                    new_attrs["description"] = str(parsed["description"])[:80]
                if "big_five" in parsed and isinstance(parsed["big_five"], dict):
                    old_bf = persona.persona_attrs.get("big_five", {})
                    alpha = cfg.ema_alpha
                    merged_bf: dict[str, float] = {}
                    for k in ["O", "C", "E", "A", "N"]:
                        nv = parsed["big_five"].get(k)
                        if nv is not None and isinstance(nv, (int, float)):
                            new_clamped = max(-1.0, min(1.0, float(nv)))
                            ov = old_bf.get(k)
                            if ov is not None:
                                merged_bf[k] = round(alpha * new_clamped + (1 - alpha) * float(ov), 4)
                            else:
                                merged_bf[k] = new_clamped
                    if merged_bf:
                        new_attrs["big_five"] = merged_bf
                ev = parsed.get("big_five_evidence")
                if isinstance(ev, dict):
                    final_bf: dict[str, float] = new_attrs.get("big_five", {})
                    cleaned: dict[str, str] = {}
                    for k, v in ev.items():
                        if k not in ("O", "C", "E", "A", "N") or not isinstance(v, str) or not v.strip():
                            continue
                        sentence = str(v)[:120]
                        if k in final_bf:
                            correct_pct = round((final_bf[k] + 1) / 2 * 100)
                            sentence = re.sub(r"\d+%", f"{correct_pct}%", sentence)
                        cleaned[k] = sentence
                    new_attrs["big_five_evidence"] = cleaned
                elif isinstance(ev, str) and ev.strip():
                    new_attrs["big_five_evidence"] = str(ev)[:120]
                
                # Metadata update
                new_attrs["content_tags"] = top_tags
                new_attrs["last_synthesized_at"] = max(e.end_time for e in events)

                merged_bf_for_quality: dict = new_attrs.get("big_five", {})
                quality = len(merged_bf_for_quality) / 5.0
                old_conf = float(persona.confidence)
                new_confidence = round(alpha * quality + (1.0 - alpha) * old_conf, 4)

                await persona_repo.upsert(
                    dataclasses.replace(persona, confidence=new_confidence, persona_attrs=new_attrs)
                )
                return True

            except asyncio.TimeoutError:
                logger.warning("[Synthesis] timeout for persona %s", persona.uid)
            except Exception as exc:
                logger.warning("[Synthesis] failed for persona %s: %s", persona.uid, exc)
            return False

    results = await asyncio.gather(*[_process_one(p) for p in personas])
    updated_count = sum(1 for r in results if r)

    logger.info("[Synthesis] persona synthesis: %d/%d updated", updated_count, len(personas))
    return updated_count


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
