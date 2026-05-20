"""Async batch writer for recent raw-message persistence."""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from ..domain.models import RawStoredMessage
from ..repository.base import RawMessageRepository

logger = logging.getLogger(__name__)

RAW_MESSAGE_BATCH_SIZE = 32
RAW_MESSAGE_FLUSH_INTERVAL_MS = 1000
RAW_MESSAGE_QUEUE_MAX_SIZE = 2000
RAW_MESSAGE_MAX_TEXT_CHARS = 4000
RAW_MESSAGE_ENQUEUE_TIMEOUT_SECONDS = 0.05


class RawMessageWriter:
    """Non-blocking raw-message persistence helper.

    The hot path enqueues records and returns quickly. A background task batches
    DB writes. Callers that need a specific message persisted can await
    ``ensure_flushed`` for those message ids.
    """

    def __init__(
        self,
        repo: RawMessageRepository,
        *,
        batch_size: int = RAW_MESSAGE_BATCH_SIZE,
        flush_interval_ms: int = RAW_MESSAGE_FLUSH_INTERVAL_MS,
        queue_max_size: int = RAW_MESSAGE_QUEUE_MAX_SIZE,
        max_text_chars: int = RAW_MESSAGE_MAX_TEXT_CHARS,
    ) -> None:
        self._repo = repo
        self._batch_size = max(1, int(batch_size))
        self._flush_interval = max(0.001, float(flush_interval_ms) / 1000.0)
        self._max_text_chars = max(1, int(max_text_chars))
        self._queue: asyncio.Queue[RawStoredMessage] = asyncio.Queue(
            maxsize=max(1, int(queue_max_size))
        )
        self._pending: dict[str, asyncio.Future[bool]] = {}
        self._task: asyncio.Task | None = None
        self._closed = False

    async def start(self) -> None:
        if self._closed:
            return
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(
                self._run(), name="moirai-raw-message-writer"
            )

    async def stop(self) -> None:
        self._closed = True
        await self._queue.join()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def enqueue(self, message: RawStoredMessage) -> bool:
        if self._closed:
            return False
        await self.start()
        message = self._truncate(message)
        loop = asyncio.get_running_loop()
        self._pending.setdefault(message.message_id, loop.create_future())
        try:
            await asyncio.wait_for(
                self._queue.put(message),
                timeout=RAW_MESSAGE_ENQUEUE_TIMEOUT_SECONDS,
            )
            return True
        except asyncio.TimeoutError:
            fut = self._pending.pop(message.message_id, None)
            if fut is not None and not fut.done():
                fut.set_result(False)
            logger.warning(
                "[RawMessageWriter] queue full; skipped raw message %s",
                message.message_id,
            )
            return False

    async def ensure_flushed(
        self, message_ids: list[str], timeout: float = 5.0
    ) -> bool:
        futures = [
            fut
            for mid in message_ids
            if (fut := self._pending.get(mid)) is not None
        ]
        if not futures:
            return True
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*futures, return_exceptions=True),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return False
        return all(result is True for result in results)

    async def flush_once(self) -> int:
        batch = self._drain_available()
        if not batch:
            return 0
        await self._write_batch(batch)
        return len(batch)

    async def _run(self) -> None:
        while True:
            try:
                first = await self._queue.get()
                batch = [first]
                deadline = asyncio.get_running_loop().time() + self._flush_interval
                while len(batch) < self._batch_size:
                    timeout = max(0.0, deadline - asyncio.get_running_loop().time())
                    if timeout <= 0:
                        break
                    try:
                        batch.append(await asyncio.wait_for(self._queue.get(), timeout))
                    except asyncio.TimeoutError:
                        break
                await self._write_batch(batch)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("[RawMessageWriter] worker error: %s", exc)

    def _drain_available(self) -> list[RawStoredMessage]:
        batch: list[RawStoredMessage] = []
        while len(batch) < self._batch_size:
            try:
                batch.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return batch

    async def _write_batch(self, batch: list[RawStoredMessage]) -> None:
        success = False
        try:
            await self._repo.upsert_many(batch)
            success = True
        except Exception as exc:
            logger.warning(
                "[RawMessageWriter] failed to persist %d raw messages: %s",
                len(batch),
                exc,
            )
        finally:
            for message in batch:
                fut = self._pending.pop(message.message_id, None)
                if fut is not None and not fut.done():
                    fut.set_result(success)
                self._queue.task_done()

    def _truncate(self, message: RawStoredMessage) -> RawStoredMessage:
        if len(message.text) <= self._max_text_chars:
            return message
        from dataclasses import replace

        return replace(message, text=message.text[: self._max_text_chars])
