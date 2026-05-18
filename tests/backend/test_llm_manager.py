import asyncio
import time
import pytest
from core.managers.llm_manager import LLMTaskManager

@pytest.mark.asyncio
async def test_llm_manager_concurrency():
    manager = LLMTaskManager(concurrency=2)
    
    active_count = 0
    max_active = 0
    
    async def mock_llm_call(duration=0.1):
        nonlocal active_count, max_active
        active_count += 1
        max_active = max(max_active, active_count)
        await asyncio.sleep(duration)
        active_count -= 1
        return "ok"

    # Run 5 tasks concurrently
    tasks = [
        manager.run(mock_llm_call, duration=0.2, task_name=f"task_{i}")
        for i in range(5)
    ]
    
    results = await asyncio.gather(*tasks)
    
    assert len(results) == 5
    assert all(r == "ok" for r in results)
    assert max_active == 2  # Concurrency limit should be respected
    assert manager.get_stats()["total_calls"] == 5

@pytest.mark.asyncio
async def test_llm_manager_failure():
    manager = LLMTaskManager(concurrency=1)
    
    async def failing_call():
        raise ValueError("simulated failure")
        
    with pytest.raises(ValueError, match="simulated failure"):
        await manager.run(failing_call)
        
    stats = manager.get_stats()
    assert stats["failed_calls"] == 1
    assert stats["total_calls"] == 1
    assert stats["active_tasks"] == 0


@pytest.mark.asyncio
async def test_llm_manager_recent_call_details_are_gated():
    manager = LLMTaskManager(concurrency=1)

    class Usage:
        input = 12
        output = 5

    class Result:
        usage = Usage()

    async def ok_call():
        return Result()

    async def failing_call():
        raise RuntimeError("provider unavailable")

    await manager.run(ok_call, task_name="summary")
    with pytest.raises(RuntimeError):
        await manager.run(failing_call, task_name="extraction")

    compact = manager.get_stats()
    detailed = manager.get_stats(show_details=True)

    assert "recent_calls" not in compact
    assert detailed["successful_calls"] == 1
    assert detailed["failed_calls"] == 1
    assert detailed["recent_calls"][0]["task_name"] == "extraction"
    assert detailed["recent_calls"][0]["success"] is False
    assert "provider unavailable" in detailed["recent_calls"][0]["error"]
    assert detailed["recent_calls"][1]["prompt_tokens"] == 12
