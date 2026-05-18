import pytest
from unittest.mock import AsyncMock, MagicMock
from core.tasks.reindex import run_reindex_all
from core.domain.models import Event

@pytest.mark.asyncio
async def test_run_reindex_all():
    event_repo = AsyncMock()
    retriever = AsyncMock()
    
    events = [
        Event(event_id="e1", topic="topic1"),
        Event(event_id="e2", topic="topic2"),
    ]
    event_repo.list_all.return_value = events
    
    count = await run_reindex_all(event_repo, retriever)
    
    assert count == 2
    assert retriever.index_event.call_count == 2
    retriever.index_event.assert_any_call(events[0])
    retriever.index_event.assert_any_call(events[1])

@pytest.mark.asyncio
async def test_run_reindex_all_with_error():
    event_repo = AsyncMock()
    retriever = AsyncMock()
    
    events = [
        Event(event_id="e1", topic="topic1"),
        Event(event_id="e2", topic="topic2"),
    ]
    event_repo.list_all.return_value = events
    
    # Second call fails
    retriever.index_event.side_effect = [None, RuntimeError("fail")]
    
    count = await run_reindex_all(event_repo, retriever)
    
    assert count == 1
    assert retriever.index_event.call_count == 2
