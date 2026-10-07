"""Thin async client for the TypeSafe System One Choice and Noul APIs.

One POST to ``/v1/systemone`` carries a shared ``state`` and any number of typed
questions that are evaluated in parallel against it. Choice answers select one
declared option; Noul answers return a scalar in ``[0, 1]``.

Failure contract: transient failures (timeouts, connection errors, 429, 529,
5xx) are retried with exponential backoff; 401 disables the client for the rest
of the process; every other failure raises ``TypeSafeError`` immediately.
Neither the API key nor the request body (which carries chat content) is ever
logged.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Mapping

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.typesafe.ai"
DEFAULT_MODEL = "jev-latest"
_ENDPOINT = "/v1/systemone"
_RETRY_AFTER_CAP_SECONDS = 30.0
_ERROR_TEXT_LIMIT = 200


class TypeSafeError(Exception):
    """A TypeSafe request failed; ``retryable`` says whether a later try may work."""

    def __init__(
        self, message: str, *, retryable: bool = False, status: int | None = None
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status = status


class TypeSafeAuthError(TypeSafeError):
    """The API key was rejected (401)."""


@dataclass(frozen=True, slots=True)
class ChoiceAnswer:
    choice: str
    confidence: float


@dataclass(frozen=True, slots=True)
class NoulAnswer:
    value: float


@dataclass(frozen=True, slots=True)
class SystemOneAnswers:
    choices: dict[str, ChoiceAnswer]
    nouls: dict[str, NoulAnswer]


# key -> (instructions, criteria); criteria maps option id -> description.
ChoiceQuestions = Mapping[str, tuple[str, Mapping[str, Any]]]
NoulQuestions = Mapping[str, str]


class TypeSafeClient:
    """Async System One client. Safe for concurrent use from one event loop."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 10.0,
        max_retries: int = 2,
        backoff_seconds: float = 1.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._max_retries = max(0, max_retries)
        self._backoff_seconds = backoff_seconds
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        self._disabled = False

    @property
    def usable(self) -> bool:
        return bool(self._api_key) and not self._disabled

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=self._timeout,
                transport=self._transport,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def choices(
        self, state: str, questions: ChoiceQuestions,
    ) -> dict[str, ChoiceAnswer]:
        """Ask every question against ``state``; return the valid answers by key.

        An answer is dropped (not raised) when its ``choice`` is not one of the
        question's criteria or its confidence is not a number in [0, 1], so a
        partly malformed response still yields the usable part.
        """
        return (await self.ask(state, choices=questions)).choices

    async def ask(
        self,
        state: str,
        *,
        choices: ChoiceQuestions | None = None,
        nouls: NoulQuestions | None = None,
    ) -> SystemOneAnswers:
        """Ask mixed Choice and Noul questions against one shared state."""
        if not self.usable:
            raise TypeSafeError("TypeSafe client is not usable (no key or disabled)")
        choice_questions = choices or {}
        noul_questions = nouls or {}
        overlap = set(choice_questions) & set(noul_questions)
        if overlap:
            raise ValueError(f"duplicate TypeSafe question key: {sorted(overlap)[0]}")
        if not choice_questions and not noul_questions:
            return SystemOneAnswers(choices={}, nouls={})
        request_questions = {
            key: {
                "type": "choice",
                "instructions": instructions,
                "criteria": dict(criteria),
            }
            for key, (instructions, criteria) in choice_questions.items()
        }
        request_questions.update({
            key: {"type": "noul", "instructions": instructions}
            for key, instructions in noul_questions.items()
        })
        body = {"state": state, "model": self._model, "questions": request_questions}
        data = await self._post(body)
        answers = data.get("answers") if isinstance(data, dict) else None
        if not isinstance(answers, dict):
            raise TypeSafeError("TypeSafe response has no 'answers' object")
        choice_result: dict[str, ChoiceAnswer] = {}
        for key, (_, criteria) in choice_questions.items():
            raw = answers.get(key)
            if not isinstance(raw, dict):
                continue
            choice = raw.get("choice")
            confidence = raw.get("confidence")
            if (
                choice not in criteria
                or isinstance(confidence, bool)
                or not isinstance(confidence, (int, float))
                or not 0.0 <= float(confidence) <= 1.0
            ):
                continue
            choice_result[key] = ChoiceAnswer(choice=choice, confidence=float(confidence))
        noul_result: dict[str, NoulAnswer] = {}
        for key in noul_questions:
            raw = answers.get(key)
            if not isinstance(raw, dict):
                continue
            value = raw.get("noul")
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0.0 <= float(value) <= 1.0
            ):
                continue
            noul_result[key] = NoulAnswer(value=float(value))
        return SystemOneAnswers(choices=choice_result, nouls=noul_result)

    async def _post(self, body: dict[str, Any]) -> Any:
        last: TypeSafeError | None = None
        for attempt in range(self._max_retries + 1):
            delay = self._backoff_seconds * (2 ** attempt)
            try:
                response = await self._http().post(_ENDPOINT, json=body)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = TypeSafeError(
                    f"TypeSafe request failed: {type(exc).__name__}", retryable=True
                )
            else:
                status = response.status_code
                if status == 200:
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise TypeSafeError("TypeSafe returned non-JSON body") from exc
                if status == 401:
                    self._disabled = True
                    logger.error(
                        "[TypeSafe] API key rejected (401); disabling classification "
                        "for this process."
                    )
                    raise TypeSafeAuthError("TypeSafe API key rejected", status=status)
                text = response.text[:_ERROR_TEXT_LIMIT]
                if status == 429 or status >= 500:
                    last = TypeSafeError(
                        f"TypeSafe HTTP {status}: {text}", retryable=True, status=status
                    )
                    delay = self._retry_after(response, delay)
                else:
                    raise TypeSafeError(
                        f"TypeSafe HTTP {status}: {text}", status=status
                    )
            if attempt < self._max_retries:
                logger.warning(
                    "[TypeSafe] attempt %d/%d failed (%s); retrying in %.1fs",
                    attempt + 1, self._max_retries + 1, last, delay,
                )
                await asyncio.sleep(delay)
        assert last is not None
        raise last

    @staticmethod
    def _retry_after(response: httpx.Response, default: float) -> float:
        raw = response.headers.get("retry-after")
        if raw is None:
            return default
        try:
            return min(max(float(raw), 0.0), _RETRY_AFTER_CAP_SECONDS)
        except ValueError:
            return default
