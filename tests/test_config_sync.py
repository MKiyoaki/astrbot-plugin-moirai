import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from web.plugin_routes import PluginRoutes
from web.server import WebuiServer
from core.repository.memory import InMemoryPersonaRepository, InMemoryEventRepository, InMemoryImpressionRepository

@pytest.mark.asyncio
async def test_plugin_routes_config_sync(tmp_path):
    # Mock repositories
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()
    
    # Mock Star instance
    mock_star = MagicMock()
    mock_star.config = MagicMock()
    # Mock the behavior of a dict-like object for config
    config_dict = {}
    mock_star.config.update = MagicMock(side_effect=config_dict.update)
    mock_star.config.save_config = MagicMock()
    
    # Instantiate PluginRoutes
    routes = PluginRoutes(
        persona_repo=pr,
        event_repo=er,
        impression_repo=ir,
        data_dir=tmp_path,
        star=mock_star
    )
    
    # Mock _conf_schema.json for validation
    schema_content = {
        "webui": {
            "type": "object",
            "items": {
                "webui_port": {"type": "int", "default": 2655},
                "webui_enabled": {"type": "bool", "default": True}
            }
        }
    }
    
    schema_file = tmp_path / "_conf_schema.json"
    schema_file.write_text(json.dumps(schema_content))
    
    with patch("web.plugin_routes._CONF_SCHEMA_PATH", schema_file):
        # Prepare mock request
        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={
            "webui_port": "1234", # Should be coerced to int
            "webui_enabled": True,
            "non_existent_key": "ignore"
        })
        
        # Call the handler
        response = await routes._handle_update_config(mock_request)
        
        # 1. Check response
        assert response.status_code == 200
        resp_data = json.loads(await response.get_data())
        assert resp_data["ok"] is True
        assert "webui_port" in resp_data["saved"]
        assert "webui_enabled" in resp_data["saved"]
        assert "non_existent_key" not in resp_data["saved"]
        
        # 2. Check local file (Step 1 of implementation)
        local_cfg_path = tmp_path / "plugin_config.json"
        assert local_cfg_path.exists()
        local_cfg = json.loads(local_cfg_path.read_text())
        assert local_cfg["webui_port"] == 1234
        assert local_cfg["webui_enabled"] is True
        
        # 3. Check Star sync (Step 2 & 3 of implementation)
        mock_star.config.update.assert_called()
        assert config_dict["webui_port"] == 1234
        assert config_dict["webui_enabled"] is True
        mock_star.config.save_config.assert_called_once()


@pytest.mark.asyncio
async def test_webui_server_config_sync(tmp_path):
    # Mock repositories
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()
    
    # Mock Star instance
    mock_star = MagicMock()
    mock_star.config = MagicMock()
    config_dict = {}
    mock_star.config.update = MagicMock(side_effect=config_dict.update)
    mock_star.config.save_config = MagicMock()
    
    # Instantiate WebuiServer
    server = WebuiServer(
        persona_repo=pr,
        event_repo=er,
        impression_repo=ir,
        data_dir=tmp_path,
        star=mock_star,
        auth_enabled=False # Disable auth for easier testing
    )
    
    # Mock _conf_schema.json
    schema_content = {
        "webui": {
            "type": "object",
            "items": {
                "webui_port": {"type": "int", "default": 2655}
            }
        }
    }
    schema_file = tmp_path / "_conf_schema.json"
    schema_file.write_text(json.dumps(schema_content))
    
    with patch.object(WebuiServer, "_CONF_SCHEMA_PATH", schema_file):
        # Prepare mock request for aiohttp
        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={"webui_port": 8888})
        
        # Call the handler directly
        response = await server._handle_update_config(mock_request)
        
        # 1. Check response
        assert response.status == 200
        resp_data = json.loads(response.text)
        assert resp_data["ok"] is True
        
        # 2. Check local file
        local_cfg_path = tmp_path / "plugin_config.json"
        assert local_cfg_path.exists()
        local_cfg = json.loads(local_cfg_path.read_text())
        assert local_cfg["webui_port"] == 8888
        
        # 3. Check Star sync
        mock_star.config.update.assert_called()
        assert config_dict["webui_port"] == 8888
        mock_star.config.save_config.assert_called_once()

@pytest.mark.asyncio
async def test_config_read_priority(tmp_path):
    """Verify that WebUI reads from both initial_config (AstrBot) and local plugin_config.json."""
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()
    
    # 1. Initial config from AstrBot
    initial_config = {"webui_port": 1111, "language": "en-US"}
    
    # 2. Local config from previous WebUI save
    local_cfg_path = tmp_path / "plugin_config.json"
    local_cfg_path.write_text(json.dumps({"webui_port": 2222}))
    
    # Mock _conf_schema.json
    schema_content = {
        "webui": {
            "type": "object",
            "items": {
                "webui_port": {"type": "int", "default": 2655},
                "language": {"type": "string", "default": "zh-CN"}
            }
        }
    }
    schema_file = tmp_path / "_conf_schema.json"
    schema_file.write_text(json.dumps(schema_content))
    
    routes = PluginRoutes(
        persona_repo=pr,
        event_repo=er,
        impression_repo=ir,
        data_dir=tmp_path,
        initial_config=initial_config
    )
    
    with patch("web.plugin_routes._CONF_SCHEMA_PATH", schema_file):
        # _read_config is internal but used by _handle_get_config
        config = routes._read_config()
        
        # Local config should override initial config
        assert config["webui_port"] == 2222
        # Initial config should be present if not in local
        assert config["language"] == "en-US"
