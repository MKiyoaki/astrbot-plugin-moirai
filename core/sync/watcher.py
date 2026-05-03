"""Asyncio polling file watcher.

Watches a set of registered paths for mtime changes and fires an async
callback when a file is modified.  Polling (default 30 s) is acceptable
because reverse sync is not latency-sensitive.

The _check_once() method is kept as a public-ish helper so tests can
trigger a check without needing to run the background loop.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_POLL_INTERVAL = 30.0


class FileWatcher:
    """Polls registered paths for mtime changes and fires async callbacks."""

    def __init__(self, poll_interval: float = _DEFAULT_POLL_INTERVAL) -> None:
        self._poll_interval = poll_interval
        # path → (last_known_mtime, callback)
        self._watched: dict[Path, tuple[float, Callable[[Path], Awaitable[None]]]] = {}
        self._task: asyncio.Task | None = None

    def register(self, path: Path, callback: Callable[[Path], Awaitable[None]]) -> None:
        """Watch path; fire callback with the path on every mtime change."""
        mtime = path.stat().st_mtime if path.exists() else 0.0
        self._watched[path] = (mtime, callback)

    def unregister(self, path: Path) -> None:
        self._watched.pop(path, None)

    async def _check_once(self) -> list[Path]:
        """Check all registered paths; fire callbacks for changed files.

        Returns the list of paths that triggered a callback (for testing).
        """
        changed: list[Path] = []
        for path, (last_mtime, callback) in list(self._watched.items()):
            if not path.exists():
                continue
            try:
                current_mtime = path.stat().st_mtime
            except OSError:
                continue
            if current_mtime != last_mtime:
                changed.append(path)
                self._watched[path] = (current_mtime, callback)
                try:
                    await callback(path)
                except Exception:
                    logger.exception("[FileWatcher] callback error for %s", path)
        return changed

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())
        logger.info("[FileWatcher] started, polling every %.0fs", self._poll_interval)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("[FileWatcher] stopped")

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._poll_interval)
            await self._check_once()
