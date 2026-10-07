"""一次模型调用加解析与校验的抽取步骤：失败就重试，子类决定下一次的提示、等待多久、怎样解析回复。"""
from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Generic, TypeVar

T = TypeVar("T")
Call = Callable[[str, str], Awaitable[Any]]


@dataclass
class Reply(Generic[T]):
    value: T | None
    errors: list[str] = field(default_factory=list)


@dataclass
class StageResult(Generic[T]):
    value: T | None
    attempts: int
    error: str | None


class JsonStage(ABC, Generic[T]):
    """Retry one prompt until parse() accepts the reply; a failed call and a rejected reply each use one attempt.

    Every exception from the call is retried, as both extraction loops did before they shared this class.
    """

    max_attempts: int
    timeout: float | None = None

    def __init__(self, call: Call) -> None:
        self.call = call

    @property
    @abstractmethod
    def system_prompt(self) -> str: ...

    @abstractmethod
    def parse(self, resp: Any) -> Reply[T]: ...

    def next_prompt(self, prompt: str, errors: list[str]) -> str:
        return prompt

    def call_failed(self, exc: Exception) -> str:
        return f"{type(exc).__name__}: {exc}"

    def backoff(self, attempt: int) -> float:
        return 0.0

    def on_call_failed(self, attempt: int, seconds: float, message: str) -> None:
        return None

    def on_reply(self, attempt: int, seconds: float, resp: Any, reply: Reply[T]) -> None:
        return None

    async def run(self, prompt: str) -> StageResult[T]:
        errors: list[str] = []
        last: str | None = None
        for attempt in range(1, self.max_attempts + 1):
            started = time.monotonic()
            try:
                request = self.call(self.next_prompt(prompt, errors), self.system_prompt)
                resp = await (request if self.timeout is None else asyncio.wait_for(request, self.timeout))
            except Exception as exc:
                errors = []
                last = self.call_failed(exc)
                self.on_call_failed(attempt, time.monotonic() - started, last)
                delay = self.backoff(attempt) if attempt < self.max_attempts else 0.0
                if delay:
                    await asyncio.sleep(delay)
                continue
            seconds = time.monotonic() - started
            reply = self.parse(resp)
            self.on_reply(attempt, seconds, resp, reply)
            if not reply.errors:
                return StageResult(reply.value, attempt, None)
            errors = reply.errors
            last = "；".join(errors)
        return StageResult(None, self.max_attempts, last)
