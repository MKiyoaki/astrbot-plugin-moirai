import pytest
import math
import time
from pathlib import Path
from core.domain.models import Event, Impression, Persona, EventStatus, MessageRef
from core.repository.sqlite import (
    SQLiteEventRepository,
    SQLiteImpressionRepository,
    SQLitePersonaRepository,
    db_open,
)

NOW = 2_000_000.0

@pytest.fixture
async def db(tmp_path: Path):
    async with db_open(tmp_path / "test_extra.db") as conn:
        yield conn

@pytest.fixture
async def event_repo(db):
    return SQLiteEventRepository(db)

@pytest.fixture
async def persona_repo(db):
    return SQLitePersonaRepository(db)

@pytest.fixture
async def impression_repo(db):
    return SQLiteImpressionRepository(db)

def make_event(event_id, group_id="g1", status=EventStatus.ACTIVE, salience=0.5, is_locked=False, chat_content_tags=None):
    return Event(
        event_id=event_id,
        group_id=group_id,
        start_time=NOW,
        end_time=NOW + 100,
        participants=["u1", "u2"],
        interaction_flow=[MessageRef("u1", NOW, "h", "p")],
        topic="topic",
        summary="summary",
        status=status,
        salience=salience,
        is_locked=is_locked,
        chat_content_tags=chat_content_tags or []
    )

@pytest.mark.asyncio
async def test_event_status_and_locking(event_repo):
    await event_repo.upsert(make_event("e1", status=EventStatus.ACTIVE))
    
    # Test count_by_status
    assert await event_repo.count_by_status(EventStatus.ACTIVE) == 1
    assert await event_repo.count_by_status(EventStatus.ARCHIVED) == 0
    
    # Test set_status
    await event_repo.set_status("e1", EventStatus.ARCHIVED)
    assert await event_repo.count_by_status(EventStatus.ACTIVE) == 0
    assert await event_repo.count_by_status(EventStatus.ARCHIVED) == 1
    
    # Test list_by_status
    archived = await event_repo.list_by_status(EventStatus.ARCHIVED)
    assert len(archived) == 1
    assert archived[0].event_id == "e1"
    
    # Test set_locked
    await event_repo.set_locked("e1", True)
    ev = await event_repo.get("e1")
    assert ev.is_locked is True

@pytest.mark.asyncio
async def test_event_cleanup_tasks(event_repo):
    await event_repo.upsert(make_event("active_low", salience=0.1, status=EventStatus.ACTIVE))
    await event_repo.upsert(make_event("active_high", salience=0.9, status=EventStatus.ACTIVE))
    await event_repo.upsert(make_event("locked_low", salience=0.1, status=EventStatus.ACTIVE, is_locked=True))
    
    # 1. archive_low_salience_events
    count = await event_repo.archive_low_salience_events(threshold=0.3)
    assert count == 1 # only active_low
    assert (await event_repo.get("active_low")).status == EventStatus.ARCHIVED
    
    # 2. cleanup_low_salience_events
    await event_repo.upsert(make_event("to_delete", salience=0.1, status=EventStatus.ACTIVE))
    # threshold 0.3 will catch active_low (ARCHIVED) and to_delete (ACTIVE)
    count = await event_repo.cleanup_low_salience_events(threshold=0.3)
    assert count == 2
    assert await event_repo.get("to_delete") is None
    assert await event_repo.get("active_low") is None
    
    # 3. delete_old_archived_events
    await event_repo.set_status("active_high", EventStatus.ARCHIVED)
    # Set end_time to very old
    ev = await event_repo.get("active_high")
    ev.end_time = NOW - 10000
    await event_repo.upsert(ev)
    
    count = await event_repo.delete_old_archived_events(cutoff_ts=NOW - 5000)
    assert count == 1 # active_high
    assert await event_repo.get("active_high") is None

@pytest.mark.asyncio
async def test_event_bulk_deletes(event_repo):
    await event_repo.upsert(make_event("e1", group_id="g1"))
    await event_repo.upsert(make_event("e2", group_id="g1"))
    await event_repo.upsert(make_event("e3", group_id="g2"))
    
    count = await event_repo.delete_by_group("g1")
    assert count == 2
    assert await event_repo.count_by_status(EventStatus.ACTIVE) == 1
    
    await event_repo.delete_all()
    assert await event_repo.count_by_status(EventStatus.ACTIVE) == 0

