"""Tests for memory cleanup and protection."""
import pytest
import asyncio
import time
from core.domain.models import Event, MessageRef, EventStatus, RawStoredMessage
from core.repository.sqlite import SQLiteEventRepository, SQLiteRawMessageRepository, db_open
from core.tasks.cleanup import run_memory_cleanup, run_raw_message_cleanup
from core.config import CleanupConfig

@pytest.fixture
async def event_repo(tmp_path):
    db_path = tmp_path / "test.db"
    async with db_open(db_path) as db:
        repo = SQLiteEventRepository(db)
        yield repo

async def test_memory_cleanup(event_repo):
    # 1. Create 3 events: one high salience, one low salience, one low salience but locked
    e_high = Event(
        event_id="e1", group_id="g1", start_time=100, end_time=200,
        participants=["u1"], interaction_flow=[], topic="High",
        summary="High summary",
        chat_content_tags=[], salience=0.8, confidence=1.0,
        inherit_from=[], last_accessed_at=200, status=EventStatus.ACTIVE,
        is_locked=False
    )
    e_low = Event(
        event_id="e2", group_id="g1", start_time=100, end_time=200,
        participants=["u1"], interaction_flow=[], topic="Low",
        summary="Low summary",
        chat_content_tags=[], salience=0.1, confidence=1.0,
        inherit_from=[], last_accessed_at=200, status=EventStatus.ACTIVE,
        is_locked=False
    )
    e_locked = Event(
        event_id="e3", group_id="g1", start_time=100, end_time=200,
        participants=["u1"], interaction_flow=[], topic="Locked",
        summary="Locked summary",
        chat_content_tags=[], salience=0.1, confidence=1.0,
        inherit_from=[], last_accessed_at=200, status=EventStatus.ACTIVE,
        is_locked=True
    )
    
    await event_repo.upsert(e_high)
    await event_repo.upsert(e_low)
    await event_repo.upsert(e_locked)
    
    # 2. Run cleanup with threshold 0.3 and very long retention to prevent phase-2 hard delete
    cfg = CleanupConfig(enabled=True, threshold=0.3, interval_days=7, retention_days=99999)
    deleted = await run_memory_cleanup(event_repo, cfg)

    # Phase 1 archives 1 event (e_low). Phase 2 does not hard-delete (retention too far in future).
    assert deleted == 1
    
    # 3. Verify: e1 and e3 remain active; e2 is archived (soft-deleted), not hard-deleted
    e1 = await event_repo.get("e1")
    e2 = await event_repo.get("e2")
    e3 = await event_repo.get("e3")
    assert e1 is not None and e1.status == EventStatus.ACTIVE
    assert e2 is not None and e2.status == EventStatus.ARCHIVED
    assert e3 is not None and e3.status == EventStatus.ACTIVE

async def test_cleanup_newly_archived_event_survives_current_cycle(event_repo):
    old_low = Event(
        event_id="old-low", group_id="g1", start_time=100, end_time=200,
        participants=["u1"], interaction_flow=[], topic="Old Low",
        summary="Old low summary",
        chat_content_tags=[], salience=0.1, confidence=1.0,
        inherit_from=[], last_accessed_at=200, status=EventStatus.ACTIVE,
        is_locked=False
    )
    old_archived = Event(
        event_id="old-archived", group_id="g1", start_time=100, end_time=200,
        participants=["u1"], interaction_flow=[], topic="Old Archived",
        summary="Old archived summary",
        chat_content_tags=[], salience=0.1, confidence=1.0,
        inherit_from=[], last_accessed_at=200, status=EventStatus.ARCHIVED,
        is_locked=False
    )
    await event_repo.upsert(old_low)
    await event_repo.upsert(old_archived)

    cfg = CleanupConfig(enabled=True, threshold=0.3, interval_days=7, retention_days=1)
    affected = await run_memory_cleanup(event_repo, cfg)

    assert affected == 2
    assert await event_repo.get("old-archived") is None
    newly_archived = await event_repo.get("old-low")
    assert newly_archived is not None
    assert newly_archived.status == EventStatus.ARCHIVED

async def test_set_locked(event_repo):
    e = Event(
        event_id="e1", group_id="g1", start_time=100, end_time=200,
        participants=["u1"], interaction_flow=[], topic="Test",
        summary="Test summary",
        chat_content_tags=[], salience=0.5, confidence=1.0,
        inherit_from=[], last_accessed_at=200, status=EventStatus.ACTIVE,
        is_locked=False
    )
    await event_repo.upsert(e)
    
    assert (await event_repo.get("e1")).is_locked is False
    
    await event_repo.set_locked("e1", True)
    assert (await event_repo.get("e1")).is_locked is True
    
    await event_repo.set_locked("e1", False)
    assert (await event_repo.get("e1")).is_locked is False


async def test_raw_message_cleanup_deletes_only_expired_raw_messages(tmp_path):
    now = time.time()
    async with db_open(tmp_path / "raw-cleanup.db") as db:
        event_repo = SQLiteEventRepository(db)
        raw_repo = SQLiteRawMessageRepository(db)
        await event_repo.upsert(Event(
            event_id="e1",
            group_id="g1",
            start_time=now - 10,
            end_time=now,
            participants=["u1", "u2"],
            interaction_flow=[],
            topic="Raw cleanup anchor",
            summary="Raw cleanup anchor summary",
            chat_content_tags=[],
            salience=0.8,
            confidence=0.9,
            inherit_from=[],
            last_accessed_at=now,
            status=EventStatus.ACTIVE,
        ))
        await raw_repo.upsert_many([
            RawStoredMessage(
                message_id="old",
                session_id="s",
                group_id="g1",
                platform="test",
                physical_id="u1",
                sender_uid="u1",
                display_name="Alice",
                role="user",
                text="old raw detail",
                content_hash="h-old",
                created_at=now - 3 * 86400.0,
                ingested_at=now - 3 * 86400.0,
            ),
            RawStoredMessage(
                message_id="fresh",
                session_id="s",
                group_id="g1",
                platform="test",
                physical_id="u2",
                sender_uid="u2",
                display_name="Bob",
                role="user",
                text="fresh raw detail",
                content_hash="h-fresh",
                created_at=now,
                ingested_at=now,
            ),
        ])
        await raw_repo.link_event_messages("e1", ["old", "fresh"])

        deleted = await run_raw_message_cleanup(raw_repo, retention_days=1)

        assert deleted == 1
        assert await raw_repo.get("old") is None
        assert await raw_repo.get("fresh") is not None
        assert await event_repo.get("e1") is not None
        linked = await raw_repo.list_by_event("e1")
        assert [message.message_id for message in linked] == ["fresh"]
