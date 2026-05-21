"""Tests for cross-platform account binding (persona groups)."""
from __future__ import annotations

import time

import pytest

from core.config import SynthesisConfig
from core.domain.models import Event, MessageRef, Persona, PersonaGroup
from core.managers.account_link_manager import AccountLinkError, AccountLinkManager
from core.repository.memory import (
    InMemoryEventRepository,
    InMemoryPersonaGroupRepository,
    InMemoryPersonaRepository,
)
from core.repository.sqlite import (
    SQLitePersonaGroupRepository,
    SQLitePersonaRepository,
    db_open,
)
from core.social.persona_group import aggregate_events, expand_uids
from core.tasks.synthesis import PersonaSynthesisTrigger, synthesize_persona_group


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

class _MockResponse:
    def __init__(self, text: str) -> None:
        self.completion_text = text


class _MockProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def text_chat(self, prompt: str = "", system_prompt: str = "") -> _MockResponse:
        self.calls.append(prompt)
        return _MockResponse('{"description":"merged","big_five":{"O":0.6}}')


def _persona(uid: str, platform: str = "qq", name: str | None = None) -> Persona:
    return Persona(
        uid=uid,
        bound_identities=[(platform, uid)],
        primary_name=name or uid,
        persona_attrs={},
        confidence=0.5,
        created_at=1.0,
        last_active_at=5000.0,
    )


def _event(event_id: str, uid: str, messages: int = 2, end_time: float = 1000.0) -> Event:
    return Event(
        event_id=event_id,
        group_id="g1",
        start_time=end_time - 10,
        end_time=end_time,
        participants=[uid],
        interaction_flow=[
            MessageRef(sender_uid=uid, timestamp=end_time + i, content_hash="", content_preview="hi")
            for i in range(messages)
        ],
        topic="topic",
        summary="summary",
        chat_content_tags=["tag"],
        salience=0.5,
        confidence=0.8,
        last_accessed_at=end_time,
    )


async def _make_manager() -> tuple:
    pr = InMemoryPersonaRepository()
    gr = InMemoryPersonaGroupRepository(pr)
    er = InMemoryEventRepository()
    for uid, plat in (("u1", "qq"), ("u2", "discord"), ("u3", "qq")):
        await pr.upsert(_persona(uid, plat))
    mgr = AccountLinkManager(
        persona_repo=pr,
        group_repo=gr,
        event_repo=er,
        provider_getter=lambda: None,  # synthesis no-ops in these tests
        synthesis_config=SynthesisConfig(),
    )
    return pr, gr, er, mgr


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sqlite_persona_group_repo_roundtrip(tmp_path) -> None:
    async with db_open(tmp_path / "t.db", migration_auto_backup=False) as db:
        pr = SQLitePersonaRepository(db)
        gr = SQLitePersonaGroupRepository(db)
        now = time.time()
        for uid in ("a", "b"):
            await pr.upsert(_persona(uid))
        await gr.upsert_group(PersonaGroup("g", "Alice", "a", now, now))
        await gr.set_member_group("a", "g")
        await gr.set_member_group("b", "g")

        assert sorted(await gr.list_member_uids("g")) == ["a", "b"]
        assert (await pr.get("a")).group_id == "g"
        assert (await gr.get_group("g")).display_name == "Alice"

        assert await gr.delete_group("g") is True
        assert await gr.get_group("g") is None
        assert (await pr.get("a")).group_id is None  # membership cleared


# ---------------------------------------------------------------------------
# AccountLinkManager
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bind_creates_group_and_extends() -> None:
    pr, gr, er, mgr = await _make_manager()

    group = await mgr.bind_accounts(["u1", "u2"], "Alice")
    assert group.display_name == "Alice"
    assert sorted(await gr.list_member_uids(group.group_id)) == ["u1", "u2"]

    # binding u3 with an already-grouped uid extends the same group
    group2 = await mgr.bind_accounts(["u1", "u3"])
    assert group2.group_id == group.group_id
    assert sorted(await gr.list_member_uids(group.group_id)) == ["u1", "u2", "u3"]


@pytest.mark.asyncio
async def test_bind_rejects_too_few_and_bot_personas() -> None:
    pr, gr, er, mgr = await _make_manager()
    with pytest.raises(AccountLinkError):
        await mgr.bind_accounts(["u1"])

    await pr.upsert(
        Persona(
            uid="bot", bound_identities=[("internal", "bot")], primary_name="Bot",
            persona_attrs={}, confidence=0.5, created_at=1.0, last_active_at=1.0,
        )
    )
    with pytest.raises(AccountLinkError):
        await mgr.bind_accounts(["u1", "bot"])


@pytest.mark.asyncio
async def test_unbind_dissolves_group_when_one_member_left() -> None:
    pr, gr, er, mgr = await _make_manager()
    group = await mgr.bind_accounts(["u1", "u2"])

    await mgr.unbind("u2")
    # only u1 would remain -> group auto-dissolved
    assert await gr.get_group(group.group_id) is None
    assert (await pr.get("u1")).group_id is None
    assert (await pr.get("u2")).group_id is None


