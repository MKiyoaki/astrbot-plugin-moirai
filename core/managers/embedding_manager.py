"""Shared asynchronous embedding batching, concurrency, retry, and lifecycle control."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import EmbeddingConfig
    from ..embedding.encoder import Encoder

logger = logging.getLogger(__name__)


class EmbeddingManager:
    def __init__(self, encoder: Encoder, config: EmbeddingConfig) -> None:
        if min(config.request_batch_size, config.batch_size, config.concurrency) < 1:
            raise ValueError("Embedding batch sizes and concurrency must be positive")
        self._encoder, self._cfg = encoder, config
        self._queue = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._interval_lock = asyncio.Lock()
        self._last_request_time = 0.0
        self._closed = False
        self.disabled_reason: str | None = None

    @property
    def dim(self) -> int:
        return 0 if self.disabled_reason else self._encoder.dim

    @property
    def active(self) -> bool:
        from ..embedding.encoder import NullEncoder
        return not isinstance(self._encoder, NullEncoder) and not self.disabled_reason

    @property
    def identity(self) -> dict:
        return getattr(self._encoder, "identity", {
            "provider": self._cfg.provider, "model": self._cfg.model,
        })

    def metrics(self) -> dict:
        method = getattr(self._encoder, "metrics", None)
        metrics = method() if method else {}
        return {**metrics, "disabled": self.disabled_reason} if self.disabled_reason else metrics

    def disable(self, reason: str) -> None:
        """Turn off vector recall for this process; BM25 recall and stored vectors are untouched."""
        if not self.disabled_reason:
            self.disabled_reason = reason
            logger.error("[EmbeddingManager] vector recall disabled: %s", reason)

    async def start(self) -> None:
        if self._closed:
            raise RuntimeError("Embedding manager is closed")
        if not self._workers:
            self._workers = [asyncio.create_task(self._worker()) for _ in range(self._cfg.concurrency)]

    async def prepare(self, fallback: int) -> int:
        """Return the vector-table dimension at startup, or 0 when vectors are off.

        Local models stay lazily loaded and use the configured or fallback dimension.
        An unconfigured remote dimension is measured with one unretried request; if
        that fails, vector recall is disabled rather than blocking startup.
        """
        if not self.active:
            return 0
        if self._cfg.dimensions:
            return self._cfg.dimensions
        if self._cfg.provider != "api":
            return fallback
        try:
            vectors = await self._encoder.encode_batch(["Moirai embedding dimension probe"])
        except Exception as exc:
            self.disable(f"embedding endpoint unavailable at startup ({exc})")
            return 0
        return len(vectors[0])

    async def stop(self) -> None:
        if self._closed:
            return
        self._closed = True
        for _ in self._workers:
            self._queue.put_nowait(None)
        await asyncio.gather(*self._workers)
        self._workers.clear()
        close = getattr(self._encoder, "close", None)
        if close:
            await close()

    async def encode(self, text: str) -> list[float]:
        return (await self.encode_batch([text]))[0]

    async def encode_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._closed:
            raise RuntimeError("Embedding manager is closed")
        if not self.active:
            return [[] for _ in texts]
        await self.start()
        futures = [asyncio.get_running_loop().create_future() for _ in texts]
        for text, future in zip(texts, futures):
            self._queue.put_nowait((text, future))
        return await asyncio.gather(*futures)

    async def _request(self, texts: list[str]) -> list[list[float]]:
        for attempt in range(self._cfg.retry_max + 1):
            async with self._interval_lock:
                delay = self._cfg.request_interval_ms / 1000 - (time.monotonic() - self._last_request_time)
                if delay > 0:
                    await asyncio.sleep(delay)
                self._last_request_time = time.monotonic()
            try:
                results = await self._encoder.encode_batch(texts)
                if len(results) != len(texts):
                    raise ValueError("Embedding batch result count mismatch")
                return results
            except Exception as exc:
                if attempt == self._cfg.retry_max or not getattr(exc, "retryable", True):
                    raise
                await asyncio.sleep(min(self._cfg.retry_delay_ms / 1000 * 2 ** attempt, 60))
        raise RuntimeError("Embedding retry loop exhausted")

    async def _worker(self) -> None:
        cap = min(self._cfg.batch_size, self._cfg.request_batch_size)
        stopping = False
        while not stopping:
            first = await self._queue.get()
            if first is None:
                self._queue.task_done()
                return
            batch = [first]
            deadline = time.monotonic() + self._cfg.batch_interval_ms / 1000
            while len(batch) < cap:
                try:
                    item = self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    try:
                        item = await asyncio.wait_for(self._queue.get(), remaining)
                    except asyncio.TimeoutError:
                        break
                if item is None:
                    self._queue.task_done()
                    stopping = True
                    break
                batch.append(item)
            live = [(text, future) for text, future in batch if not future.done()]
            try:
                if live:
                    vectors = await self._request([text for text, _ in live])
                    for (_, future), vector in zip(live, vectors):
                        if not future.done():
                            future.set_result(vector)
            except Exception as exc:
                logger.warning("[EmbeddingManager] batch failed: %s", exc)
                for _, future in live:
                    if not future.done():
                        future.set_exception(exc)
            finally:
                for _ in batch:
                    self._queue.task_done()
