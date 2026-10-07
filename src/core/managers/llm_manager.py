"""Shared model concurrency, request pacing and call accounting."""
import asyncio
import contextlib
import heapq
import itertools
import logging
import time
from collections import deque
from typing import Any, Callable, Coroutine, Dict, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

class LLMTaskManager:
    """
    Global LLM task manager for controlling concurrency and managing background tasks.
    
    This manager prevents overwhelming the LLM provider by using a central semaphore
    for all background LLM calls (extraction, synthesis, summary, etc.).
    """
    
    def __init__(self, concurrency: int = 2, request_interval_seconds: float = 0.0):
        if concurrency < 1 or request_interval_seconds < 0:
            raise ValueError("Model concurrency must be positive and request interval nonnegative")
        self._limit = concurrency
        self._in_use = 0
        self._waiters: list[tuple[int, int, asyncio.Future]] = []
        self._waiter_seq = itertools.count()
        self._request_interval = request_interval_seconds
        self._pacing_lock = asyncio.Lock()
        self._next_request = 0.0
        self._active_tasks = 0
        self._total_calls = 0
        self._failed_calls = 0
        self._token_usage: Dict[str, Dict[str, int]] = {} # task_name -> {prompt, completion}
        self._recent_calls = deque(maxlen=50)
        self._call_seq = 0
        self._start_time = time.time()

    def _record_call(
        self,
        *,
        task_name: str,
        success: bool,
        duration: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        error: str | None = None,
    ) -> None:
        self._call_seq += 1
        if error and len(error) > 300:
            error = error[:297] + "..."
        self._recent_calls.append({
            "id": self._call_seq,
            "timestamp": time.time(),
            "task_name": task_name,
            "success": success,
            "duration_ms": round(duration * 1000, 1),
            "prompt_tokens": int(prompt_tokens or 0),
            "completion_tokens": int(completion_tokens or 0),
            "error": error,
        })
        
    async def run(
        self, 
        coro_func: Callable[..., Coroutine[Any, Any, T]], 
        *args, 
        priority: int = 10, 
        task_name: str = "unnamed_task",
        **kwargs
    ) -> T:
        """
        Runs an LLM task with concurrency control.
        
        Args:
            coro_func: The coroutine function to execute (e.g., provider.text_chat).
            *args: Arguments for the coroutine function.
            priority: Task priority (smaller values = higher priority). A free slot goes to the
                waiting task with the smallest priority; equal priorities are served first come, first served.
            task_name: Name of the task for logging/monitoring.
            **kwargs: Keyword arguments for the coroutine function.
            
        Returns:
            The result of the coroutine.
        """
        async with self._slot(priority):
            async with self._pacing_lock:
                while self._next_request > time.monotonic():
                    await asyncio.sleep(self._next_request - time.monotonic())
                self._next_request = time.monotonic() + self._request_interval
            self._active_tasks += 1
            self._total_calls += 1
            start = time.time()
            logger.debug(f"[LLMTaskManager] Starting task '{task_name}' (priority={priority}, active={self._active_tasks})")
            
            try:
                result = await coro_func(*args, **kwargs)
                duration = time.time() - start
                prompt_tokens = 0
                completion_tokens = 0
                
                # Try to extract token usage from ProviderResponse (LLMResponse in AstrBot core)
                try:
                    if hasattr(result, "usage") and result.usage:
                        prompt_tokens = getattr(result.usage, "input", 0)
                        completion_tokens = getattr(result.usage, "output", 0)
                    
                    if prompt_tokens > 0 or completion_tokens > 0:
                        if task_name not in self._token_usage:
                            self._token_usage[task_name] = {"prompt": 0, "completion": 0}
                        self._token_usage[task_name]["prompt"] += prompt_tokens
                        self._token_usage[task_name]["completion"] += completion_tokens
                except Exception as e:
                    logger.debug(f"[LLMTaskManager] Failed to extract token usage for '{task_name}': {e}")

                self._record_call(
                    task_name=task_name,
                    success=True,
                    duration=duration,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
                logger.debug(f"[LLMTaskManager] Task '{task_name}' finished in {duration:.2f}s")
                return result
            except Exception as e:
                duration = time.time() - start
                self._failed_calls += 1
                self._record_call(
                    task_name=task_name,
                    success=False,
                    duration=duration,
                    error=str(e) or repr(e),
                )
                logger.error(f"[LLMTaskManager] Task '{task_name}' failed: {e}")
                raise
            finally:
                self._active_tasks -= 1

    @contextlib.asynccontextmanager
    async def _slot(self, priority: int):
        if self._in_use < self._limit and not self._waiters:
            self._in_use += 1
        else:
            granted = asyncio.get_running_loop().create_future()
            heapq.heappush(self._waiters, (priority, next(self._waiter_seq), granted))
            try:
                await granted
            except asyncio.CancelledError:
                if granted.done() and not granted.cancelled():
                    self._release_slot()
                raise
        try:
            yield
        finally:
            self._release_slot()

    def _release_slot(self) -> None:
        while self._waiters:
            _, _, granted = heapq.heappop(self._waiters)
            if not granted.done():
                granted.set_result(None)
                return
        self._in_use -= 1

    def defer_requests(self, seconds: float) -> None:
        """Share provider cooldown with every queued model task."""
        self._next_request = max(self._next_request, time.monotonic() + seconds)

    def get_stats(self, show_details: bool = False) -> Dict[str, Any]:
        """Returns statistics about the LLM task manager."""
        uptime = time.time() - self._start_time
        total_prompt = sum(u["prompt"] for u in self._token_usage.values())
        total_completion = sum(u["completion"] for u in self._token_usage.values())
        stats = {
            "active_tasks": self._active_tasks,
            "total_calls": self._total_calls,
            "successful_calls": self._total_calls - self._failed_calls,
            "failed_calls": self._failed_calls,
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "token_usage_by_task": self._token_usage,
            "uptime_seconds": uptime,
            "concurrency_limit": self._limit,
        }
        if show_details:
            stats["recent_calls"] = list(reversed(self._recent_calls))
        return stats
