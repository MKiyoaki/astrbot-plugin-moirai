import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
from core.domain.models import Event, Persona, Impression, EventStatus
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
async def test_handle_stats(routes):
    # Setup some data
    await routes._persona_repo.upsert(Persona(
        uid="u1", primary_name="U1", bound_identities=[], persona_attrs={}, 
        confidence=1.0, created_at=0.0, last_active_at=0.0
    ))
    
    req = mock_request()
    resp = await routes._handle_stats(req)
    assert resp.status_code == 200
    data = await get_json(resp)
    assert data["personas"] == 1
    assert data["version"] == "0.1.3"

@pytest.mark.asyncio
async def test_handle_events(routes):
    # Setup an event
    await routes._event_repo.upsert(Event(
        event_id="e1", group_id="g1", status=EventStatus.ACTIVE
    ))
    
    # Test listing all
    req = mock_request(query={"limit": "10"})
    resp = await routes._handle_events(req)
    data = await get_json(resp)
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == "e1"
    
    # Test filtering by group
    req = mock_request(query={"group_id": "g2"})
    resp = await routes._handle_events(req)
    data = await get_json(resp)
    assert len(data["items"]) == 0

@pytest.mark.asyncio
async def test_handle_bot_personas_list(routes):
    # Setup events with bot_persona_name
    await routes._event_repo.upsert(Event(
        event_id="e1", bot_persona_name="BotA"
    ))
    await routes._event_repo.upsert(Event(
        event_id="e2", bot_persona_name="BotB"
    ))
    
    req = mock_request()
    resp = await routes._handle_bot_personas_list(req)
    data = await get_json(resp)
    assert len(data["items"]) >= 2
    names = [i["name"] for i in data["items"]]
    assert "BotA" in names
    assert "BotB" in names

@pytest.mark.asyncio
async def test_handle_get_config(routes, tmp_path):
    # Setup a mock config file
    config_file = tmp_path / "plugin_config.json"
    config_file.write_text(json.dumps({"test_key": "test_val"}))
    
    req = mock_request()
    resp = await routes._handle_get_config(req)
    data = await get_json(resp)
    assert data["values"]["test_key"] == "test_val"

@pytest.mark.asyncio
async def test_handle_update_event(routes):
    await routes._event_repo.upsert(Event(
        event_id="e1", topic="old topic", status=EventStatus.ACTIVE
    ))
    
    req = mock_request(json_data={"topic": "new topic"}, match_info={"event_id": "e1"})
    
    resp = await routes._handle_update_event(req)
    assert resp.status_code == 200
    data = await get_json(resp)
    assert data["ok"] is True
    assert data["event"]["topic"] == "new topic"
    
    # Verify persistence
    updated = await routes._event_repo.get("e1")
    assert updated.topic == "new topic"

@pytest.mark.asyncio
async def test_handle_delete_event(routes):
    await routes._event_repo.upsert(Event(
        event_id="e1", status=EventStatus.ACTIVE
    ))
    
    req = mock_request(match_info={"event_id": "e1"})
    
    resp = await routes._handle_delete_event(req)
    assert resp.status_code == 200
    assert (await get_json(resp))["ok"] is True
    
    assert await routes._event_repo.get("e1") is None
    assert len(routes._recycle_bin) == 1
    assert routes._recycle_bin[0]["id"] == "e1"

@pytest.mark.asyncio
async def test_handle_reanalyze_impressions(routes):
    # Setup some events to analyze
    await routes._event_repo.upsert(Event(
        event_id="e1", participants=["u1", "u2"], group_id="g1", status=EventStatus.ACTIVE
    ))
    await routes._event_repo.upsert(Event(
        event_id="e2", participants=["u1", "u2"], group_id="g1", status=EventStatus.ACTIVE
    ))
    
    req = mock_request(json_data={"scope": "g1"})
    resp = await routes._handle_reanalyze_impressions_guarded(req)
    assert resp.status_code == 200
    data = await get_json(resp)
    assert data["ok"] is True
    assert data["updated"] > 0
    
    # Check if impression was created
    imp = await routes._impression_repo.get("u1", "u2", "g1")
    assert imp is not None
    assert imp.observer_uid == "u1"
    assert imp.subject_uid == "u2"
