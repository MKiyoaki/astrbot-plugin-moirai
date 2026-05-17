"""Tests for group-scoped relation graph: __private__ key mapping and impression scope filtering."""
from __future__ import annotations

import pytest

from core.domain.models import Event, Impression, Persona
from core.repository.memory import (
    InMemoryEventRepository,
    InMemoryImpressionRepository,
    InMemoryPersonaRepository,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_persona(uid: str, name: str = "User") -> Persona:
    return Persona(
        uid=uid,
        bound_identities=[("qq", uid)],
        primary_name=name,
        persona_attrs={},
        confidence=0.8,
        created_at=1000.0,
        last_active_at=2000.0,
    )


def make_event(event_id: str, group_id: str | None, participants: list[str]) -> Event:
    return Event(
        event_id=event_id,
        group_id=group_id,
        start_time=1_700_000_000.0,
        end_time=1_700_001_000.0,
        participants=participants,
        interaction_flow=[],
        topic="test",
        summary="test summary",
        chat_content_tags=[],
        salience=0.6,
        confidence=0.8,
        inherit_from=[],
        last_accessed_at=1_700_001_000.0,
    )


def make_impression(observer: str, subject: str, scope: str) -> Impression:
    return Impression(
        observer_uid=observer,
        subject_uid=subject,
        scope=scope,
        ipc_orientation="friend",
        benevolence=0.5,
        power=0.0,
        affect_intensity=0.5,
        r_squared=0.8,
        confidence=0.7,
        evidence_event_ids=[],
        last_reinforced_at=1000.0,
    )


# ---------------------------------------------------------------------------
# Tests: plugin_routes graph_data() __private__ key mapping
# ---------------------------------------------------------------------------

class TestGraphDataPrivateKey:
    """Verify that events with group_id=None produce '__private__' key in group_members."""

    @pytest.mark.asyncio
    async def test_private_chat_events_produce_private_key(self, tmp_path):
        from web.plugin_routes import PluginRoutes
        from core.repository.memory import InMemoryPersonaRepository, InMemoryEventRepository, InMemoryImpressionRepository

        persona_repo = InMemoryPersonaRepository()
        event_repo = InMemoryEventRepository()
        impression_repo = InMemoryImpressionRepository()

        await persona_repo.upsert(make_persona("u1", "Alice"))
        await persona_repo.upsert(make_persona("u2", "Bob"))

        # Private chat event (group_id=None)
        await event_repo.upsert(make_event("e1", None, ["u1", "u2"]))

        routes = PluginRoutes(
            persona_repo=persona_repo,
            event_repo=event_repo,
            impression_repo=impression_repo,
            data_dir=tmp_path,
        )
        data = await routes.graph_data()

        group_members = data["group_members"]
        # None group_id must be mapped to "__private__", not "null" or None
        assert "__private__" in group_members
        assert None not in group_members
        assert "null" not in group_members
        assert "u1" in group_members["__private__"]
        assert "u2" in group_members["__private__"]

    @pytest.mark.asyncio
    async def test_group_chat_events_use_group_id_as_key(self, tmp_path):
        from web.plugin_routes import PluginRoutes

        persona_repo = InMemoryPersonaRepository()
        event_repo = InMemoryEventRepository()
        impression_repo = InMemoryImpressionRepository()

        await persona_repo.upsert(make_persona("u1"))
        await persona_repo.upsert(make_persona("u2"))
        await event_repo.upsert(make_event("e1", "group_abc", ["u1", "u2"]))

        routes = PluginRoutes(
            persona_repo=persona_repo,
            event_repo=event_repo,
            impression_repo=impression_repo,
            data_dir=tmp_path,
        )
        data = await routes.graph_data()
        group_members = data["group_members"]

        assert "group_abc" in group_members
        assert "__private__" not in group_members

    @pytest.mark.asyncio
    async def test_mixed_private_and_group_both_appear(self, tmp_path):
        from web.plugin_routes import PluginRoutes

        persona_repo = InMemoryPersonaRepository()
        event_repo = InMemoryEventRepository()
        impression_repo = InMemoryImpressionRepository()

        await persona_repo.upsert(make_persona("u1"))
        await persona_repo.upsert(make_persona("u2"))
        await persona_repo.upsert(make_persona("u3"))

        await event_repo.upsert(make_event("e1", None, ["u1", "u2"]))        # private
        await event_repo.upsert(make_event("e2", "grp1", ["u2", "u3"]))      # group

        routes = PluginRoutes(
            persona_repo=persona_repo,
            event_repo=event_repo,
            impression_repo=impression_repo,
            data_dir=tmp_path,
        )
        data = await routes.graph_data()
        gm = data["group_members"]

        assert "__private__" in gm
        assert "grp1" in gm
        assert set(gm["__private__"]) == {"u1", "u2"}
        assert set(gm["grp1"]) == {"u2", "u3"}



# ---------------------------------------------------------------------------
# Tests: graph_data() impression scope in edges
# ---------------------------------------------------------------------------

class TestGraphDataEdgeScope:
    """Verify that edges in graph_data() carry the correct scope field."""

    @pytest.mark.asyncio
    async def test_group_impression_scope_matches_group_id(self, tmp_path):
        from web.plugin_routes import PluginRoutes

        persona_repo = InMemoryPersonaRepository()
        event_repo = InMemoryEventRepository()
        impression_repo = InMemoryImpressionRepository()

        await persona_repo.upsert(make_persona("u1"))
        await persona_repo.upsert(make_persona("u2"))
        await event_repo.upsert(make_event("e1", "grp1", ["u1", "u2"]))
        await impression_repo.upsert(make_impression("u1", "u2", "grp1"))

        routes = PluginRoutes(
            persona_repo=persona_repo,
            event_repo=event_repo,
            impression_repo=impression_repo,
            data_dir=tmp_path,
        )
        data = await routes.graph_data()
        edges = data["edges"]
        assert len(edges) == 1
        assert edges[0]["data"]["scope"] == "grp1"

    @pytest.mark.asyncio
    async def test_private_impression_scope_is_global(self, tmp_path):
        from web.plugin_routes import PluginRoutes

        persona_repo = InMemoryPersonaRepository()
        event_repo = InMemoryEventRepository()
        impression_repo = InMemoryImpressionRepository()

        await persona_repo.upsert(make_persona("u1"))
        await persona_repo.upsert(make_persona("u2"))
        await event_repo.upsert(make_event("e1", None, ["u1", "u2"]))
        # Private chat → scope="global" (set by extractor: event.group_id or "global")
        await impression_repo.upsert(make_impression("u1", "u2", "global"))

        routes = PluginRoutes(
            persona_repo=persona_repo,
            event_repo=event_repo,
            impression_repo=impression_repo,
            data_dir=tmp_path,
        )
        data = await routes.graph_data()
        edges = data["edges"]
        assert len(edges) == 1
        assert edges[0]["data"]["scope"] == "global"
