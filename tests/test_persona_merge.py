"""Tests for Phase 4 — bot persona merge (src → target).

Covers the SQL-level helper in core.repository.sqlite, exercising:
  * happy path (events / impressions / personas all re-keyed)
  * impression conflict resolution (target wins; src conflicting row dropped)
  * empty / no-op scenarios
  * preview matches the actual merge counts
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from core.domain.models import Event, Impression, Persona
from core.repository.sqlite import (
    SQLiteEventRepository,
    SQLiteImpressionRepository,
    SQLitePersonaRepository,
    db_open,
    merge_bot_persona,
    preview_bot_persona_merge,
)

NOW = 2_000_000.0


@pytest.fixture
async def db(tmp_path: Path):
    async with db_open(tmp_path / "test.db") as conn:
        yield conn


@pytest.fixture
async def repos(db):
    return (
        SQLitePersonaRepository(db),
        SQLiteEventRepository(db),
        SQLiteImpressionRepository(db),
    )


def _event(eid: str, persona_name: str | None) -> Event:
    return Event(
        event_id=eid,
        group_id="g1",
        start_time=NOW,
        end_time=NOW + 60,
        participants=["u1", "u2"],
        interaction_flow=[],
        topic=f"t-{eid}",
        chat_content_tags=[],
        salience=0.5,
        confidence=0.8,
        inherit_from=[],
        last_accessed_at=NOW,
        bot_persona_name=persona_name,
    )


def _impression(obs: str, subj: str, scope: str, persona_name: str | None, b: float = 0.5) -> Impression:
    return Impression(
        observer_uid=obs,
        subject_uid=subj,
        ipc_orientation="友好",
        benevolence=b,
        power=0.0,
        affect_intensity=0.3,
        r_squared=0.5,
        confidence=0.7,
        scope=scope,
        evidence_event_ids=[],
        last_reinforced_at=NOW,
        bot_persona_name=persona_name,
    )


def _persona(uid: str, persona_name: str | None) -> Persona:
    return Persona(
        uid=uid,
        bound_identities=[],
        primary_name=uid,
        persona_attrs={},
        confidence=0.5,
        created_at=NOW,
        last_active_at=NOW,
        bot_persona_name=persona_name,
    )


@pytest.mark.asyncio
async def test_merge_moves_events_no_conflict(db, repos) -> None:
    persona_repo, event_repo, _ = repos
    await event_repo.upsert(_event("e-alice-1", "Alice"))
    await event_repo.upsert(_event("e-alice-2", "Alice"))
    await event_repo.upsert(_event("e-other", "Other"))

    counts = await merge_bot_persona(db, "Alice", "Bob")
    assert counts["events_moved"] == 2
    assert counts["impressions_moved"] == 0
    assert counts["impressions_dropped"] == 0

    all_events = await event_repo.list_all(limit=10)
    alice_rows = [e for e in all_events if e.bot_persona_name == "Alice"]
    bob_rows = [e for e in all_events if e.bot_persona_name == "Bob"]
    other_rows = [e for e in all_events if e.bot_persona_name == "Other"]
    assert alice_rows == []
    assert len(bob_rows) == 2
    assert len(other_rows) == 1


@pytest.mark.asyncio
async def test_merge_target_wins_on_impression_conflict(db, repos) -> None:
    _, _, impression_repo = repos
    # src and target both have an impression for (u1, u2, global). Target wins.
    target_imp = _impression("u1", "u2", "global", "Bob", b=0.9)
    await impression_repo.upsert(target_imp)
    src_imp = _impression("u1", "u2", "global", "Alice", b=0.2)
    await impression_repo.upsert(src_imp)
    # Non-conflicting src impression at a different scope
    await impression_repo.upsert(_impression("u1", "u2", "g-only", "Alice", b=0.4))

    preview = await preview_bot_persona_merge(db, "Alice", "Bob")
    assert preview["impressions_moved"] == 1     # the non-conflicting one
    assert preview["impressions_dropped"] == 1   # the (u1,u2,global) collision

    counts = await merge_bot_persona(db, "Alice", "Bob")
    assert counts == preview

    survivors = await impression_repo.list_by_observer("u1")
    # Target's (u1,u2,global,Bob) row is still there with its original score
    global_bob = [i for i in survivors if i.scope == "global" and i.bot_persona_name == "Bob"]
    assert len(global_bob) == 1
    assert global_bob[0].benevolence == 0.9      # target wins
    # The migrated non-conflict row is now under Bob
    g_only_bob = [i for i in survivors if i.scope == "g-only" and i.bot_persona_name == "Bob"]
    assert len(g_only_bob) == 1
    assert g_only_bob[0].benevolence == 0.4
    # No leftover Alice rows
    assert not any(i.bot_persona_name == "Alice" for i in survivors)


@pytest.mark.asyncio
async def test_merge_rekeys_personas(db, repos) -> None:
    persona_repo, _, _ = repos
    await persona_repo.upsert(_persona("u1", "Alice"))
    await persona_repo.upsert(_persona("u2", "Alice"))
    await persona_repo.upsert(_persona("u3", "Other"))

    counts = await merge_bot_persona(db, "Alice", "Bob")
    assert counts["personas_moved"] == 2

    all_personas = await persona_repo.list_all()
    by_name = {p.uid: p.bot_persona_name for p in all_personas}
    assert by_name["u1"] == "Bob"
    assert by_name["u2"] == "Bob"
    assert by_name["u3"] == "Other"


@pytest.mark.asyncio
async def test_preview_matches_actual_merge(db, repos) -> None:
    _, event_repo, impression_repo = repos
    await event_repo.upsert(_event("e1", "Alice"))
    await event_repo.upsert(_event("e2", "Alice"))
    await impression_repo.upsert(_impression("u1", "u2", "global", "Alice"))
    await impression_repo.upsert(_impression("u3", "u4", "g1", "Alice"))

    preview = await preview_bot_persona_merge(db, "Alice", "Bob")
    actual = await merge_bot_persona(db, "Alice", "Bob")
    assert preview == actual


@pytest.mark.asyncio
async def test_merge_empty_src_is_noop(db, repos) -> None:
    _, event_repo, _ = repos
    await event_repo.upsert(_event("e1", "Alice"))

    counts = await merge_bot_persona(db, "DoesNotExist", "Bob")
    assert counts == {
        "events_moved": 0,
        "impressions_moved": 0,
        "impressions_dropped": 0,
        "personas_moved": 0,
    }
    # Alice's event still belongs to Alice
    all_events = await event_repo.list_all(limit=10)
    assert any(e.bot_persona_name == "Alice" for e in all_events)


@pytest.mark.asyncio
async def test_merge_legacy_null_to_named(db, repos) -> None:
    """Pre-migration NULL rows can be claimed by a named persona."""
    _, event_repo, impression_repo = repos
    await event_repo.upsert(_event("e-null", None))
    await impression_repo.upsert(_impression("u1", "u2", "global", None))

    preview = await preview_bot_persona_merge(db, None, "Bob")
    assert preview["events_moved"] == 1
    assert preview["impressions_moved"] == 1
    counts = await merge_bot_persona(db, None, "Bob")
    assert counts == preview

    all_events = await event_repo.list_all(limit=10)
    assert all_events[0].bot_persona_name == "Bob"
    imps = await impression_repo.list_by_observer("u1")
    assert imps[0].bot_persona_name == "Bob"


@pytest.mark.asyncio
async def test_merge_named_to_legacy_null(db, repos) -> None:
    _, event_repo, impression_repo = repos
    await event_repo.upsert(_event("e-alice", "Alice"))
    await impression_repo.upsert(_impression("u1", "u2", "global", "Alice"))

    counts = await merge_bot_persona(db, "Alice", None)

    assert counts["events_moved"] == 1
    all_events = await event_repo.list_all(limit=10)
    assert all_events[0].bot_persona_name is None
    imps = await impression_repo.list_by_observer("u1")
    assert imps[0].bot_persona_name is None


@pytest.mark.asyncio
async def test_merge_impressions_only_leaves_events_and_personas(db, repos) -> None:
    persona_repo, event_repo, impression_repo = repos
    await persona_repo.upsert(_persona("p1", "Alice"))
    await event_repo.upsert(_event("e-alice", "Alice"))
    await impression_repo.upsert(_impression("u1", "u2", "global", "Alice"))

    counts = await merge_bot_persona(db, "Alice", "Bob", mode="impressions_only")

    assert counts == {
        "events_moved": 0,
        "impressions_moved": 1,
        "impressions_dropped": 0,
        "personas_moved": 0,
    }
    all_events = await event_repo.list_all(limit=10)
    assert all_events[0].bot_persona_name == "Alice"
    all_personas = await persona_repo.list_all()
    assert all_personas[0].bot_persona_name == "Alice"
    imps = await impression_repo.list_by_observer("u1")
    assert imps[0].bot_persona_name == "Bob"
