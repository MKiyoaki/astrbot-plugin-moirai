import sys
import os
from pathlib import Path
import json
import shutil
import asyncio

# Setup mock environment
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from web.server import WebuiServer, _PASSWORD_MASK
from web.auth import AuthManager

class MockStar:
    def __init__(self, config):
        self.config = config
        self.saved = False
    
    def save_config(self):
        self.saved = True

async def test_auth_logic():
    test_data_dir = ROOT / "tests" / "test_data_auth"
    if test_data_dir.exists():
        shutil.rmtree(test_data_dir)
    test_data_dir.mkdir(parents=True)
    
    try:
        # 1. Simulate empty config (First start)
        print("\n--- Phase 1: First Start (No password) ---")
        initial_config = {}
        star = MockStar(initial_config)
        
        server = WebuiServer(
            persona_repo=None, event_repo=None, impression_repo=None,
            data_dir=test_data_dir, star=star, auth_enabled=True,
            initial_config=initial_config
        )
        
        print(f"Token generated: {server.token_generated}")
        assert server.token_generated == True
        
        # 2. Simulate User setting password via WebUI
        print("\n--- Phase 2: Setting password via WebUI ---")
        new_pw = "my_secure_password"
        
        class MockRequest:
            async def json(self):
                return {"webui_password": new_pw}
        
        server._CONF_SCHEMA_PATH = ROOT / "_conf_schema.json"
        await server._handle_update_config(MockRequest())
        
        print(f"Hashed file exists: {(test_data_dir / '.webui_password').exists()}")
        print(f"Mask in config: '{star.config.get('webui_password')}'")
        
        assert (test_data_dir / ".webui_password").exists()
        assert star.config.get("webui_password") == _PASSWORD_MASK # CRITICAL: Must be MASKED!
        
        # 3. Simulate Restart with mask in config
        print("\n--- Phase 3: Restart with Masked Config ---")
        restarted_config = {"webui_password": _PASSWORD_MASK}
        restarted_star = MockStar(restarted_config)
        
        restarted_server = WebuiServer(
            persona_repo=None, event_repo=None, impression_repo=None,
            data_dir=test_data_dir, star=restarted_star, auth_enabled=True,
            initial_config=restarted_config
        )
        
        print(f"Token generated: {restarted_server.token_generated}")
        assert restarted_server.token_generated == False
        
        # 4. Verify Authentication
        print("\n--- Phase 4: Verifying Authentication ---")
        auth = restarted_server._auth
        v1 = auth.verify_password(new_pw)
        v2 = auth.verify_password("wrong_password")
        
        print(f"Verification (correct): {v1}")
        print(f"Verification (wrong): {v2}")
        
        assert v1 == True
        assert v2 == False
        
        # 5. Simulate setting password via PANEL (Plaintext)
        print("\n--- Phase 5: Setting password via Panel (Plaintext) ---")
        panel_pw = "panel_password_123"
        panel_config = {"webui_password": panel_pw}
        panel_star = MockStar(panel_config)
        
        # This simulates plugin restart after user saves plaintext in panel
        panel_server = WebuiServer(
            persona_repo=None, event_repo=None, impression_repo=None,
            data_dir=test_data_dir, star=panel_star, auth_enabled=True,
            initial_config=panel_config
        )
        
        print(f"New password masked in config: {panel_star.config.get('webui_password') == _PASSWORD_MASK}")
        print(f"Token generated: {panel_server.token_generated}")
        
        assert panel_star.config.get("webui_password") == _PASSWORD_MASK
        assert panel_server.token_generated == False
        assert panel_server._auth.verify_password(panel_pw) == True
        
        print("\n✅ All secure masking and auth logic tests passed!")

    finally:
        shutil.rmtree(test_data_dir)

if __name__ == "__main__":
    asyncio.run(test_auth_logic())
