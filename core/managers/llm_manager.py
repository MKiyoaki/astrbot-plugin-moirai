import asyncio
import logging
import time
from collections import deque
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

    def get_token_usage(self) -> Dict[str, Dict[str, int]]:
        """Returns aggregated token usage per task name."""
        return self._token_usage

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
            "concurrency_limit": self._semaphore._value if hasattr(self._semaphore, "_value") else "unknown"
        }
        if show_details:
            stats["recent_calls"] = list(reversed(self._recent_calls))
        return stats
