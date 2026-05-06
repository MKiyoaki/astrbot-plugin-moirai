"""Tests for BaseRetryManager."""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from core.utils.retry import BaseRetryManager

class ConcreteRetryManager(BaseRetryManager[int]):
    async def _run(self, func, *args, **kwargs):
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        return func(*args, **kwargs)

@pytest.mark.asyncio
async def test_retry_success():
    mgr = ConcreteRetryManager(max_retries=2, delay_ms=1, backoff_factor=1)
    func = AsyncMock(return_value=42)
    
    result = await mgr.execute(func)
    assert result == 42
    assert func.call_count == 1

@pytest.mark.asyncio
async def test_retry_fail_then_success():
    mgr = ConcreteRetryManager(max_retries=2, delay_ms=1, backoff_factor=1)
    func = AsyncMock()
    func.side_effect = [ValueError("Fail"), ValueError("Fail"), 42]
    
    result = await mgr.execute(func)
    assert result == 42
    assert func.call_count == 3

@pytest.mark.asyncio
async def test_retry_all_fail():
    mgr = ConcreteRetryManager(max_retries=2, delay_ms=1, backoff_factor=1)
    func = AsyncMock(side_effect=ValueError("Persistent Fail"))
    
    with pytest.raises(ValueError, match="Persistent Fail"):
        await mgr.execute(func)
    assert func.call_count == 3
