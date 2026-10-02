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


async def retry_model_call(factory, *, task_name: str, strict: bool = False,
                           max_retries: int = 0, minimum: float = 2.0,
                           timeout: float | None = None, manager=None, validate=None):
    attempt = 0
    while True:
        try:
            async def request():
                if timeout is None:
                    return await factory()
                return await asyncio.wait_for(factory(), timeout)
            result = await manager.run(request, task_name=task_name) if manager else await request()
            if validate is not None:
                validate(result)
            return result, attempt
        except Exception as exc:
            if strict and not retryable(exc):
                raise
            if not strict and attempt >= max_retries:
                raise
            delay = retry_delay(exc, attempt, minimum)
            logger.warning("[ModelRetry] task=%s attempt=%d retry_in=%.2fs reason=%s error=%s",
                           task_name, attempt + 1, delay, type(exc).__name__, str(exc) or repr(exc))
            if manager and hasattr(manager, "defer_requests"):
                manager.defer_requests(delay)
            await asyncio.sleep(delay)
            attempt += 1


async def model_response(provider, manager, cfg, *, prompt: str, system_prompt: str,
                         task_name: str, validate=None):
    response, _ = await retry_model_call(
        lambda: provider.text_chat(prompt=prompt, system_prompt=system_prompt),
        task_name=task_name, strict=cfg.retry_until_success,
        minimum=max(2.0, cfg.retry_delay_seconds), timeout=cfg.llm_timeout,
        manager=manager, validate=validate if cfg.retry_until_success else None,
    )
    return response
