"""Integration tests for the in-memory repository implementations.

These same tests must also pass against the SQLite implementation (Phase 2),
verifying interface-swap compatibility.
"""

import math

import pytest

from core.domain.models import Event, Impression, MessageRef, Persona
from core.repository.memory import (
    InMemoryEventRepository,
    InMemoryImpressionRepository,
    InMemoryPersonaRepository,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOW = 2_000_000.0


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
        ipc_orientation="友好",
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


@pytest.mark.asyncio
async def test_persona_get_missing_returns_none() -> None:
    repo = InMemoryPersonaRepository()
    assert await repo.get("nonexistent") is None


@pytest.mark.asyncio
async def test_persona_upsert_and_get() -> None:
    repo = InMemoryPersonaRepository()
    p = make_persona()
    await repo.upsert(p)
    result = await repo.get(p.uid)
    assert result is not None
    assert result.uid == p.uid
    assert result.primary_name == p.primary_name


@pytest.mark.asyncio
async def test_persona_get_returns_copy() -> None:
    repo = InMemoryPersonaRepository()
    p = make_persona()
    await repo.upsert(p)
    r1 = await repo.get(p.uid)
    r1.primary_name = "Mutated"  # type: ignore[union-attr]
    r2 = await repo.get(p.uid)
    assert r2.primary_name == "Alice"  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_persona_get_by_identity() -> None:
    repo = InMemoryPersonaRepository()
    p = make_persona(bound_identities=[("qq", "99999"), ("telegram", "t-1")])
    await repo.upsert(p)
    result = await repo.get_by_identity("qq", "99999")
    assert result is not None and result.uid == p.uid
    result2 = await repo.get_by_identity("telegram", "t-1")
    assert result2 is not None and result2.uid == p.uid


@pytest.mark.asyncio
async def test_persona_get_by_identity_missing() -> None:
    repo = InMemoryPersonaRepository()
    assert await repo.get_by_identity("qq", "unknown") is None


@pytest.mark.asyncio
async def test_persona_upsert_updates_bindings() -> None:
    repo = InMemoryPersonaRepository()
    p_v1 = make_persona(bound_identities=[("qq", "old-id")])
    await repo.upsert(p_v1)

    # Re-upsert with new bound identity, old binding removed
    p_v2 = make_persona(bound_identities=[("qq", "new-id")])
    await repo.upsert(p_v2)

    assert await repo.get_by_identity("qq", "old-id") is None
    assert await repo.get_by_identity("qq", "new-id") is not None


@pytest.mark.asyncio
async def test_persona_delete() -> None:
    repo = InMemoryPersonaRepository()
    p = make_persona(bound_identities=[("qq", "del-id")])
    await repo.upsert(p)
    assert await repo.delete(p.uid) is True
    assert await repo.get(p.uid) is None
    assert await repo.get_by_identity("qq", "del-id") is None


@pytest.mark.asyncio
async def test_persona_delete_missing_returns_false() -> None:
    repo = InMemoryPersonaRepository()
    assert await repo.delete("ghost") is False


@pytest.mark.asyncio
async def test_persona_bind_identity() -> None:
    repo = InMemoryPersonaRepository()
    p = make_persona(bound_identities=[])
    await repo.upsert(p)
    await repo.bind_identity(p.uid, "wechat", "wx-abc")
    result = await repo.get_by_identity("wechat", "wx-abc")
    assert result is not None and result.uid == p.uid


@pytest.mark.asyncio
async def test_persona_list_all() -> None:
    repo = InMemoryPersonaRepository()
    for i in range(3):
        await repo.upsert(make_persona(uid=f"uid-{i}", name=f"User{i}"))
    all_personas = await repo.list_all()
    assert len(all_personas) == 3


# ===========================================================================
# EventRepository
# ===========================================================================


@pytest.mark.asyncio
async def test_event_get_missing_returns_none() -> None:
    repo = InMemoryEventRepository()
    assert await repo.get("missing") is None


@pytest.mark.asyncio
async def test_event_upsert_and_get() -> None:
    repo = InMemoryEventRepository()
    e = make_event()
    await repo.upsert(e)
    result = await repo.get(e.event_id)
    assert result is not None
    assert result.event_id == e.event_id
    assert result.topic == e.topic


@pytest.mark.asyncio
async def test_event_get_returns_copy() -> None:
    repo = InMemoryEventRepository()
    e = make_event()
    await repo.upsert(e)
    r1 = await repo.get(e.event_id)
    r1.salience = 0.0  # type: ignore[union-attr]
    r2 = await repo.get(e.event_id)
    assert r2.salience == 0.7  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_event_list_by_group() -> None:
    repo = InMemoryEventRepository()
    await repo.upsert(make_event("e1", group_id="grp-1", start_offset=0))
    await repo.upsert(make_event("e2", group_id="grp-1", start_offset=100))
    await repo.upsert(make_event("e3", group_id="grp-2", start_offset=200))

    grp1 = await repo.list_by_group("grp-1")
    assert {e.event_id for e in grp1} == {"e1", "e2"}
    # Most recent first
    assert grp1[0].event_id == "e2"


@pytest.mark.asyncio
async def test_event_list_by_group_private_chat() -> None:
    repo = InMemoryEventRepository()
    await repo.upsert(make_event("private", group_id=None))
    await repo.upsert(make_event("group", group_id="grp-X"))

    private = await repo.list_by_group(None)
    assert len(private) == 1 and private[0].event_id == "private"


@pytest.mark.asyncio
async def test_event_list_by_participant() -> None:
    repo = InMemoryEventRepository()
    await repo.upsert(make_event("e1", participants=["uid-a", "uid-b"]))
    await repo.upsert(make_event("e2", participants=["uid-b", "uid-c"]))
    await repo.upsert(make_event("e3", participants=["uid-c"]))

    results = await repo.list_by_participant("uid-b")
    assert {e.event_id for e in results} == {"e1", "e2"}


@pytest.mark.asyncio
async def test_event_search_fts_topic() -> None:
    repo = InMemoryEventRepository()
    await repo.upsert(make_event("e1", topic="项目规划"))
    await repo.upsert(make_event("e2", topic="周末活动"))

    results = await repo.search_fts("项目")
    assert len(results) == 1
    assert results[0].event_id == "e1"


@pytest.mark.asyncio
async def test_event_search_fts_tags() -> None:
    repo = InMemoryEventRepository()
    await repo.upsert(make_event("e1", tags=["工作", "产品"]))
    await repo.upsert(make_event("e2", tags=["家庭", "旅行"]))

    results = await repo.search_fts("产品")
    assert len(results) == 1 and results[0].event_id == "e1"


@pytest.mark.asyncio
async def test_event_search_fts_no_match() -> None:
    repo = InMemoryEventRepository()
    await repo.upsert(make_event("e1", topic="工作"))
    assert await repo.search_fts("完全不匹配的关键词") == []


@pytest.mark.asyncio
async def test_event_search_vector_returns_empty_stub() -> None:
    repo = InMemoryEventRepository()
    await repo.upsert(make_event())
    # In-memory stub: always returns []
    assert await repo.search_vector([0.1, 0.2, 0.3]) == []


@pytest.mark.asyncio
async def test_event_get_children() -> None:
    repo = InMemoryEventRepository()
    parent = make_event("parent")
    child1 = make_event("child1", inherit_from=["parent"])
    child2 = make_event("child2", inherit_from=["parent", "other"])
    unrelated = make_event("unrelated", inherit_from=["other"])

    for e in [parent, child1, child2, unrelated]:
        await repo.upsert(e)

    children = await repo.get_children("parent")
    assert {e.event_id for e in children} == {"child1", "child2"}


@pytest.mark.asyncio
async def test_event_update_salience() -> None:
    repo = InMemoryEventRepository()
    await repo.upsert(make_event("e1", salience=0.9))

    assert await repo.update_salience("e1", 0.3) is True
    result = await repo.get("e1")
    assert result.salience == pytest.approx(0.3)  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_event_update_salience_missing() -> None:
    repo = InMemoryEventRepository()
    assert await repo.update_salience("ghost", 0.5) is False


@pytest.mark.asyncio
async def test_event_update_last_accessed() -> None:
    repo = InMemoryEventRepository()
    await repo.upsert(make_event("e1"))
    new_ts = NOW + 9999
    assert await repo.update_last_accessed("e1", new_ts) is True
    result = await repo.get("e1")
    assert result.last_accessed_at == new_ts  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_event_decay_all_salience() -> None:
    repo = InMemoryEventRepository()
    await repo.upsert(make_event("e1", salience=1.0))
    await repo.upsert(make_event("e2", salience=0.5))

    lambda_ = 0.01
    count = await repo.decay_all_salience(lambda_)
    assert count == 2

    expected_factor = math.exp(-lambda_)
    r1 = await repo.get("e1")
    r2 = await repo.get("e2")
    assert r1.salience == pytest.approx(1.0 * expected_factor)  # type: ignore[union-attr]
    assert r2.salience == pytest.approx(0.5 * expected_factor)  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_event_decay_keeps_salience_nonnegative() -> None:
    repo = InMemoryEventRepository()
    await repo.upsert(make_event("e1", salience=1e-300))
    await repo.decay_all_salience(lambda_=1000.0)
    result = await repo.get("e1")
    assert result.salience >= 0.0  # type: ignore[union-attr]


# ===========================================================================
# ImpressionRepository
# ===========================================================================


@pytest.mark.asyncio
async def test_impression_get_missing_returns_none() -> None:
    repo = InMemoryImpressionRepository()
    assert await repo.get("obs", "subj", "global") is None


@pytest.mark.asyncio
async def test_impression_upsert_and_get() -> None:
    repo = InMemoryImpressionRepository()
    imp = make_impression()
    await repo.upsert(imp)
    result = await repo.get(imp.observer_uid, imp.subject_uid, imp.scope)
    assert result is not None
    assert result.benevolence == imp.benevolence


@pytest.mark.asyncio
async def test_impression_upsert_overwrites() -> None:
    repo = InMemoryImpressionRepository()
    imp_v1 = make_impression(affect=0.3)
    await repo.upsert(imp_v1)
    imp_v2 = make_impression(affect=0.9)  # same key, updated affect
    await repo.upsert(imp_v2)

    result = await repo.get(imp_v1.observer_uid, imp_v1.subject_uid, imp_v1.scope)
    assert result is not None and result.benevolence == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_impression_directional_asymmetry() -> None:
    repo = InMemoryImpressionRepository()
    fwd = make_impression(observer="uid-a", subject="uid-b", affect=0.8)
    rev = make_impression(observer="uid-b", subject="uid-a", affect=-0.2)
    await repo.upsert(fwd)
    await repo.upsert(rev)

    r_fwd = await repo.get("uid-a", "uid-b", "global")
    r_rev = await repo.get("uid-b", "uid-a", "global")
    assert r_fwd.benevolence == pytest.approx(0.8)   # type: ignore[union-attr]
    assert r_rev.benevolence == pytest.approx(-0.2)  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_impression_list_by_observer() -> None:
    repo = InMemoryImpressionRepository()
    await repo.upsert(make_impression(observer="bot", subject="alice", scope="global"))
    await repo.upsert(make_impression(observer="bot", subject="bob", scope="global"))
    await repo.upsert(make_impression(observer="alice", subject="bot", scope="global"))

    bot_imps = await repo.list_by_observer("bot")
    assert len(bot_imps) == 2
    subjects = {i.subject_uid for i in bot_imps}
    assert subjects == {"alice", "bob"}


@pytest.mark.asyncio
async def test_impression_list_by_observer_filter_scope() -> None:
    repo = InMemoryImpressionRepository()
    await repo.upsert(make_impression(observer="bot", subject="alice", scope="global"))
    await repo.upsert(make_impression(observer="bot", subject="alice", scope="grp-1"))

    global_only = await repo.list_by_observer("bot", scope="global")
    assert len(global_only) == 1 and global_only[0].scope == "global"


@pytest.mark.asyncio
async def test_impression_list_by_subject() -> None:
    repo = InMemoryImpressionRepository()
    await repo.upsert(make_impression(observer="bot", subject="alice"))
    await repo.upsert(make_impression(observer="bob", subject="alice"))
    await repo.upsert(make_impression(observer="bot", subject="bob"))

    alice_imps = await repo.list_by_subject("alice")
    assert len(alice_imps) == 2
    observers = {i.observer_uid for i in alice_imps}
    assert observers == {"bot", "bob"}


@pytest.mark.asyncio
async def test_impression_delete() -> None:
    repo = InMemoryImpressionRepository()
    imp = make_impression()
    await repo.upsert(imp)
    assert await repo.delete(imp.observer_uid, imp.subject_uid, imp.scope) is True
    assert await repo.get(imp.observer_uid, imp.subject_uid, imp.scope) is None


@pytest.mark.asyncio
async def test_impression_delete_missing_returns_false() -> None:
    repo = InMemoryImpressionRepository()
    assert await repo.delete("ghost", "shadow", "global") is False


@pytest.mark.asyncio
async def test_impression_scope_isolation() -> None:
    """global impression and group impression are independent records."""
    repo = InMemoryImpressionRepository()
    g = make_impression(scope="global", affect=0.5)
    grp = make_impression(scope="grp-1", affect=-0.3)
    await repo.upsert(g)
    await repo.upsert(grp)

    r_global = await repo.get("uid-bot", "uid-a", "global")
    r_grp = await repo.get("uid-bot", "uid-a", "grp-1")
    assert r_global.benevolence == pytest.approx(0.5)   # type: ignore[union-attr]
    assert r_grp.benevolence == pytest.approx(-0.3)     # type: ignore[union-attr]