@pytest.mark.asyncio
async def test_unbind_keeps_group_with_remaining_members() -> None:
    pr, gr, er, mgr = await _make_manager()
    group = await mgr.bind_accounts(["u1", "u2", "u3"])

    await mgr.unbind("u3")
    assert sorted(await gr.list_member_uids(group.group_id)) == ["u1", "u2"]
    assert (await pr.get("u3")).group_id is None


@pytest.mark.asyncio
async def test_dissolve_and_rename() -> None:
    pr, gr, er, mgr = await _make_manager()
    group = await mgr.bind_accounts(["u1", "u2"], "Old")

    renamed = await mgr.rename(group.group_id, "New")
    assert renamed.display_name == "New"

    await mgr.dissolve(group.group_id)
    assert await gr.get_group(group.group_id) is None
    assert (await pr.get("u1")).group_id is None


@pytest.mark.asyncio
async def test_pairing_code_flow() -> None:
    pr, gr, er, mgr = await _make_manager()
    code = mgr.generate_pairing_code("u1")
    group = await mgr.redeem_pairing_code(code, "u2")
    assert sorted(await gr.list_member_uids(group.group_id)) == ["u1", "u2"]

    # a code cannot be redeemed twice
    with pytest.raises(AccountLinkError):
        await mgr.redeem_pairing_code(code, "u3")


# ---------------------------------------------------------------------------
# Overlay helpers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_expand_uids_and_aggregate_events() -> None:
    pr, gr, er, mgr = await _make_manager()
    await er.upsert(_event("e1", "u1"))
    await er.upsert(_event("e2", "u2"))
    await mgr.bind_accounts(["u1", "u2"])

    assert sorted(await expand_uids(pr, gr, "u1")) == ["u1", "u2"]
    assert await expand_uids(pr, gr, "u3") == ["u3"]

    merged = await aggregate_events(er, ["u1", "u2"], limit=10)
    assert {e.event_id for e in merged} == {"e1", "e2"}


# ---------------------------------------------------------------------------
# Group-aware synthesis
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_synthesize_persona_group_aggregates_and_mirrors() -> None:
    pr = InMemoryPersonaRepository()
    gr = InMemoryPersonaGroupRepository(pr)
    er = InMemoryEventRepository()
    provider = _MockProvider()
    now = time.time()
    for uid, plat in (("u1", "qq"), ("u2", "discord")):
        await pr.upsert(_persona(uid, plat))
    await er.upsert(_event("e1", "u1", end_time=1000.0))
    await er.upsert(_event("e2", "u2", end_time=2000.0))
    await gr.upsert_group(PersonaGroup("g", "Alice", "u1", now, now))
    await gr.set_member_group("u1", "g")
    await gr.set_member_group("u2", "g")

    ok = await synthesize_persona_group(
        pr, gr, er, lambda: provider, "g",
        synthesis_config=SynthesisConfig(ema_alpha=1.0),
    )
    assert ok is True
    # one LLM call for the whole group, not one per member
    assert len(provider.calls) == 1
    # merged result mirrored to every member
    p1, p2 = await pr.get("u1"), await pr.get("u2")
    assert p1.persona_attrs["description"] == "merged"
    assert p2.persona_attrs["description"] == "merged"
    assert p1.persona_attrs["big_five"] == p2.persona_attrs["big_five"]


@pytest.mark.asyncio
async def test_synthesis_trigger_collapses_group_to_single_call() -> None:
    pr = InMemoryPersonaRepository()
    gr = InMemoryPersonaGroupRepository(pr)
    er = InMemoryEventRepository()
    provider = _MockProvider()
    now = time.time()
    for uid, plat in (("u1", "qq"), ("u2", "discord")):
        await pr.upsert(_persona(uid, plat))
    ev1 = _event("e1", "u1", messages=2, end_time=1000.0)
    ev2 = _event("e2", "u2", messages=2, end_time=2000.0)
    await er.upsert(ev1)
    await er.upsert(ev2)
    await gr.upsert_group(PersonaGroup("g", "Alice", "u1", now, now))
    await gr.set_member_group("u1", "g")
    await gr.set_member_group("u2", "g")

    trigger = PersonaSynthesisTrigger(
        persona_repo=pr,
        event_repo=er,
        provider_getter=lambda: provider,
        synthesis_config=SynthesisConfig(ema_alpha=1.0),
        min_messages=4,  # group total = 2 + 2
        min_events=2,
        cooldown_hours=0,
        group_repo=gr,
    )

    updated = await trigger.handle_events([ev1, ev2])
    assert updated == 1  # collapsed: the group counts once
    assert len(provider.calls) == 1
    p1, p2 = await pr.get("u1"), await pr.get("u2")
    assert p1.persona_attrs["description"] == "merged"
    assert p2.persona_attrs["description"] == "merged"
