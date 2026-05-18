import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from core.managers.memory_manager import MemoryManager
from core.domain.models import Event, EventStatus, MessageRef
from core.repository.memory import InMemoryEventRepository
from core.config import DecayConfig, ContextConfig

@pytest.fixture
def memory_manager():
    event_repo = InMemoryEventRepository()
    retriever = AsyncMock()
    encoder = AsyncMock()
    encoder.dim = 384
    decay_config = DecayConfig(lambda_=0.01)
    context_config = ContextConfig(max_history_messages=120, cleanup_batch_size=20)
    return MemoryManager(event_repo, retriever, encoder, decay_config, context_config), event_repo, retriever, encoder

@pytest.mark.asyncio
async def test_memory_manager_add_event(memory_manager):
    mm, repo, retriever, encoder = memory_manager
    event = Event(event_id="e1", group_id="g1", topic="test")
    encoder.encode.return_value = [0.1, 0.2]
    
    await mm.add_event(event)
    
    stored = await repo.get("e1")
    assert stored is not None
    assert stored.topic == "test"
    encoder.encode.assert_called_once()

@pytest.mark.asyncio
async def test_memory_manager_add_event_no_encoder(memory_manager):
    mm, repo, retriever, encoder = memory_manager
    encoder.dim = 0
    event = Event(event_id="e1", group_id="g1", topic="test")
    
    await mm.add_event(event)
    
    assert await repo.get("e1") is not None
    encoder.encode.assert_not_called()

@pytest.mark.asyncio
async def test_memory_manager_update_event(memory_manager):
    mm, repo, retriever, encoder = memory_manager
    event = Event(event_id="e1", group_id="g1", topic="old")
    await repo.upsert(event)
    
    updated_event = Event(event_id="e1", group_id="g1", topic="new")
    encoder.encode.return_value = [0.3, 0.4]
    
    await mm.update_event(updated_event)
    
    stored = await repo.get("e1")
    assert stored.topic == "new"
    encoder.encode.assert_called_once()

@pytest.mark.asyncio
async def test_memory_manager_delete_event(memory_manager):
    mm, repo, retriever, encoder = memory_manager
    event = Event(event_id="e1", group_id="g1")
    await repo.upsert(event)
    
    success = await mm.delete_event("e1")
    assert success is True
    assert await repo.get("e1") is None

@pytest.mark.asyncio
async def test_memory_manager_lifecycle(memory_manager):
    mm, repo, retriever, encoder = memory_manager
    event = Event(event_id="e1", status=EventStatus.ACTIVE)
    await repo.upsert(event)
    
    await mm.archive_event("e1")
    assert (await repo.get("e1")).status == EventStatus.ARCHIVED
    
    await mm.unarchive_event("e1")
    assert (await repo.get("e1")).status == EventStatus.ACTIVE
    
    await mm.lock_event("e1")
    assert (await repo.get("e1")).is_locked is True
    
    await mm.unlock_event("e1")
    assert (await repo.get("e1")).is_locked is False

@pytest.mark.asyncio
async def test_memory_manager_list_status(memory_manager):
    mm, repo, retriever, encoder = memory_manager
    await repo.upsert(Event(event_id="e1", status=EventStatus.ACTIVE))
    await repo.upsert(Event(event_id="e2", status=EventStatus.ARCHIVED))
    
    active = await mm.list_active_events()
    assert len(active) == 1
    assert active[0].event_id == "e1"
    
    archived = await mm.list_archived_events()
    assert len(archived) == 1
    assert archived[0].event_id == "e2"

@pytest.mark.asyncio
async def test_memory_manager_search(memory_manager):
    mm, repo, retriever, encoder = memory_manager
    event = Event(event_id="e1", status=EventStatus.ACTIVE)
    retriever.search.return_value = [event]
    
    results = await mm.search("query")
    assert len(results) == 1
    assert results[0].event_id == "e1"
    retriever.search.assert_called_once_with("query", limit=10)

@pytest.mark.asyncio
async def test_memory_manager_apply_decay(memory_manager):
    mm, repo, retriever, encoder = memory_manager
    await repo.upsert(Event(event_id="e1", salience=1.0))
    
    count = await mm.apply_decay()
    assert count == 1
    assert (await repo.get("e1")).salience < 1.0

@pytest.mark.asyncio
async def test_memory_manager_stats(memory_manager):
    mm, repo, retriever, encoder = memory_manager
    await repo.upsert(Event(event_id="e1", status=EventStatus.ACTIVE, salience=0.8, is_locked=True))
    await repo.upsert(Event(event_id="e2", status=EventStatus.ARCHIVED, salience=0.2))
    
    stats = await mm.stats()
    assert stats["active_count"] == 1
    assert stats["archived_count"] == 1
    assert stats["locked_count"] == 1
    assert stats["avg_salience"] == 0.8
    assert stats["min_salience"] == 0.8
    assert stats["max_salience"] == 0.8

@pytest.mark.asyncio
async def test_memory_manager_pruning(memory_manager):
    mm, repo, retriever, encoder = memory_manager
    
    # Create an event with 50 messages
    flow = [MessageRef(sender_uid="u1", timestamp=0.0, content_hash="hi", content_preview="hi")] * 50
    event1 = Event(event_id="e1", group_id="g1", interaction_flow=flow, start_time=1000.0, end_time=1100.0)
    await mm.add_event(event1)
    
    # Add another event that should trigger pruning (max_history_messages=120, cleanup_batch_size=20)
    event2 = Event(event_id="e2", group_id="g1", interaction_flow=flow, start_time=2000.0, end_time=2100.0)
    await mm.add_event(event2)
    assert await repo.get("e1") is not None
    
    event3 = Event(event_id="e3", group_id="g1", interaction_flow=flow, start_time=3000.0, end_time=3100.0)
    # Total messages = 150. Should prune e1.
    await mm.add_event(event3)
    
    assert await repo.get("e1") is None
    assert await repo.get("e2") is not None
    assert await repo.get("e3") is not None
