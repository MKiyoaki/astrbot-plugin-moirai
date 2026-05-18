from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.config import ExtractorConfig
from core.domain.models import Event, MessageRef, Persona
from core.repository.memory import InMemoryEventRepository, InMemoryPersonaRepository
from core.tasks.reextract import ReextractError, reextract_event


class _MockProvider:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0
        self.last_prompt = ""

    async def text_chat(self, prompt: str = "", system_prompt: str = "") -> SimpleNamespace:
        self.calls += 1
        self.last_prompt = prompt
        return SimpleNamespace(completion_text=self.text)


class _MockEncoder:
    dim = 2

    def __init__(self) -> None:
        self.calls = 0

    async def encode(self, text: str) -> list[float]:
        self.calls += 1
        assert "新主题" in text
        return [0.1, 0.2]


def _event(
    event_id: str = "e1",
    *,
    refs: list[MessageRef] | None = None,
    is_locked: bool = False,
) -> Event:
    return Event(
        event_id=event_id,
        group_id="discord:channel-1",
        start_time=1000.0,
        end_time=1010.0,
        participants=["u1", "u2"],
        interaction_flow=refs if refs is not None else [
            MessageRef("u1", 1000.0, "h1", "今天讨论伦敦餐厅"),
            MessageRef("u2", 1005.0, "h2", "我推荐一家英式早餐店"),
        ],
        topic="旧主题",
        summary="旧摘要",
        chat_content_tags=["旧标签"],
        salience=0.3,
        confidence=0.4,
        inherit_from=["parent"],
        last_accessed_at=900.0,
        is_locked=is_locked,
    )


def _json_result(topic: str = "新主题") -> str:
    return (
        '[{"start_idx": 0, "end_idx": 1, '
        f'"topic": "{topic}", "summary": "新摘要", '
        '"chat_content_tags": ["餐厅", "伦敦"], '
        '"salience": 0.8, "confidence": 0.9}]'
    )


@pytest.mark.asyncio
async def test_reextract_event_updates_llm_fields_and_preserves_identity() -> None:
    event_repo = InMemoryEventRepository()
    persona_repo = InMemoryPersonaRepository()
    await event_repo.upsert(_event())
    await persona_repo.upsert(Persona(
        uid="u1",
        bound_identities=[("discord", "1")],
        primary_name="Alice",
        persona_attrs={},
        confidence=0.9,
        created_at=1.0,
        last_active_at=2.0,
    ))
    provider = _MockProvider(_json_result())
    encoder = _MockEncoder()

    result = await reextract_event(
        event_repo,
        persona_repo,
        "e1",
        lambda: provider,
        extractor_config=ExtractorConfig(llm_timeout=1.0),
        encoder=encoder,
    )

    assert result.source_count == 2
    assert result.event.topic == "新主题"
    assert result.event.summary == "新摘要"
    assert result.event.chat_content_tags == ["餐厅", "伦敦"]
    assert result.event.salience == pytest.approx(0.8)
    assert result.event.confidence == pytest.approx(0.9)
    assert result.event.group_id == "discord:channel-1"
    assert result.event.inherit_from == ["parent"]
    assert provider.calls == 1
    assert "Alice" in provider.last_prompt
    assert encoder.calls == 1


@pytest.mark.asyncio
async def test_reextract_event_injects_bot_persona_for_eval_summary() -> None:
    event_repo = InMemoryEventRepository()
    persona_repo = InMemoryPersonaRepository()
    await event_repo.upsert(_event())
    await persona_repo.upsert(Persona(
        uid="bot-uid",
        bound_identities=[("internal", "bot")],
        primary_name="Moirai",
        persona_attrs={"description": "Analytical bot persona"},
        confidence=1.0,
        created_at=1.0,
        last_active_at=1.0,
    ))
    provider = _MockProvider(
        '[{"start_idx": 0, "end_idx": 1, '
        '"topic": "eval topic", '
        '"summary": "[What] Alice asks for food suggestions [Who] Alice [How] Bob gives options [Eval] Useful preference signal", '
        '"chat_content_tags": ["food"], '
        '"salience": 0.7, "confidence": 0.8}]'
    )

    result = await reextract_event(
        event_repo,
        persona_repo,
        "e1",
        lambda: provider,
        extractor_config=ExtractorConfig(llm_timeout=1.0, persona_influenced_summary=True),
    )

    assert "Analytical bot persona" in provider.last_prompt
    assert "[Eval]" in provider.last_prompt
    assert result.event.bot_persona_name == "Moirai"
    assert "[Eval] Useful preference signal" in result.event.summary


@pytest.mark.asyncio
async def test_reextract_event_missing_source_messages_does_not_call_provider() -> None:
    event_repo = InMemoryEventRepository()
    await event_repo.upsert(_event(refs=[]))
    provider = _MockProvider(_json_result())

    with pytest.raises(ReextractError) as exc:
        await reextract_event(event_repo, None, "e1", lambda: provider)

    assert exc.value.code == "missing_source_messages"
    assert provider.calls == 0
    unchanged = await event_repo.get("e1")
    assert unchanged is not None
    assert unchanged.topic == "旧主题"


@pytest.mark.asyncio
async def test_reextract_event_non_text_only_sources_fail_without_fallback() -> None:
    event_repo = InMemoryEventRepository()
    await event_repo.upsert(_event(refs=[
        MessageRef("u1", 1000.0, "h1", "[image]"),
        MessageRef("u2", 1001.0, "h2", "[emoji]"),
    ]))
    provider = _MockProvider(_json_result())

    with pytest.raises(ReextractError) as exc:
        await reextract_event(event_repo, None, "e1", lambda: provider)

    assert exc.value.code == "missing_source_messages"
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_reextract_event_parse_error_leaves_event_unchanged() -> None:
    event_repo = InMemoryEventRepository()
    await event_repo.upsert(_event())
    provider = _MockProvider("not json")

    with pytest.raises(ReextractError) as exc:
        await reextract_event(event_repo, None, "e1", lambda: provider)

    assert exc.value.code == "parse_error"
    unchanged = await event_repo.get("e1")
    assert unchanged is not None
    assert unchanged.topic == "旧主题"
    assert unchanged.summary == "旧摘要"


@pytest.mark.asyncio
async def test_reextract_event_provider_none_leaves_event_unchanged() -> None:
    event_repo = InMemoryEventRepository()
    await event_repo.upsert(_event())

    with pytest.raises(ReextractError) as exc:
        await reextract_event(event_repo, None, "e1", lambda: None)

    assert exc.value.code == "provider_none"
    unchanged = await event_repo.get("e1")
    assert unchanged is not None
    assert unchanged.topic == "旧主题"


@pytest.mark.asyncio
async def test_reextract_event_locked_event_fails() -> None:
    event_repo = InMemoryEventRepository()
    await event_repo.upsert(_event(is_locked=True))
    provider = _MockProvider(_json_result())

    with pytest.raises(ReextractError) as exc:
        await reextract_event(event_repo, None, "e1", lambda: provider)

    assert exc.value.code == "locked"
    assert provider.calls == 0
