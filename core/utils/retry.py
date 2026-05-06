"""Retry abstraction for asynchronous operations."""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, TypeVar, Generic

T = TypeVar("T")
logger = logging.getLogger(__name__)


class BaseRetryManager(ABC, Generic[T]):
    """Abstract base class for retryable operations."""

    def __init__(self, max_retries: int = 3, delay_ms: int = 1000, backoff_factor: float = 2.0) -> None:
        self.max_retries = max_retries
        self.delay_ms = delay_ms
        self.backoff_factor = backoff_factor

    async def execute(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> T:
        """Execute the function with retries."""
        last_exc = None
        current_delay = self.delay_ms / 1000.0

        for attempt in range(self.max_retries + 1):
            try:
                return await self._run(func, *args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    logger.warning(
                        "[RetryManager] Attempt %d failed: %s. Retrying in %.2fs...",
                        attempt + 1, exc, current_delay
                    )
                    await asyncio.sleep(current_delay)
                    current_delay *= self.backoff_factor
                else:
                    logger.error("[RetryManager] All %d attempts failed. Last error: %s", self.max_retries + 1, exc)
        
        if last_exc:
            raise last_exc
        raise RuntimeError("Retry loop exited without result or exception")

    @abstractmethod
    async def _run(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> T:
        """Internal execution logic (can be overridden to add specific handling)."""
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        return func(*args, **kwargs)
