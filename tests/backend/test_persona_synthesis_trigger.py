from __future__ import annotations

import time

import pytest

from core.domain.models import Event, MessageRef, Persona
from core.repository.memory import InMemoryEventRepository, InMemoryPersonaRepository
from core.tasks.synthesis import PersonaSynthesisTrigger
from core.config import SynthesisConfig


class _MockResponse:
    def __init__(self, text: str) -> None:
        self.completion_text = text


class _MockProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def text_chat(self, prompt: str = "", system_prompt: str = "") -> _MockResponse:
        self.calls.append(prompt)
        return _MockResponse('{"description":"updated","big_five":{"O":0.4}}')


def _persona(uid: str = "u1") -> Persona:
    return Persona(
        uid=uid,
        bound_identities=[("qq", uid)],
        primary_name="Alice",
        persona_attrs={},
        confidence=0.5,
        created_at=1.0,
        last_active_at=5000.0,
    )


def _event(event_id: str, uid: str = "u1", messages: int = 2, end_time: float = 1000.0) -> Event:
    return Event(
        event_id=event_id,
        group_id="g1",
        start_time=end_time - 10,
        end_time=end_time,
        participants=[uid],
        interaction_flow=[
            MessageRef(sender_uid=uid, timestamp=end_time + i, content_hash="", content_preview="hello")
            for i in range(messages)
        ],
        topic="topic",
        summary="summary",
        chat_content_tags=["tag"],
        salience=0.5,
        confidence=0.8,
        last_accessed_at=end_time,
    )


@pytest.mark.asyncio
async def test_persona_synthesis_trigger_runs_when_message_threshold_reached() -> None:
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    provider = _MockProvider()
    await pr.upsert(_persona())
    ev1 = _event("e1", messages=2, end_time=1000.0)
    ev2 = _event("e2", messages=2, end_time=2000.0)
    await er.upsert(ev1)
    await er.upsert(ev2)

    trigger = PersonaSynthesisTrigger(
        persona_repo=pr,
        event_repo=er,
        provider_getter=lambda: provider,
        synthesis_config=SynthesisConfig(ema_alpha=1.0),
        min_messages=4,
        min_events=2,
        cooldown_hours=0,
    )

    updated = await trigger.handle_events([ev2])

    assert updated == 1
    assert len(provider.calls) == 1
    persona = await pr.get("u1")
    assert persona is not None
    assert persona.persona_attrs["description"] == "updated"
    assert persona.persona_attrs["last_synthesized_message_count"] == 4


@pytest.mark.asyncio
async def test_persona_synthesis_trigger_skips_below_threshold() -> None:
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    provider = _MockProvider()
    await pr.upsert(_persona())
    ev = _event("e1", messages=2)
    await er.upsert(ev)

    trigger = PersonaSynthesisTrigger(
        persona_repo=pr,
        event_repo=er,
        provider_getter=lambda: provider,
        synthesis_config=SynthesisConfig(),
        min_messages=3,
        min_events=1,
        cooldown_hours=0,
    )

    assert await trigger.handle_events([ev]) == 0
    assert provider.calls == []


@pytest.mark.asyncio
async def test_persona_synthesis_trigger_respects_cooldown() -> None:
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    provider = _MockProvider()
    persona = _persona()
    persona.persona_attrs["last_synthesis_attempt_at"] = time.time()
    await pr.upsert(persona)
    ev = _event("e1", messages=5)
    await er.upsert(ev)

    trigger = PersonaSynthesisTrigger(
        persona_repo=pr,
        event_repo=er,
        provider_getter=lambda: provider,
        synthesis_config=SynthesisConfig(),
        min_messages=3,
        min_events=1,
        cooldown_hours=1,
    )

    assert await trigger.handle_events([ev]) == 0
    assert provider.calls == []


@pytest.mark.asyncio
async def test_persona_synthesis_fallback_runs_for_stale_uid_below_threshold() -> None:
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    provider = _MockProvider()
    persona = _persona()
    persona.persona_attrs["last_synthesized_message_count"] = 0
    persona.persona_attrs["last_synthesis_wall_time"] = 1.0
    await pr.upsert(persona)
    ev = _event("e1", messages=2)
    await er.upsert(ev)

    trigger = PersonaSynthesisTrigger(
        persona_repo=pr,
        event_repo=er,
        provider_getter=lambda: provider,
        synthesis_config=SynthesisConfig(ema_alpha=1.0),
        min_messages=30,
        min_events=1,
        cooldown_hours=0,
        fallback_staleness_hours=0.01,
    )

    assert await trigger.run_fallback() == 1
    assert len(provider.calls) == 1
