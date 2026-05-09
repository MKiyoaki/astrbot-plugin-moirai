"""Tests for memory cleanup and protection."""
import pytest
import asyncio
from core.domain.models import Event, MessageRef, EventStatus
from core.repository.sqlite import SQLiteEventRepository, db_open
from core.tasks.cleanup import run_memory_cleanup
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
    
    # 2. Run cleanup with threshold 0.3
    cfg = CleanupConfig(enabled=True, threshold=0.3, interval_days=7)
    deleted = await run_memory_cleanup(event_repo, cfg)
    
    assert deleted == 1
    
    # 3. Verify: e1 and e3 should remain, e2 should be gone
    assert await event_repo.get("e1") is not None
    assert await event_repo.get("e2") is None
    assert await event_repo.get("e3") is not None

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
