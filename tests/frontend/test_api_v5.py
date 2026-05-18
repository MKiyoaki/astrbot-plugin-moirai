import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.domain.models import Event
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
async def test_handle_recall(routes):
    # Setup: mock recall_manager
    mock_rm = AsyncMock()
    event = Event(event_id="e1", topic="test topic")
    mock_rm.recall.return_value = [event]
    routes._recall_manager = mock_rm
    
    req = mock_request(query={"q": "test", "limit": "5"})
    resp = await routes._handle_recall(req)
    assert resp.status_code == 200
    data = await get_json(resp)
    assert data["count"] == 1
    assert data["items"][0]["id"] == "e1"
    assert data["algorithm"] == "hybrid (rrf)"

@pytest.mark.asyncio
async def test_handle_persona_merge_preview(routes):
    # Mocking the SQLite DB requirement
    mock_db = MagicMock()
    routes._event_repo._db = mock_db
    
    with patch("core.repository.sqlite.preview_bot_persona_merge", new_callable=AsyncMock) as mock_preview:
        mock_preview.return_value = {"src_events": 1, "impacted_impressions": 2}
        
        req = mock_request(query={"src": "BotA", "target": "BotB"})
        resp = await routes._handle_persona_merge_preview(req)
        assert resp.status_code == 200
        data = await get_json(resp)
        assert data["src_events"] == 1

@pytest.mark.asyncio
async def test_handle_update_config(routes, tmp_path):
    # Setup mock schema
    routes._load_conf_schema = MagicMock(return_value={
        "group1": {
            "type": "object",
            "items": {
                "key1": {"type": "string", "default": "def"},
                "key2": {"type": "int", "default": 10}
            }
        }
    })
    
    req = mock_request(json_data={"key1": "new_val", "key2": 20})
    resp = await routes._handle_update_config(req)
    assert resp.status_code == 200
    
    # Verify file
    config_file = tmp_path / "plugin_config.json"
    assert config_file.exists()
    saved = json.loads(config_file.read_text(encoding="utf-8"))
    assert saved["key1"] == "new_val"
    assert saved["key2"] == 20
