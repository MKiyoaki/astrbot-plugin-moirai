import pytest
import json
import httpx
from unittest.mock import AsyncMock, patch
from core.utils.llm import SimpleLLMClient, LLMResponse, MockProviderBridge

@pytest.mark.asyncio
async def test_simple_llm_client_success():
    client = SimpleLLMClient(api_url="https://api.openai.com/v1", api_key="sk-123", model="gpt-3.5-turbo")
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{
            "message": {
                "content": "hello world"
            }
        }]
    }
    
    # We need to mock the async context manager of httpx.AsyncClient
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        
        resp = await client.text_chat("hi", system_prompt="be nice")
        
        assert isinstance(resp, LLMResponse)
        assert resp.completion_text == "hello world"
        
        # Verify call details
        args, kwargs = mock_post.call_args
        assert kwargs["json"]["model"] == "gpt-3.5-turbo"
        assert kwargs["json"]["messages"][0]["role"] == "system"
        assert kwargs["json"]["messages"][1]["content"] == "hi"

@pytest.mark.asyncio
async def test_simple_llm_client_failure():
    client = SimpleLLMClient(api_url="https://api.openai.com/v1", api_key="sk-123", model="gpt-3.5-turbo")
    
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("500", request=None, response=mock_response)
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        
        with pytest.raises(httpx.HTTPStatusError):
            await client.text_chat("hi")

@pytest.mark.asyncio
async def test_mock_provider_bridge():
    mock_client = AsyncMock(spec=SimpleLLMClient)
    mock_client.text_chat.return_value = LLMResponse("bridged response")
    
    bridge = MockProviderBridge(mock_client)
    resp = await bridge.text_chat("test prompt", "test system")
    
    assert resp.completion_text == "bridged response"
    mock_client.text_chat.assert_called_with("test prompt", "test system")

from unittest.mock import MagicMock
