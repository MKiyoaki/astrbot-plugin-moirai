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
import time
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ..repository.base import EventRepository, ImpressionRepository, PersonaRepository
    from ..config import SynthesisConfig

logger = logging.getLogger(__name__)

_VALID_RELATIONS = frozenset({"friend", "colleague", "stranger", "family", "rival"})


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


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

    Returns number of personas whose attrs were updated.
    """
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
            if isinstance(parsed.get("content_tags"), list):
                new_attrs["content_tags"] = [str(t) for t in parsed["content_tags"][:5]]

            await persona_repo.upsert(dataclasses.replace(persona, persona_attrs=new_attrs))
            updated += 1

        except asyncio.TimeoutError:
            logger.warning("[Synthesis] timeout for persona %s", persona.uid)
        except Exception as exc:
            logger.warning("[Synthesis] failed for persona %s: %s", persona.uid, exc)

    logger.info("[Synthesis] persona synthesis: %d/%d updated", updated, len(personas))
    return updated


async def run_impression_aggregation(
    persona_repo: PersonaRepository,
    event_repo: EventRepository,
    impression_repo: ImpressionRepository,
    provider_getter: Callable,
    synthesis_config: SynthesisConfig | None = None,
) -> int:
    """Re-evaluate each impression from its evidence events.

    Returns number of impressions updated.
    """
    from ..config import SynthesisConfig as _SC
    cfg = synthesis_config or _SC()

    provider = provider_getter()
    if provider is None:
        logger.debug("[Aggregation] no provider, skipping impression aggregation")
        return 0

    personas = await persona_repo.list_all()
    all_impressions = []
    for persona in personas:
        all_impressions.extend(await impression_repo.list_by_observer(persona.uid))

    updated = 0

    for imp in all_impressions:
        if not imp.evidence_event_ids:
            continue

        events = []
        for eid in imp.evidence_event_ids[:cfg.max_events]:
            ev = await event_repo.get(eid)
            if ev is not None:
                events.append(ev)
        if not events:
            continue

        event_summaries = "\n".join(f"- {e.topic}" for e in events)
        current = (
            f"relation_type={imp.relation_type}, affect={imp.affect:.2f}, "
            f"intensity={imp.intensity:.2f}, confidence={imp.confidence:.2f}"
        )
        prompt = (
            f"观察者:{imp.observer_uid[:8]}，被观察者:{imp.subject_uid[:8]}。\n"
            f"依据事件：\n{event_summaries}\n"
            f"当前印象：{current}。\n"
            "请更新印象。"
        )
        try:
            resp = await asyncio.wait_for(
                provider.text_chat(prompt=prompt, system_prompt=cfg.impression_system_prompt),
                timeout=cfg.llm_timeout,
            )
            parsed = _safe_parse(resp.completion_text)
            if parsed is None:
                continue

            rel = str(parsed.get("relation_type", imp.relation_type))
            new_imp = dataclasses.replace(
                imp,
                relation_type=rel if rel in _VALID_RELATIONS else imp.relation_type,
                affect=_clamp(float(parsed.get("affect", imp.affect)), -1.0, 1.0),
                intensity=_clamp(float(parsed.get("intensity", imp.intensity)), 0.0, 1.0),
                confidence=_clamp(float(parsed.get("confidence", imp.confidence)), 0.0, 1.0),
                last_reinforced_at=time.time(),
            )
            await impression_repo.upsert(new_imp)
            updated += 1

        except asyncio.TimeoutError:
            logger.warning(
                "[Aggregation] timeout for %s→%s",
                imp.observer_uid[:8], imp.subject_uid[:8],
            )
        except Exception as exc:
            logger.warning(
                "[Aggregation] failed for %s→%s: %s",
                imp.observer_uid[:8], imp.subject_uid[:8], exc,
            )

    logger.info("[Aggregation] impression aggregation: %d updated", updated)
    return updated
