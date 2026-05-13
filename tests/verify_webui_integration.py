import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

# Add project root to sys path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import MoiraiPlugin
from core.config import PluginConfig
from core.plugin_initializer import PluginInitializer

async def test_moirai_initialization():
    print("Testing MoiraiPlugin.initialize()...")
    context = MagicMock()
    # Mock context.get_using_provider and other AstrBot internal methods
    context.get_using_provider = MagicMock(return_value=MagicMock())
    context.get_all_providers = MagicMock(return_value=[])
    
    plugin = MoiraiPlugin(context)
    # Mock register_page
    plugin.register_page = MagicMock()
    
    # Mock plugin config
    plugin.config = {
        "webui_enabled": True,
        "webui_port": 2656, # Use a different port to avoid conflict
        "embedding_enabled": False,
        "relation_enabled": True
    }
    
    # We need to mock PluginInitializer inside main.py if it tries to do heavy IO/Network
    # For now let's see if it runs
    try:
        await plugin.initialize()
        print("鉁 plugin.initialize() completed.")
        
        # Verify register_page was called
        plugin.register_page.assert_called_with("Moirai", "pages/moirai/index.html")
        print("鉁 register_page was called correctly.")
        
        # Verify standalone webui server started (it should be running now on port 2656)
        if plugin._initializer.webui and plugin._initializer.webui._runner:
            print(f"鉁 Standalone WebUI server is running on port {plugin._initializer.webui._port}.")
        else:
            print("鉁 Standalone WebUI server is NOT running (expected if port busy or disabled).")
            
        await plugin.terminate()
        print("鉁 plugin.terminate() completed.")
    except Exception as e:
        print(f"鉁 Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_moirai_initialization())
