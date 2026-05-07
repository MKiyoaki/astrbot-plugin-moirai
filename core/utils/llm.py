import json
import httpx
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

class LLMResponse:
    def __init__(self, text: str):
        self.completion_text = text

class SimpleLLMClient:
    """A simple OpenAI-compatible LLM client for testing and internal tasks."""
    
    def __init__(self, api_url: str, api_key: str, model: str):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def text_chat(self, prompt: str, system_prompt: str = "") -> LLMResponse:
        """Mimics AstrBot's Provider.text_chat interface."""
        url = f"{self.api_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1, # Low temperature for extraction
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code != 200:
                    logger.error(f"LLM request failed with status {response.status_code}: {response.text}")
                response.raise_for_status()
                data = response.json()
                text = data["choices"][0]["message"]["content"]
                return LLMResponse(text)
            except Exception as e:
                logger.error(f"LLM request failed: {e}")
                raise

class MockProviderBridge:
    """Bridges our SimpleLLMClient to the interface expected by EventExtractor."""
    def __init__(self, client: SimpleLLMClient):
        self.client = client
        
    async def text_chat(self, prompt: str, system_prompt: str = ""):
        return await self.client.text_chat(prompt, system_prompt)
