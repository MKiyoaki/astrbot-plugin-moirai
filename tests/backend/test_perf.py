import asyncio
import pytest
from core.utils.perf import tracker, performance_timer
from core.api import get_stats
from core.repository.memory import (
    InMemoryEventRepository,
    InMemoryImpressionRepository,
    InMemoryPersonaRepository,
)

@pytest.fixture(autouse=True)
async def reset_tracker():
    """Reset the global tracker before each test."""
    async with tracker._lock:
        tracker._history.clear()
        tracker._last_durations.clear()
        tracker._hit_history.clear()
    yield

@pytest.mark.asyncio
async def test_perf_tracker_records_and_averages():
    async with performance_timer("extraction"):
        await asyncio.sleep(0.01)
    
    async with performance_timer("extraction"):
        await asyncio.sleep(0.03)
        
    averages = await tracker.get_averages()
    assert 0.01 <= averages["extraction"] <= 0.06 # Allow some overhead
    assert averages.get("retrieval", 0.0) == 0.0

@pytest.mark.asyncio
async def test_get_stats_includes_perf_data():
    await tracker.record("extraction", 0.5)
    await tracker.record("retrieval", 0.1)
    await tracker.record("recall", 0.2)
    await tracker.record("response", 0.8)
    await tracker.record_hit("recall", 5)
    
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()
    
    stats = await get_stats(pr, er, ir)
    assert "perf" in stats
    # Check new nested structure
    assert stats["perf"]["extraction"]["avg_ms"] == 500.0
    assert stats["perf"]["retrieval"]["avg_ms"] == 100.0
    assert stats["perf"]["recall"]["avg_ms"] == 200.0
    assert stats["perf"]["response"]["avg_ms"] == 800.0
    assert stats["perf"]["recall"]["last_hits"] == 5
    
    # Check legacy flat fields
    assert stats["perf"]["avg_extraction_time"] == 0.5
    assert stats["perf"]["avg_retrieval_time"] == 0.1
    assert stats["perf"]["avg_recall_time"] == 0.2

@pytest.mark.asyncio
async def test_get_stats_counts_summaries(tmp_path):
    # Setup mock summaries files
    data_dir = tmp_path / "data"
    groups_dir = data_dir / "groups"
    g1_sum = groups_dir / "group1" / "summaries"
    g1_sum.mkdir(parents=True)
    (g1_sum / "2026-05-12.md").write_text("content")
    
    global_sum = data_dir / "global" / "summaries"
    global_sum.mkdir(parents=True)
    (global_sum / "2026-05-12.md").write_text("content")
    
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()
    
    stats = await get_stats(pr, er, ir, data_dir=data_dir)
    assert stats["summaries"] == 2
