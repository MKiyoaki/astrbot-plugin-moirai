import asyncio
import pytest
from core.utils.perf import tracker, performance_timer
from core.api import get_stats
from core.repository.memory import (
    InMemoryEventRepository,
    InMemoryImpressionRepository,
    InMemoryPersonaRepository,
)

@pytest.mark.asyncio
async def test_perf_tracker_records_and_averages():
    # Reset tracker for testing
    tracker._history["extraction"].clear()
    
    async with performance_timer("extraction"):
        await asyncio.sleep(0.01)
    
    async with performance_timer("extraction"):
        await asyncio.sleep(0.03)
        
    averages = await tracker.get_averages()
    assert 0.01 <= averages["extraction"] <= 0.05
    assert averages["retrieval"] == 0.0
    assert averages["recall"] == 0.0

@pytest.mark.asyncio
async def test_get_stats_includes_perf_data():
    tracker._history["extraction"].clear()
    await tracker.record("extraction", 0.5)
    await tracker.record("retrieval", 0.1)
    await tracker.record("recall", 0.2)
    
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()
    
    stats = await get_stats(pr, er, ir)
    assert "perf" in stats
    assert stats["perf"]["avg_extraction_time"] == 0.5
    assert stats["perf"]["avg_retrieval_time"] == 0.1
    assert stats["perf"]["avg_recall_time"] == 0.2
