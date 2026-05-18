import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from core.domain.models import Event, Persona, EventStatus
from core.repository.memory import InMemoryEventRepository, InMemoryPersonaRepository, InMemoryImpressionRepository
from web.plugin_routes import PluginRoutes

@pytest.fixture
def routes(tmp_path):
    er = InMemoryEventRepository()
    pr = InMemoryPersonaRepository()
    ir = InMemoryImpressionRepository()
    return PluginRoutes(
        persona_repo=pr,
        event_repo=er,
        impression_repo=ir,
        data_dir=tmp_path,
        plugin_version="0.1.3"
    )

def mock_request(query=None, json_data=None, match_info=None):
    req = MagicMock()
    req.rel_url.query = query or {}
    req.args = query or {}
    req.match_info = match_info or {}
    req.view_args = match_info or {}
    if json_data:
        req.get_json = AsyncMock(return_value=json_data)
        req.json = json_data
    else:
        req.get_json = AsyncMock(return_value={})
    return req

async def get_json(resp):
    data = await resp.get_data()
    return json.loads(data)

@pytest.mark.asyncio
async def test_persona_crud(routes):
    # 1. Create
    req = mock_request(json_data={
        "uid": "p1",
        "primary_name": "Persona 1",
        "bound_identities": [{"platform": "qq", "physical_id": "123"}]
    })
    resp = await routes._handle_create_persona(req)
    assert resp.status_code == 201
    
    # 2. Update
    req = mock_request(json_data={"primary_name": "Updated Name"}, match_info={"uid": "p1"})
    resp = await routes._handle_update_persona(req)
    assert resp.status_code == 200
    data = await get_json(resp)
    assert data["persona"]["data"]["label"] == "Updated Name"
    
    # 3. Delete
    req = mock_request(match_info={"uid": "p1"})
    resp = await routes._handle_delete_persona(req)
    assert resp.status_code == 200
    assert await routes._persona_repo.get("p1") is None

@pytest.mark.asyncio
async def test_recycle_bin_operations(routes):
    # Setup: delete an event to put it in recycle bin
    await routes._event_repo.upsert(Event(event_id="e1", topic="to be deleted"))
    req_del = mock_request(match_info={"event_id": "e1"})
    await routes._handle_delete_event(req_del)
    assert len(routes._recycle_bin) == 1
    
    # 1. List
    req_list = mock_request()
    resp = await routes._handle_recycle_bin_list(req_list)
    data = await get_json(resp)
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == "e1"
    
    # 2. Restore
    req_restore = mock_request(json_data={"event_id": "e1"})
    resp = await routes._handle_recycle_bin_restore(req_restore)
    assert resp.status_code == 200
    assert await routes._event_repo.get("e1") is not None
    assert len(routes._recycle_bin) == 0
    
    # 3. Clear (setup again)
    await routes._handle_delete_event(req_del)
    assert len(routes._recycle_bin) == 1
    req_clear = mock_request()
    resp = await routes._handle_recycle_bin_clear(req_clear)
    assert resp.status_code == 200
    assert len(routes._recycle_bin) == 0

@pytest.mark.asyncio
async def test_update_summary(routes, tmp_path):
    req = mock_request(json_data={
        "group_id": "g1",
        "date": "2023-11-16",
        "content": "new summary content"
    })
    resp = await routes._handle_update_summary(req)
    assert resp.status_code == 200
    
    # Verify file
    path = tmp_path / "groups" / "g1" / "summaries" / "2023-11-16.md"
    assert path.exists()
    assert path.read_text(encoding="utf-8") == "new summary content"

@pytest.mark.asyncio
async def test_handle_tags_aggregation(routes):
    await routes._event_repo.upsert(Event(event_id="e1", group_id="g1", chat_content_tags=["tag1", "tag2"]))
    await routes._event_repo.upsert(Event(event_id="e2", group_id="g1", chat_content_tags=["tag1"]))
    
    req = mock_request()
    resp = await routes._handle_tags(req)
    data = await get_json(resp)
    # tag1 should have count 2, tag2 count 1
    tags = {t["name"]: t["count"] for t in data["tags"]}
    assert tags["tag1"] == 2
    assert tags["tag2"] == 1
