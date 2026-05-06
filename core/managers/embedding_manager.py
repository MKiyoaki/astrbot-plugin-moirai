"""EmbeddingManager: advanced batching, concurrency, and retry control."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, List, Dict, Any

from ..utils.retry import BaseRetryManager

if TYPE_CHECKING:
    from ..config import EmbeddingConfig
    from ..embedding.encoder import Encoder

logger = logging.getLogger(__name__)


class EmbeddingRetryManager(BaseRetryManager[List[List[float]]]):
    """Retry manager specialized for embedding batches."""
    
    async def _run(self, func: Any, *args: Any, **kwargs: Any) -> List[List[float]]:
        return await func(*args, **kwargs)


class EmbeddingManager:
    """Manages embedding requests with batching, concurrency, and intervals."""

    def __init__(self, encoder: Encoder, config: EmbeddingConfig) -> None:
        self._encoder = encoder
        self._cfg = config
        self._queue: asyncio.Queue[tuple[str, asyncio.Future[List[float]]]] = asyncio.Queue()
        self._semaphore = asyncio.Semaphore(config.concurrency)
        self._retry_mgr = EmbeddingRetryManager(
            max_retries=config.retry_max,
            delay_ms=config.retry_delay_ms
        )
        self._stop_event = asyncio.Event()
        self._worker_task: asyncio.Task | None = None
        self._last_request_time = 0.0

    async def start(self) -> None:
        """Start the background worker."""
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._worker())
            logger.info("[EmbeddingManager] worker started")

    async def stop(self) -> None:
        """Stop the background worker."""
        self._stop_event.set()
        if self._worker_task:
            # Wake up worker
            self._queue.put_nowait(("", asyncio.Future()))
            await self._worker_task
            self._worker_task = None
            logger.info("[EmbeddingManager] worker stopped")

    async def encode(self, text: str) -> List[float]:
        """Enqueue a single text for embedding and wait for the result."""
        if self._encoder.dim == 0:
            return []
            
        future: asyncio.Future[List[float]] = asyncio.Future()
        await self._queue.put((text, future))
        return await future

    async def _worker(self) -> None:
        """Background worker that processes batches."""
        while not self._stop_event.is_set():
            batch: List[tuple[str, asyncio.Future[List[float]]]] = []
            
            # Wait for the first item
            try:
                item = await self._queue.get()
                if self._stop_event.is_set():
                    break
                batch.append(item)
            except asyncio.CancelledError:
                break

            # Try to fill the batch
            start_time = time.time()
            while len(batch) < self._cfg.batch_size:
                timeout = (self._cfg.batch_interval_ms / 1000.0) - (time.time() - start_time)
                if timeout <= 0:
                    break
                try:
                    item = await asyncio.wait_for(self._queue.get(), timeout=timeout)
                    batch.append(item)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    break

            if not batch:
                continue

            # Process the batch
            texts = [t for t, _ in batch]
            futures = [f for _, f in batch]
            
            async with self._semaphore:
                # Apply request interval
                elapsed = time.time() - self._last_request_time
                wait_time = (self._cfg.request_interval_ms / 1000.0) - elapsed
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                
                try:
                    self._last_request_time = time.time()
                    results = await self._retry_mgr.execute(self._encoder.encode_batch, texts)
                    
                    # Distribute results
                    for i, future in enumerate(futures):
                        if i < len(results):
                            future.set_result(results[i])
                        else:
                            future.set_exception(RuntimeError("Batch result size mismatch"))
                            
                except Exception as exc:
                    # Check failure tolerance
                    logger.error("[EmbeddingManager] batch failed: %s", exc)
                    for future in futures:
                        if not future.done():
                            future.set_exception(exc)
            
            for _ in range(len(batch)):
                self._queue.task_done()
