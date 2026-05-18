import pytest
from unittest.mock import AsyncMock, MagicMock
from core.api import (
    list_archived_events,
    get_event,
    update_event,
    delete_event,
    list_personas,
    update_impression,
    recall_preview
)
from core.domain.models import Event, Persona, Impression, EventStatus

@pytest.fixture
def mock_repos():
    persona_repo = AsyncMock()
    event_repo = AsyncMock()
    impression_repo = AsyncMock()
    memory = AsyncMock()
    recall = AsyncMock()
    return persona_repo, event_repo, impression_repo, memory, recall

@pytest.mark.asyncio
async def test_list_archived_events(mock_repos):
    pr, er, ir, memory, recall = mock_repos
    er.list_by_status.return_value = [Event(event_id="e1", status=EventStatus.ARCHIVED)]
    res = await list_archived_events(er)
    assert len(res["items"]) == 1
    assert res["items"][0]["id"] == "e1"

@pytest.mark.asyncio
async def test_get_event(mock_repos):
    pr, er, ir, memory, recall = mock_repos
    er.get.return_value = Event(event_id="e1")
    res = await get_event(er, "e1")
    assert res["id"] == "e1"
    
    er.get.return_value = None
    res = await get_event(er, "unknown")
    assert res is None

@pytest.mark.asyncio
async def test_update_event(mock_repos):
    pr, er, ir, memory, recall = mock_repos
    event = Event(event_id="e1", topic="old")
    memory.get_event.return_value = event
    
    res = await update_event(memory, "e1", {"topic": "new", "salience": 0.9, "is_locked": True})
    assert res["topic"] == "new"
    assert res["salience"] == 0.9
    assert res["is_locked"] is True
    memory.update_event.assert_called_once()

@pytest.mark.asyncio
async def test_delete_event(mock_repos):
    pr, er, ir, memory, recall = mock_repos
    memory.delete_event.return_value = True
    res = await delete_event(memory, "e1")
    assert res is True
    memory.delete_event.assert_called_once_with("e1")

@pytest.mark.asyncio
async def test_list_personas(mock_repos):
    pr, er, ir, memory, recall = mock_repos
    pr.list_all.return_value = [Persona("u1", [], "Alice", {}, 0.5, 0.0, 0.0)]
    res = await list_personas(pr)
    assert len(res) == 1
    assert res[0]["uid"] == "u1"

@pytest.mark.asyncio
async def test_update_impression(mock_repos):
    pr, er, ir, memory, recall = mock_repos
    imp = Impression("u1", "u2", "affinity", 0.0, 0.0, 0.0, 0.0, 0.0, "g1", [], 0.0)
    ir.get.return_value = imp
    
    res = await update_impression(ir, "u1", "u2", "g1", {"benevolence": 0.5, "affect_intensity": 0.7})
    assert res["benevolence"] == 0.5
    assert res["affect_intensity"] == 0.7
    ir.upsert.assert_called_once()

@pytest.mark.asyncio
async def test_recall_preview(mock_repos):
    pr, er, ir, memory, recall = mock_repos
    recall.recall.return_value = [Event(event_id="e1")]
    res = await recall_preview(recall, "query", group_id="g1")
    assert len(res) == 1
    assert res[0]["id"] == "e1"
    recall.recall.assert_called_once_with("query", group_id="g1", scope_mode="group")
