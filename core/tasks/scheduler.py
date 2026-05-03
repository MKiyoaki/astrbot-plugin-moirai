"""Simple asyncio periodic task scheduler.

Tasks are registered with an interval (seconds). The internal loop ticks
every _tick seconds and fires any task whose interval has elapsed since its
last successful run. All tasks run sequentially within one tick to avoid
concurrent writes to shared state.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

_DEFAULT_TICK = 60.0


@dataclass
class _Task:
    name: str
    interval: float
    fn: Callable[[], Awaitable[None]]
    last_run: float = field(default=0.0)


class TaskScheduler:
    """Runs registered async callables on fixed intervals.

    Usage::

        scheduler = TaskScheduler()
        scheduler.register("decay", interval=86400, fn=my_async_fn)
        await scheduler.start()
        ...
        await scheduler.stop()
    """

    def __init__(self, tick_seconds: float = _DEFAULT_TICK) -> None:
        self._tick = tick_seconds
        self._tasks: list[_Task] = []
        self._handle: asyncio.Task | None = None  # type: ignore[type-arg]

    def register(
        self,
        name: str,
        interval: float,
        fn: Callable[[], Awaitable[None]],
    ) -> None:
        """Register a periodic task. Duplicate names are allowed."""
        self._tasks.append(_Task(name=name, interval=interval, fn=fn))

    async def start(self) -> None:
        """Spawn the background scheduling loop."""
        self._handle = asyncio.create_task(self._loop(), name="task-scheduler")
        logger.info("[Scheduler] started with %d task(s)", len(self._tasks))

    async def stop(self) -> None:
        """Cancel the scheduling loop and wait for it to finish."""
        if self._handle is not None:
            self._handle.cancel()
            try:
                await self._handle
            except asyncio.CancelledError:
                pass
            self._handle = None
        logger.info("[Scheduler] stopped")

    async def run_now(self, name: str) -> bool:
        """Immediately execute a named task outside the normal schedule.

        Returns False if no task with that name is registered.
        """
        for task in self._tasks:
            if task.name == name:
                await self._run_task(task)
                return True
        return False

    @property
    def task_names(self) -> list[str]:
        return [t.name for t in self._tasks]

    async def _loop(self) -> None:
        while True:
            now = time.time()
            for task in self._tasks:
                if now - task.last_run >= task.interval:
                    await self._run_task(task)
            await asyncio.sleep(self._tick)

    async def _run_task(self, task: _Task) -> None:
        try:
            logger.debug("[Scheduler] running %r", task.name)
            await task.fn()
            task.last_run = time.time()
        except Exception as exc:
            logger.error("[Scheduler] task %r failed: %s", task.name, exc)
