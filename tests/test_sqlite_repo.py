"""Interface-swap tests for the SQLite repository implementations.

These mirror test_memory_repo.py exactly — if both files pass, the SQLite
and in-memory repositories are guaranteed to satisfy the same contract.

Fixtures provide a fresh temporary database per test.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from core.domain.models import Event, Impression, MessageRef, Persona
from core.repository.sqlite import (
    SQLiteEventRepository,
    SQLiteImpressionRepository,
    SQLitePersonaRepository,
    db_open,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOW = 2_000_000.0


@pytest.fixture
async def db(tmp_path: Path):
    async with db_open(tmp_path / "test.db") as conn:
        yield conn


@pytest.fixture
async def persona_repo(db):
    return SQLitePersonaRepository(db)


@pytest.fixture
async def event_repo(db):
    return SQLiteEventRepository(db)


@pytest.fixture
async def impression_repo(db):
    return SQLiteImpressionRepository(db)


# ---------------------------------------------------------------------------
# Helper constructors (identical to test_memory_repo.py)
# ---------------------------------------------------------------------------

def make_persona(uid: str = "uid-a", name: str = "Alice", **kw) -> Persona:
    return Persona(
        uid=uid,
        bound_identities=kw.pop("bound_identities", [("qq", uid)]),
        primary_name=name,
        persona_attrs={},
        confidence=0.8,
        created_at=NOW,
        last_active_at=NOW,
        **kw,
    )


def make_event(
    event_id: str = "evt-1",
    group_id: str | None = "grp-1",
    salience: float = 0.7,
    topic: str = "工作讨论",
    summary: str = "这是一个关于工作的详细摘要。",
    tags: list[str] | None = None,
    inherit_from: list[str] | None = None,
    start_offset: float = 0.0,
    participants: list[str] | None = None,
) -> Event:
    return Event(
        event_id=event_id,
        group_id=group_id,
        start_time=NOW + start_offset,
        end_time=NOW + start_offset + 600,
        participants=participants or ["uid-a", "uid-bot"],
        interaction_flow=[],
        topic=topic,
        summary=summary,
        chat_content_tags=tags or [],
        salience=salience,
        confidence=0.9,
        inherit_from=inherit_from or [],
        last_accessed_at=NOW + start_offset,
    )


def make_impression(
    observer: str = "uid-bot",
    subject: str = "uid-a",
    affect: float = 0.5,
    scope: str = "global",
    evidence: list[str] | None = None,
) -> Impression:
    return Impression(
        observer_uid=observer,
        subject_uid=subject,
        ipc_orientation="affinity",
        benevolence=affect,
        power=0.0,
        affect_intensity=0.7,
        r_squared=0.9,
        confidence=0.8,
        scope=scope,
        evidence_event_ids=evidence or [],
        last_reinforced_at=NOW,
    )


# ===========================================================================
# PersonaRepository
# ===========================================================================


async def test_persona_get_missing_returns_none(persona_repo) -> None:
    assert await persona_repo.get("nonexistent") is None


async def test_persona_upsert_and_get(persona_repo) -> None:
    p = make_persona()
    await persona_repo.upsert(p)
    result = await persona_repo.get(p.uid)
    assert result is not None
    assert result.uid == p.uid
    assert result.primary_name == p.primary_name


async def test_persona_get_by_identity(persona_repo) -> None:
    p = make_persona(bound_identities=[("qq", "99999"), ("telegram", "t-1")])
    await persona_repo.upsert(p)
    r1 = await persona_repo.get_by_identity("qq", "99999")
    assert r1 is not None and r1.uid == p.uid
    r2 = await persona_repo.get_by_identity("telegram", "t-1")
    assert r2 is not None and r2.uid == p.uid


async def test_persona_get_by_identity_missing(persona_repo) -> None:
    assert await persona_repo.get_by_identity("qq", "unknown") is None


async def test_persona_upsert_updates_bindings(persona_repo) -> None:
    p_v1 = make_persona(bound_identities=[("qq", "old-id")])
    await persona_repo.upsert(p_v1)
    p_v2 = make_persona(bound_identities=[("qq", "new-id")])
    await persona_repo.upsert(p_v2)

    assert await persona_repo.get_by_identity("qq", "old-id") is None
    assert await persona_repo.get_by_identity("qq", "new-id") is not None


async def test_persona_delete(persona_repo) -> None:
    p = make_persona(bound_identities=[("qq", "del-id")])
    await persona_repo.upsert(p)
    assert await persona_repo.delete(p.uid) is True
    assert await persona_repo.get(p.uid) is None
    assert await persona_repo.get_by_identity("qq", "del-id") is None


async def test_persona_delete_missing_returns_false(persona_repo) -> None:
    assert await persona_repo.delete("ghost") is False


async def test_persona_bind_identity(persona_repo) -> None:
    p = make_persona(bound_identities=[])
    await persona_repo.upsert(p)
    await persona_repo.bind_identity(p.uid, "wechat", "wx-abc")
    result = await persona_repo.get_by_identity("wechat", "wx-abc")
    assert result is not None and result.uid == p.uid


async def test_persona_list_all(persona_repo) -> None:
    for i in range(3):
        await persona_repo.upsert(make_persona(uid=f"uid-{i}", name=f"User{i}"))
    all_personas = await persona_repo.list_all()
    assert len(all_personas) == 3


async def test_persona_attrs_roundtrip(persona_repo) -> None:
    p = make_persona()
    p.persona_attrs = {"big_five": {"O": 0.5, "E": 0.3}, "content_tags": ["tech", "music"]}
    await persona_repo.upsert(p)
    result = await persona_repo.get(p.uid)
    assert result.persona_attrs == {"big_five": {"O": 0.5, "E": 0.3}, "content_tags": ["tech", "music"]}


# ===========================================================================
# EventRepository
# ===========================================================================


async def test_event_get_missing_returns_none(event_repo) -> None:
    assert await event_repo.get("missing") is None


async def test_event_upsert_and_get(event_repo) -> None:
    e = make_event()
    await event_repo.upsert(e)
    result = await event_repo.get(e.event_id)
    assert result is not None
    assert result.event_id == e.event_id
    assert result.topic == e.topic


async def test_event_upsert_updates_existing(event_repo) -> None:
    e = make_event(salience=0.9)
    await event_repo.upsert(e)
    e_updated = make_event(salience=0.3)  # same event_id
    await event_repo.upsert(e_updated)
    result = await event_repo.get(e.event_id)
    assert result.salience == pytest.approx(0.3)


async def test_event_list_by_group(event_repo) -> None:
    await event_repo.upsert(make_event("e1", group_id="grp-1", start_offset=0))
    await event_repo.upsert(make_event("e2", group_id="grp-1", start_offset=100))
    await event_repo.upsert(make_event("e3", group_id="grp-2", start_offset=200))

    grp1 = await event_repo.list_by_group("grp-1")
    assert {e.event_id for e in grp1} == {"e1", "e2"}
    assert grp1[0].event_id == "e2"  # most recent first


async def test_event_list_by_group_private_chat(event_repo) -> None:
    await event_repo.upsert(make_event("private", group_id=None))
    await event_repo.upsert(make_event("group", group_id="grp-X"))

    private = await event_repo.list_by_group(None)
    assert len(private) == 1 and private[0].event_id == "private"


async def test_event_list_by_participant(event_repo) -> None:
    await event_repo.upsert(make_event("e1", participants=["uid-a", "uid-b"]))
    await event_repo.upsert(make_event("e2", participants=["uid-b", "uid-c"]))
    await event_repo.upsert(make_event("e3", participants=["uid-c"]))

    results = await event_repo.list_by_participant("uid-b")
    assert {e.event_id for e in results} == {"e1", "e2"}


async def test_event_search_fts_topic(event_repo) -> None:
    # unicode61 tokenizer treats unsegmented CJK runs as single tokens; query
    # must match the full token (no sub-word stemming without a CJK tokenizer).
    await event_repo.upsert(make_event("e1", topic="项目规划"))
    await event_repo.upsert(make_event("e2", topic="周末活动"))

    results = await event_repo.search_fts("项目规划")
    assert len(results) == 1 and results[0].event_id == "e1"


async def test_event_search_fts_tags(event_repo) -> None:
    await event_repo.upsert(make_event("e1", tags=["工作", "产品"]))
    await event_repo.upsert(make_event("e2", tags=["家庭", "旅行"]))

    results = await event_repo.search_fts("产品")
    assert len(results) == 1 and results[0].event_id == "e1"


async def test_event_search_fts_no_match(event_repo) -> None:
    await event_repo.upsert(make_event("e1", topic="工作"))
    assert await event_repo.search_fts("完全不匹配的关键词xyz") == []


async def test_event_search_vector_returns_empty_stub(event_repo) -> None:
    await event_repo.upsert(make_event())
    assert await event_repo.search_vector([0.1, 0.2, 0.3]) == []


async def test_event_get_children(event_repo) -> None:
    await event_repo.upsert(make_event("parent"))
    await event_repo.upsert(make_event("child1", inherit_from=["parent"]))
    await event_repo.upsert(make_event("child2", inherit_from=["parent", "other"]))
    await event_repo.upsert(make_event("unrelated", inherit_from=["other"]))

    children = await event_repo.get_children("parent")
    assert {e.event_id for e in children} == {"child1", "child2"}


async def test_event_update_salience(event_repo) -> None:
    await event_repo.upsert(make_event("e1", salience=0.9))
    assert await event_repo.update_salience("e1", 0.3) is True
    result = await event_repo.get("e1")
    assert result.salience == pytest.approx(0.3)


async def test_event_update_salience_missing(event_repo) -> None:
    assert await event_repo.update_salience("ghost", 0.5) is False


async def test_event_update_last_accessed(event_repo) -> None:
    await event_repo.upsert(make_event("e1"))
    new_ts = NOW + 9999
    assert await event_repo.update_last_accessed("e1", new_ts) is True
    result = await event_repo.get("e1")
    assert result.last_accessed_at == new_ts


async def test_event_decay_all_salience(event_repo) -> None:
    await event_repo.upsert(make_event("e1", salience=1.0))
    await event_repo.upsert(make_event("e2", salience=0.5))

    lambda_ = 0.01
    count = await event_repo.decay_all_salience(lambda_)
    assert count == 2

    factor = math.exp(-lambda_)
    r1 = await event_repo.get("e1")
    r2 = await event_repo.get("e2")
    assert r1.salience == pytest.approx(1.0 * factor)
    assert r2.salience == pytest.approx(0.5 * factor)


async def test_event_decay_keeps_salience_nonnegative(event_repo) -> None:
    await event_repo.upsert(make_event("e1", salience=1e-300))
    await event_repo.decay_all_salience(lambda_=1000.0)
    result = await event_repo.get("e1")
    assert result.salience >= 0.0


async def test_event_interaction_flow_roundtrip(event_repo) -> None:
    refs = [
        MessageRef("uid-a", NOW, "hash1", "hello"),
        MessageRef("uid-bot", NOW + 1, "hash2", "hi there"),
    ]
    e = make_event()
    e.interaction_flow = refs
    await event_repo.upsert(e)
    result = await event_repo.get(e.event_id)
    assert len(result.interaction_flow) == 2
    assert result.interaction_flow[0].sender_uid == "uid-a"
    assert result.interaction_flow[1].content_preview == "hi there"


# ===========================================================================
# ImpressionRepository
# ===========================================================================


async def test_impression_get_missing_returns_none(impression_repo) -> None:
    assert await impression_repo.get("obs", "subj", "global") is None


async def test_impression_upsert_and_get(impression_repo) -> None:
    imp = make_impression()
    await impression_repo.upsert(imp)
    result = await impression_repo.get(imp.observer_uid, imp.subject_uid, imp.scope)
    assert result is not None
    assert result.benevolence == imp.benevolence


async def test_impression_upsert_overwrites(impression_repo) -> None:
    await impression_repo.upsert(make_impression(affect=0.3))
    await impression_repo.upsert(make_impression(affect=0.9))
    result = await impression_repo.get("uid-bot", "uid-a", "global")
    assert result.benevolence == pytest.approx(0.9)


async def test_impression_directional_asymmetry(impression_repo) -> None:
    await impression_repo.upsert(make_impression(observer="uid-a", subject="uid-b", affect=0.8))
    await impression_repo.upsert(make_impression(observer="uid-b", subject="uid-a", affect=-0.2))

    r_fwd = await impression_repo.get("uid-a", "uid-b", "global")
    r_rev = await impression_repo.get("uid-b", "uid-a", "global")
    assert r_fwd.benevolence == pytest.approx(0.8)
    assert r_rev.benevolence == pytest.approx(-0.2)


async def test_impression_list_by_observer(impression_repo) -> None:
    await impression_repo.upsert(make_impression(observer="bot", subject="alice"))
    await impression_repo.upsert(make_impression(observer="bot", subject="bob"))
    await impression_repo.upsert(make_impression(observer="alice", subject="bot"))

    bot_imps = await impression_repo.list_by_observer("bot")
    assert len(bot_imps) == 2
    assert {i.subject_uid for i in bot_imps} == {"alice", "bob"}


async def test_impression_list_by_observer_filter_scope(impression_repo) -> None:
    await impression_repo.upsert(make_impression(observer="bot", subject="alice", scope="global"))
    await impression_repo.upsert(make_impression(observer="bot", subject="alice", scope="grp-1"))

    global_only = await impression_repo.list_by_observer("bot", scope="global")
    assert len(global_only) == 1 and global_only[0].scope == "global"


async def test_impression_list_by_subject(impression_repo) -> None:
    await impression_repo.upsert(make_impression(observer="bot", subject="alice"))
    await impression_repo.upsert(make_impression(observer="bob", subject="alice"))
    await impression_repo.upsert(make_impression(observer="bot", subject="bob"))

    alice_imps = await impression_repo.list_by_subject("alice")
    assert len(alice_imps) == 2
    assert {i.observer_uid for i in alice_imps} == {"bot", "bob"}


async def test_impression_delete(impression_repo) -> None:
    imp = make_impression()
    await impression_repo.upsert(imp)
    assert await impression_repo.delete(imp.observer_uid, imp.subject_uid, imp.scope) is True
    assert await impression_repo.get(imp.observer_uid, imp.subject_uid, imp.scope) is None


async def test_impression_delete_missing_returns_false(impression_repo) -> None:
    assert await impression_repo.delete("ghost", "shadow", "global") is False


async def test_impression_scope_isolation(impression_repo) -> None:
    await impression_repo.upsert(make_impression(scope="global", affect=0.5))
    await impression_repo.upsert(make_impression(scope="grp-1", affect=-0.3))

    r_global = await impression_repo.get("uid-bot", "uid-a", "global")
    r_grp = await impression_repo.get("uid-bot", "uid-a", "grp-1")
    assert r_global.benevolence == pytest.approx(0.5)
    assert r_grp.benevolence == pytest.approx(-0.3)


# ===========================================================================
# Migration runner
# ===========================================================================


async def test_migrations_are_idempotent(tmp_path: Path) -> None:
    """Running migrations twice on the same DB must not raise."""
    async with db_open(tmp_path / "idem.db") as db:
        pass  # First run
    async with db_open(tmp_path / "idem.db") as db:
        pass  # Second run — should be idempotent


async def test_migrations_tracking_table_exists(tmp_path: Path) -> None:
    async with db_open(tmp_path / "track.db") as db:
        async with db.execute(
            "SELECT name FROM _migrations ORDER BY name"
        ) as cur:
            rows = await cur.fetchall()
        names = [r[0] for r in rows]
    assert "001_initial_schema.sql" in names


import pytest  # noqa: E402 (already imported above, harmless duplicate)
