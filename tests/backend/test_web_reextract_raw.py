from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core.domain.models import Event, MessageRef, RawStoredMessage
from core.repository.memory import (
    InMemoryEventRepository,
    InMemoryImpressionRepository,
    InMemoryPersonaRepository,
    InMemoryRawMessageRepository,
)
from web.plugin_routes import PluginRoutes


class _MockProvider:
    def __init__(self) -> None:
        self.last_prompt = ""

    async def text_chat(self, prompt: str = "", system_prompt: str = "") -> SimpleNamespace:
        self.last_prompt = prompt
        return SimpleNamespace(
            completion_text=(
                '[{"start_idx": 0, "end_idx": 1, '
                '"topic": "fresh topic", "summary": "fresh summary", '
                '"chat_content_tags": ["fresh"], "salience": 0.8, "confidence": 0.9}]'
            )
        )


@pytest.mark.asyncio
async def test_plugin_routes_reextract_uses_linked_raw_messages(tmp_path) -> None:
    event_repo = InMemoryEventRepository()
    persona_repo = InMemoryPersonaRepository()
    impression_repo = InMemoryImpressionRepository()
    raw_repo = InMemoryRawMessageRepository()
    provider = _MockProvider()

    await event_repo.upsert(Event(
        event_id="e1",
        group_id="g1",
        start_time=1000.0,
        end_time=1010.0,
        participants=["u1", "u2"],
        interaction_flow=[
            MessageRef("u1", 1000.0, "old-1", "stale preview one", "m1"),
            MessageRef("u2", 1010.0, "old-2", "stale preview two", "m2"),
        ],
        topic="old topic",
        summary="old summary",
        chat_content_tags=[],
        salience=0.4,
        confidence=0.4,
        inherit_from=[],
        last_accessed_at=1010.0,
    ))
    await raw_repo.upsert_many([
        RawStoredMessage(
            message_id="m1",
            session_id="s",
            group_id="g1",
            platform="test",
            physical_id="u1",
            sender_uid="u1",
            display_name="Alice",
            role="user",
            text="fresh raw detail one",
            content_hash="h1",
            created_at=1000.0,
            ingested_at=1000.1,
        ),
        RawStoredMessage(
            message_id="m2",
            session_id="s",
            group_id="g1",
            platform="test",
            physical_id="u2",
            sender_uid="u2",
            display_name="Bob",
            role="user",
            text="fresh raw detail two",
            content_hash="h2",
            created_at=1010.0,
            ingested_at=1010.1,
        ),
    ])
    await raw_repo.link_event_messages("e1", ["m1", "m2"])

    routes = PluginRoutes(
        persona_repo=persona_repo,
        event_repo=event_repo,
        impression_repo=impression_repo,
        data_dir=tmp_path,
        provider_getter=lambda: provider,
        raw_message_repo=raw_repo,
    )
    request = MagicMock()
    request.match_info = {"event_id": "e1"}

    response = await routes._handle_reextract_event(request)
    payload = json.loads(await response.get_data(as_text=True))

    assert response.status_code == 200
    assert payload["source_count"] == 2
    assert "fresh raw detail one" in provider.last_prompt
    assert "fresh raw detail two" in provider.last_prompt
    assert "stale preview one" not in provider.last_prompt
