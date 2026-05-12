import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, Dict, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

class LLMTaskManager:
    """
    Global LLM task manager for controlling concurrency and managing background tasks.
    
    This manager prevents overwhelming the LLM provider by using a central semaphore
    for all background LLM calls (extraction, synthesis, summary, etc.).
    """
    
    def __init__(self, concurrency: int = 2):
        self._semaphore = asyncio.Semaphore(concurrency)
        self._active_tasks = 0
        self._total_calls = 0
        self._failed_calls = 0
        self._start_time = time.time()
        
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
            priority: Task priority (smaller values = higher priority). Currently used for logging.
            task_name: Name of the task for logging/monitoring.
            **kwargs: Keyword arguments for the coroutine function.
            
        Returns:
            The result of the coroutine.
        """
        async with self._semaphore:
            self._active_tasks += 1
            self._total_calls += 1
            start = time.time()
            logger.debug(f"[LLMTaskManager] Starting task '{task_name}' (priority={priority}, active={self._active_tasks})")
            
            try:
                result = await coro_func(*args, **kwargs)
                duration = time.time() - start
                logger.debug(f"[LLMTaskManager] Task '{task_name}' finished in {duration:.2f}s")
                return result
            except Exception as e:
                self._failed_calls += 1
                logger.error(f"[LLMTaskManager] Task '{task_name}' failed: {e}")
                raise
            finally:
                self._active_tasks -= 1

    def get_stats(self) -> Dict[str, Any]:
        """Returns statistics about the LLM task manager."""
        uptime = time.time() - self._start_time
        return {
            "active_tasks": self._active_tasks,
            "total_calls": self._total_calls,
            "failed_calls": self._failed_calls,
            "uptime_seconds": uptime,
            "concurrency_limit": self._semaphore._value if hasattr(self._semaphore, "_value") else "unknown"
        }
