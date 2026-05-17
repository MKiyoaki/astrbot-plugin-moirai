"""Regression tests for the SQLite transaction serialization fix.

Before the fix, concurrent coroutines writing through the shared aiosqlite
connection raced each other at `BEGIN IMMEDIATE` and one of them hit
"cannot start a transaction within a transaction". These tests reproduce
the concurrent shape and assert that the lock-based serialization in
`core/repository/sqlite.py` keeps every writer alive.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from core.domain.models import Event, Persona
from core.repository.sqlite import (
    SQLiteEventRepository,
    SQLitePersonaRepository,
    db_open,
)


@pytest.fixture
async def db(tmp_path: Path):
    async with db_open(tmp_path / "concurrency.db") as conn:
        yield conn


@pytest.fixture
async def persona_repo(db):
    return SQLitePersonaRepository(db)


@pytest.fixture
async def event_repo(db):
    return SQLiteEventRepository(db)


def _make_persona(idx: int) -> Persona:
    return Persona(
        uid=f"uid-{idx:04d}",
        bound_identities=[("qq", f"phys-{idx}")],
        primary_name=f"User{idx}",
        persona_attrs={},
        confidence=0.5,
        created_at=1000.0 + idx,
        last_active_at=1000.0 + idx,
    )


def _make_event(idx: int) -> Event:
    return Event(
        event_id=f"event-{idx:04d}",
        group_id="g1",
        start_time=1000.0 + idx,
        end_time=1000.0 + idx + 10,
        participants=[f"uid-{idx:04d}"],
        interaction_flow=[],
        topic=f"topic-{idx}",
        summary="",
        chat_content_tags=[],
        salience=0.5,
        confidence=0.5,
        inherit_from=[],
        last_accessed_at=1000.0 + idx + 10,
    )


async def test_concurrent_persona_upserts_dont_nest_transactions(persona_repo):
    """50 coroutines upserting distinct personas concurrently must all succeed.

    Before the fix this would raise OperationalError on whichever upsert hit
    BEGIN IMMEDIATE while another transaction was still open on the shared
    connection.
    """
    await asyncio.gather(*(persona_repo.upsert(_make_persona(i)) for i in range(50)))

    rows = await persona_repo.list_all()
    assert len(rows) == 50
    assert {r.uid for r in rows} == {f"uid-{i:04d}" for i in range(50)}


async def test_concurrent_persona_and_event_upserts(persona_repo, event_repo):
    """Cross-repo concurrency (Persona + Event sharing the same connection)."""
    persona_tasks = [persona_repo.upsert(_make_persona(i)) for i in range(10)]
    event_tasks = [event_repo.upsert(_make_event(i)) for i in range(10)]

    await asyncio.gather(*persona_tasks, *event_tasks)

    assert len(await persona_repo.list_all()) == 10
    assert len(await event_repo.list_by_group("g1")) == 10


async def test_rollback_does_not_break_subsequent_transactions(persona_repo, db):
    """If one upsert fails mid-transaction, the lock releases cleanly and the
    next upsert must succeed (no leaked open transaction)."""
    original_execute = db.execute
    call_count = {"n": 0}

    async def flaky_execute(sql, *args, **kwargs):
        call_count["n"] += 1
        # On the third call (mid-upsert), simulate a failure
        if call_count["n"] == 3:
            raise RuntimeError("simulated DML failure")
        return await original_execute(sql, *args, **kwargs)

    db.execute = flaky_execute
    try:
        with pytest.raises(RuntimeError, match="simulated DML failure"):
            await persona_repo.upsert(_make_persona(1))
    finally:
        db.execute = original_execute

    # Lock must have been released and connection rolled back — next upsert succeeds
    await persona_repo.upsert(_make_persona(2))
    rows = await persona_repo.list_all()
    assert {r.uid for r in rows} == {"uid-0002"}
