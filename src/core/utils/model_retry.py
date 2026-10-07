"""Cancellable model retries that preserve strict-build quality across transient failures."""
from __future__ import annotations

import asyncio
import logging
import math
import time
from email.utils import parsedate_to_datetime

import httpx

logger = logging.getLogger(__name__)


class ModelOutputError(ValueError):
    """A model answered without a usable result; retry the original operation."""


def retryable(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (408, 409, 425, 429) or exc.response.status_code >= 500
    marker = getattr(exc, "retryable", None)
    if marker is not None:
        return bool(marker)
    return isinstance(exc, (TimeoutError, httpx.TransportError, ModelOutputError, ConnectionError))


def retry_after(value: str | None) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        try:
            seconds = parsedate_to_datetime(value).timestamp() - time.time()
        except (TypeError, ValueError, OverflowError):
            return 0.0
    return max(0.0, seconds) if math.isfinite(seconds) else 0.0


def retry_delay(exc: Exception, attempt: int, minimum: float = 2.0) -> float:
    response = getattr(exc, "response", None)
    server_delay = retry_after(response.headers.get("retry-after")) if response is not None else 0.0
    server_delay = max(server_delay, getattr(exc, "retry_after", 0.0) or 0.0)
    return max(minimum, min(minimum * 2 ** min(attempt, 6), 60.0), server_delay)


STUCK_EVERY = 8
STUCK_SECONDS = 300.0


async def retry_model_call(factory, *, task_name: str, strict: bool = False,
                           max_retries: int = 0, minimum: float = 2.0,
                           timeout: float | None = None, manager=None, validate=None,
                           timeout_growth: float = 1.5, timeout_cap: float = 300.0, priority: int = 10):
    """Retry a model call; each timeout widens the next attempt's limit up to ``timeout_cap``.

    In strict mode a retryable failure is retried until it succeeds, so a request that always needs more
    than the first limit still finishes; a request still failing after ``STUCK_EVERY`` attempts or
    ``STUCK_SECONDS`` of attempts and retry delays is reported loudly in the log without falling back.
    Time spent queued for a shared model slot is not counted, so a backlog alone never looks stuck.
    """
    attempt, limit, spent, reported = 0, timeout, 0.0, False
    while True:
        try:
            async def request(limit=limit):
                nonlocal spent
                began = time.monotonic()
                try:
                    if limit is None:
                        return await factory()
                    return await asyncio.wait_for(factory(), limit)
                finally:
                    spent += time.monotonic() - began
            result = await manager.run(request, task_name=task_name, priority=priority) if manager else await request()
            if validate is not None:
                validate(result)
            return result, attempt
        except Exception as exc:
            if strict and not retryable(exc):
                raise
            if not strict and attempt >= max_retries:
                raise
            delay = retry_delay(exc, attempt, minimum)
            logger.warning("[ModelRetry] task=%s attempt=%d retry_in=%.2fs timeout=%s reason=%s error=%s",
                           task_name, attempt + 1, delay, limit, type(exc).__name__, str(exc) or repr(exc))
            if limit is not None and isinstance(exc, (TimeoutError, asyncio.TimeoutError)) and limit < timeout_cap:
                limit = min(timeout_cap, limit * max(1.0, timeout_growth))
            attempt += 1
            if attempt % STUCK_EVERY == 0 or (spent >= STUCK_SECONDS and not reported):
                reported = reported or spent >= STUCK_SECONDS
                logger.warning("[ModelRetry] STILL RETRYING task=%s attempts=%d retrying_for=%.0fs next_timeout=%s last=%s",
                               task_name, attempt, spent, limit, type(exc).__name__)
            if manager and hasattr(manager, "defer_requests"):
                manager.defer_requests(delay)
            await asyncio.sleep(delay)
            spent += delay


async def model_response(provider, manager, cfg, *, prompt: str, system_prompt: str,
                         task_name: str, validate=None):
    response, _ = await retry_model_call(
        lambda: provider.text_chat(prompt=prompt, system_prompt=system_prompt),
        task_name=task_name, strict=cfg.retry_until_success,
        minimum=max(2.0, cfg.retry_delay_seconds), timeout=cfg.llm_timeout,
        manager=manager, validate=validate if cfg.retry_until_success else None,
    )
    return response
