"""Tests for EmbeddingManager: batching, concurrency, and retries."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from core.managers.embedding_manager import EmbeddingManager
from core.config import EmbeddingConfig

class MockEncoder:
    def __init__(self, dim=512):
        self._dim = dim
        self.encode_batch = AsyncMock()

    @property
    def dim(self):
        return self._dim

@pytest.fixture
def embed_cfg():
    return EmbeddingConfig(
        batch_size=2,
        batch_interval_ms=100,
        concurrency=1,
        retry_max=1,
        retry_delay_ms=10
    )

@pytest.mark.asyncio
async def test_batching(embed_cfg):
    encoder = MockEncoder()
    # Mock result for batch of 2
    encoder.encode_batch.side_effect = lambda texts: [[0.1] * 512 for _ in texts]
    
    mgr = EmbeddingManager(encoder, embed_cfg)
    await mgr.start()
    
    # Send two requests
    t1 = asyncio.create_task(mgr.encode("hello"))
    t2 = asyncio.create_task(mgr.encode("world"))
    
    res1 = await t1
    res2 = await t2
    
    assert len(res1) == 512
    assert len(res2) == 512
    # Verify it was called as a batch
    assert encoder.encode_batch.call_count == 1
    assert encoder.encode_batch.call_args[0][0] == ["hello", "world"]
    
    await mgr.stop()

@pytest.mark.asyncio
async def test_retry_logic(embed_cfg):
    encoder = MockEncoder()
    # Fail first time, succeed second
    encoder.encode_batch.side_effect = [
        RuntimeError("API Error"),
        [[0.2] * 512]
    ]
    
    mgr = EmbeddingManager(encoder, embed_cfg)
    await mgr.start()
    
    res = await mgr.encode("retry me")
    assert res[0] == 0.2
    assert encoder.encode_batch.call_count == 2
    
    await mgr.stop()

@pytest.mark.asyncio
async def test_concurrency_control(embed_cfg):
    embed_cfg.concurrency = 1
    embed_cfg.batch_size = 1
    encoder = MockEncoder()
    
    # Make the call take some time
    async def slow_encode(texts):
        await asyncio.sleep(0.2)
        return [[0.3] * 512]
    encoder.encode_batch.side_effect = slow_encode
    
    mgr = EmbeddingManager(encoder, embed_cfg)
    await mgr.start()
    
    t1 = asyncio.create_task(mgr.encode("first"))
    t2 = asyncio.create_task(mgr.encode("second"))
    
    await asyncio.sleep(0.1)
    # Only first should be in progress (semaphore held)
    assert encoder.encode_batch.call_count == 1
    
    await t1
    await t2
    assert encoder.encode_batch.call_count == 2
    
    await mgr.stop()
