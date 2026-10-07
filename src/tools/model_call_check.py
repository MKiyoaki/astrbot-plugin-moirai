import httpx
import asyncio

async def test_call():
    base_url = "http://localhost:1234/v1"
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        print("--- Step 1: Checking Available Models ---")
        try:
            m_resp = await client.get(f"{base_url}/models")
            if m_resp.status_code == 200:
                models = m_resp.json().get("data", [])
                if not models:
                    print("LMStudio reports NO models are currently loaded in memory.")
                    return
                print("Currently loaded models in LMStudio:")
                for m in models:
                    print(f" - ID: {m['id']}")
                # Use the first loaded model's ID for the next step
                target_model = models[0]['id']
            else:
                print(f"Failed to list models: {m_resp.text}")
                return
        except Exception as e:
            print(f"Could not connect to LMStudio: {e}")
            return

        print(f"\n--- Step 2: Calling Chat Completion with ID: {target_model} ---")
        headers = {"Authorization": "Bearer lm-studio", "Content-Type": "application/json"}
        payload = {
            "model": target_model,
            "messages": [{"role": "user", "content": "Ping? Respond with 'Pong' only."}],
            "max_tokens": 10,
            "temperature": 0.1
        }
        try:
            response = await client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
            if response.status_code == 200:
                print(f"Success! Response: {response.json()['choices'][0]['message']['content']}")
            else:
                print(f"Error {response.status_code}: {response.text}")
        except Exception as e:
            print(f"Chat call failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_call())
