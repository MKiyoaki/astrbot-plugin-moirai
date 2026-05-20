"""LLM-based impression reanalysis for all participant pairs in a scope."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from itertools import permutations
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from core.repository.base import EventRepository, ImpressionRepository, PersonaRepository

logger = logging.getLogger(__name__)

_ALPHA = 0.4  # weight for new LLM score when blending with existing impression
_SEMAPHORE_LIMIT = 3


class ReanalyzeError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


async def reanalyze_impressions_llm(
    event_repo: "EventRepository",
    impression_repo: "ImpressionRepository",
    scope: str,
    bot_persona_name: str | None,
    provider_getter: Callable[[], Any],
    persona_repo: "PersonaRepository | None" = None,
    llm_manager: Any = None,
) -> int:
    """Reanalyze all participant-pair impressions in *scope* using an LLM.

    Pre-flight checks are done before any writes so existing data is safe.
    Returns the number of impressions updated.
    Raises ReanalyzeError on fatal pre-flight failures.
    """
    provider = provider_getter()
    if provider is None:
        raise ReanalyzeError("provider_none", "重新分析失败：没有可用 LLM provider。")

    group_id = None if scope == "global" else scope
    events = await event_repo.list_by_group(group_id, limit=1000, bot_persona_name=bot_persona_name)

    uid_to_name: dict[str, str] = {}
    if persona_repo is not None:
        try:
            personas = await persona_repo.list_all()
            uid_to_name = {p.uid: p.primary_name for p in personas if p.primary_name}
        except Exception:
            pass

    participant_events: dict[str, list] = {}
    for ev in events:
        for uid in (ev.participants or []):
            participant_events.setdefault(uid, []).append(ev)

    participants = list(participant_events.keys())
    if len(participants) < 2:
        raise ReanalyzeError("insufficient_data", "重新分析失败：该范围内参与者不足 2 人。")

    sem = asyncio.Semaphore(_SEMAPHORE_LIMIT)
    updated = 0

    async def _analyze_pair(obs_uid: str, subj_uid: str) -> bool:
        nonlocal updated
        obs_events = participant_events[obs_uid]
        subj_events_ids = {ev.event_id for ev in participant_events[subj_uid]}
        shared = [ev for ev in obs_events if ev.event_id in subj_events_ids]
        if not shared:
            return False

        obs_name = uid_to_name.get(obs_uid, obs_uid)
        subj_name = uid_to_name.get(subj_uid, subj_uid)
        summary_text = "\n".join(
            f"- [{ev.topic}] {ev.summary}" for ev in shared[-10:]
        )
        prompt = (
            f"Based on the following shared interaction events between {obs_name} (observer) "
            f"and {subj_name} (subject), rate the observer's impression of the subject.\n\n"
            f"{summary_text}\n\n"
            f"Return JSON with exactly two keys: \"benevolence\" (0.0-1.0, higher = more friendly/positive) "
            f"and \"power\" (0.0-1.0, higher = more dominant/authoritative). "
            f"Example: {{\"benevolence\": 0.7, \"power\": 0.3}}"
        )

        async with sem:
            try:
                resp = await provider.text_chat(prompt=prompt, system_prompt="")
                raw = resp.completion_text.strip()
                # Extract JSON object from response
                start = raw.find("{")
                end = raw.rfind("}") + 1
                if start < 0 or end <= start:
                    raise ValueError("no JSON object in response")
                data = json.loads(raw[start:end])
                b_new = float(data["benevolence"])
                p_new = float(data["power"])
            except Exception as exc:
                logger.warning("[reanalyze_llm] pair %s→%s skipped: %s", obs_uid, subj_uid, exc)
                return False

        from core.domain.models import Impression
        from core.social.ipc_model import classify_octant, affect_intensity, r_squared

        existing = await impression_repo.get(obs_uid, subj_uid, scope)
        if existing is not None:
            b_final = _ALPHA * b_new + (1 - _ALPHA) * existing.benevolence
            p_final = _ALPHA * p_new + (1 - _ALPHA) * existing.power
        else:
            b_final = b_new
            p_final = p_new

        b_e = b_final * 2 - 1  # [-1, 1]
        p_e = p_final * 2 - 1

        imp = Impression(
            observer_uid=obs_uid,
            subject_uid=subj_uid,
            ipc_orientation=classify_octant(b_e, p_e),
            benevolence=b_final,
            power=p_final,
            affect_intensity=affect_intensity(b_e, p_e),
            r_squared=r_squared(b_e, p_e),
            confidence=min(1.0, len(shared) / 10.0),
            scope=scope,
            evidence_event_ids=[ev.event_id for ev in shared[-20:]],
            last_reinforced_at=time.time(),
        )
        await impression_repo.upsert(imp)
        return True

    tasks = [_analyze_pair(obs, subj) for obs, subj in permutations(participants, 2)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    updated = sum(1 for r in results if r is True)
    return updated
