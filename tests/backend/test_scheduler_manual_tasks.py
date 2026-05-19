import asyncio

import pytest

from core.tasks.scheduler import TaskScheduler


@pytest.mark.asyncio
async def test_interval_zero_task_is_manual_only() -> None:
    calls = 0

    async def task() -> None:
        nonlocal calls
        calls += 1

    scheduler = TaskScheduler(tick_seconds=0.01)
    scheduler.register("manual", interval=0, fn=task)
    await scheduler.start()
    try:
        await asyncio.sleep(0.04)
        assert calls == 0

        assert await scheduler.run_now("manual") is True
        assert calls == 1
    finally:
        await scheduler.stop()