@pytest.mark.asyncio
async def test_prune_group_history(event_repo):
    def make_ev_with_msgs(eid, count, start_offset):
        ev = make_event(eid)
        ev.interaction_flow = [MessageRef("u1", NOW, "h", "p")] * count
        ev.start_time = NOW + start_offset
        return ev
        
    await event_repo.upsert(make_ev_with_msgs("e1", 50, 0)) # oldest
    await event_repo.upsert(make_ev_with_msgs("e2", 50, 10))
    await event_repo.upsert(make_ev_with_msgs("e3", 50, 20)) # newest
    
    # Total messages = 150. Prune to 100. target = 100 - 10 = 90.
    # e1 (50) deleted -> 100 messages left. 100 > 90.
    # e2 (50) deleted -> 50 messages left. 50 <= 90.
    count = await event_repo.prune_group_history("g1", max_messages=100, batch_size=10)
    assert count == 2
    assert await event_repo.get("e1") is None
    assert await event_repo.get("e2") is None
    assert await event_repo.get("e3") is not None

@pytest.mark.asyncio
async def test_event_rowid_mapping(event_repo):
    await event_repo.upsert(make_event("e1"))
    rowid = await event_repo.get_rowid("e1")
    assert rowid is not None
    
    ev = await event_repo.get_by_rowid(rowid)
    assert ev.event_id == "e1"

@pytest.mark.asyncio
async def test_message_counting(event_repo):
    ev1 = make_event("e1", group_id="g1")
    ev1.interaction_flow = [MessageRef("u1", NOW, "h", "p")] * 10
    await event_repo.upsert(ev1)
    
    ev2 = make_event("e2", group_id="g1")
    ev2.interaction_flow = [MessageRef("u2", NOW, "h", "p")] * 5
    await event_repo.upsert(ev2)
    
    counts = await event_repo.count_messages_by_uid_bulk()
    assert counts["u1"] == 10
    assert counts["u2"] == 5
    
    edge_count = await event_repo.count_edge_messages("u1", "u2", scope="g1")
    assert edge_count == 15

@pytest.mark.asyncio
async def test_tag_abstraction(event_repo):
    await event_repo.upsert(make_event("e1", chat_content_tags=["tag1", "tag2"]))
    await event_repo.upsert(make_event("e2", chat_content_tags=["tag1"]))
    
    tags = await event_repo.list_frequent_tags(limit=10)
    assert "tag1" in tags
    assert "tag2" in tags
    
    await event_repo.upsert_canonical_tag("TagOne", [0.1] * 384)
    # search_canonical_tag might fail or return [] if vec0 is not active, which is fine for coverage
    await event_repo.search_canonical_tag([0.1] * 384)

@pytest.mark.asyncio
async def test_impression_bot_persona_filtering(impression_repo):
    from core.domain.models import Impression
    def make_imp(bot):
        return Impression("u1", "u2", "affinity", 0.5, 0.0, 0.5, 0.5, 0.5, "g1", [], NOW, bot_persona_name=bot)
        
    await impression_repo.upsert(make_imp("Alice"))
    await impression_repo.upsert(make_imp("Bob"))
    await impression_repo.upsert(make_imp(None)) # Legacy
    
    # Test get with bot_persona_name
    assert (await impression_repo.get("u1", "u2", "g1", bot_persona_name="Alice")) is not None
    
    # include_legacy=False
    alice_imps = await impression_repo.list_by_observer("u1", bot_persona_name="Alice", include_legacy=False)
    assert len(alice_imps) == 1
    
    # bot_persona_name=None -> no filter by bot_persona_name, returns all
    all_imps = await impression_repo.list_by_observer("u1", bot_persona_name=None)
    assert len(all_imps) == 3


@pytest.mark.asyncio
async def test_bump_event_usage(event_repo):
    event = make_event("e_bump", salience=0.4)
    await event_repo.upsert(event)
    
    # Assert initial state
    db_ev = await event_repo.get("e_bump")
    assert db_ev.salience == 0.4
    assert db_ev.access_count == 0
    
    # Bump usage
    now = time.time()
    success = await event_repo.bump_event_usage("e_bump", 0.8, now)
    assert success is True
    
    # Verify updated values
    db_ev_updated = await event_repo.get("e_bump")
    assert db_ev_updated.salience == 0.8
    assert db_ev_updated.access_count == 1
    assert abs(db_ev_updated.last_accessed_at - now) < 1e-3
    
    # Non-existent event
    success_none = await event_repo.bump_event_usage("nonexistent", 0.9, now)
    assert success_none is False

