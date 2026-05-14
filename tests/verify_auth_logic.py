import sys
import os
from pathlib import Path
import json
import shutil
import asyncio

# Setup mock environment
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from web.server import WebuiServer
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
        print(f"Secret token exists: {bool(server._secret_token)}")
        assert server.token_generated == True
        assert server._secret_token is not None
        
        # 2. Simulate User setting password via WebUI
        print("\n--- Phase 2: Setting password via WebUI ---")
        new_pw = "my_secure_password"
        
        class MockRequest:
            async def json(self):
                return {"webui_password": new_pw}
        
        # Mocking the schema path for the handler
        server._CONF_SCHEMA_PATH = ROOT / "_conf_schema.json"
        
        await server._handle_update_config(MockRequest())
        
        print(f"Hashed file exists: {(test_data_dir / '.webui_password').exists()}")
        print(f"Plaintext in config: '{star.config.get('webui_password')}'")
        print(f"Config saved: {star.saved}")
        
        assert (test_data_dir / ".webui_password").exists()
        assert star.config.get("webui_password") == new_pw # CRITICAL: Must be preserved!
        
        # 3. Simulate Restart with password set
        print("\n--- Phase 3: Restart with password ---")
        # In a real scenario, AstrBot would load the config with the password
        restarted_config = {"webui_password": new_pw}
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
        # Now verify that the actual authentication works
        v1 = auth.verify_password(new_pw)
        v2 = auth.verify_password("wrong_password")
        
        print(f"Verification (correct): {v1}")
        print(f"Verification (wrong): {v2}")
        
        assert v1 == True
        assert v2 == False
        
        print("\n✅ All authentication logic tests passed!")

    finally:
        shutil.rmtree(test_data_dir)

if __name__ == "__main__":
    asyncio.run(test_auth_logic())
