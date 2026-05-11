"""Big Five personality scorer — pluggable interface.

Primary path (LLMBigFiveScorer): accumulates messages per user per session,
then calls the LLM once every `x_messages` to get [O, C, E, A, N] scores.

The BigFiveScorer Protocol is the public interface; future implementations
(e.g. BERTBigFiveScorer) can replace LLMBigFiveScorer without touching
the rest of the pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable, Protocol, runtime_checkable

from ..domain.models import BigFiveVector

logger = logging.getLogger(__name__)

_DEFAULT_SYSTEM_PROMPT = (
    "你是一个人格分析助手。根据以下对话文本，评估发言者在大五人格各维度上的倾向。"
    "只输出单行JSON，字段：O（开放性）、C（尽责性）、E（外倾性）、A（宜人性）、N（神经质），"
    "各维度范围 -1.0（低）到 1.0（高）的浮点数。不要输出任何其他内容。"
    "\n示例：{\"O\": 0.3, \"C\": -0.1, \"E\": 0.7, \"A\": 0.5, \"N\": -0.2}"
)

_ZERO_VECTOR = BigFiveVector(
    openness=0.0, conscientiousness=0.0, extraversion=0.0,
    agreeableness=0.0, neuroticism=0.0,
)


def _safe_parse(text: str) -> dict | None:
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        return None


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


@runtime_checkable
class BigFiveScorer(Protocol):
    """Replaceable interface for Big Five personality scoring.

    Implementations: LLMBigFiveScorer (default), BERTBigFiveScorer (future).
    """

    async def score(self, context: str, provider_getter: Callable) -> BigFiveVector:
        """Score a block of conversation text, returning Big Five trait values."""
        ...


class LLMBigFiveScorer:
    """Approach A: single LLM call per scoring trigger → [O, C, E, A, N].

    Falls back to _ZERO_VECTOR (neutral) on LLM timeout or parse failure so
    the caller never has to handle exceptions.
    """

    def __init__(
        self,
        system_prompt: str = _DEFAULT_SYSTEM_PROMPT,
        llm_timeout: float = 30.0,
    ) -> None:
        self._system_prompt = system_prompt
        self._llm_timeout = llm_timeout

    async def score(self, context: str, provider_getter: Callable) -> BigFiveVector:
        provider = provider_getter()
        if provider is None:
            return _ZERO_VECTOR
        try:
            resp = await asyncio.wait_for(
                provider.text_chat(prompt=context, system_prompt=self._system_prompt),
                timeout=self._llm_timeout,
            )
            parsed = _safe_parse(resp.completion_text)
            if parsed is None:
                logger.warning("[BigFiveScorer] unparseable LLM response")
                return _ZERO_VECTOR
            return BigFiveVector(
                openness=_clamp(float(parsed.get("O", 0.0))),
                conscientiousness=_clamp(float(parsed.get("C", 0.0))),
                extraversion=_clamp(float(parsed.get("E", 0.0))),
                agreeableness=_clamp(float(parsed.get("A", 0.0))),
                neuroticism=_clamp(float(parsed.get("N", 0.0))),
            )
        except asyncio.TimeoutError:
            logger.warning("[BigFiveScorer] LLM timeout, using neutral vector")
            return _ZERO_VECTOR
        except Exception as exc:
            logger.warning("[BigFiveScorer] scoring failed: %s", exc)
            return _ZERO_VECTOR


class BigFiveBuffer:
    """Per-session per-user message accumulator + cached BigFiveVector.

    Call `add_message(uid, text)` on every incoming message.
    When `count(uid) >= x_messages`, `maybe_score()` fires an async
    background LLM call and resets the counter for that uid.

    The cached vector persists until the next scoring trigger, so
    SocialOrientationAnalyzer can always read a recent (if slightly stale)
    estimate even for users below the threshold.
    """

    def __init__(
        self,
        x_messages: int = 10,
        scorer: BigFiveScorer | None = None,
        llm_timeout: float = 30.0,
    ) -> None:
        self._x = max(1, x_messages)
        self._scorer: BigFiveScorer = scorer or LLMBigFiveScorer(llm_timeout=llm_timeout)
        # Cap text accumulation at 2× threshold to prevent unbounded memory growth.
        self._max_texts = self._x * 2
        # uid → (message_count_since_last_score, accumulated_texts, cached_vector)
        self._counters: dict[str, int] = {}
        self._texts: dict[str, list[str]] = {}
        self._cache: dict[str, BigFiveVector] = {}
        self._evidence: dict[str, str] = {}
        self._pending_tasks: dict[str, asyncio.Task] = {}

    def add_message(self, uid: str, text: str) -> None:
        self._counters[uid] = self._counters.get(uid, 0) + 1
        buf = self._texts.setdefault(uid, [])
        buf.append(text)
        if len(buf) > self._max_texts:
            del buf[: len(buf) - self._max_texts]

    def get_cached(self, uid: str) -> BigFiveVector:
        return self._cache.get(uid, _ZERO_VECTOR)

    def get_evidence(self, uid: str) -> str | None:
        return self._evidence.get(uid)

    def count(self, uid: str) -> int:
        return self._counters.get(uid, 0)

    def maybe_score(self, uid: str, provider_getter: Callable) -> asyncio.Task | None:
        """Fire a background scoring task if the uid has reached the threshold.
        Returns the existing task if one is already running for this uid.
        """
        if uid in self._pending_tasks:
            return self._pending_tasks[uid]

        if self._counters.get(uid, 0) < self._x:
            return None

        context = "\n".join(self._texts.get(uid, [])[-self._x :])
        self._counters[uid] = 0
        self._texts[uid] = []
        
        task = asyncio.create_task(self._run_score(uid, context, provider_getter))
        self._pending_tasks[uid] = task
        return task

    async def _run_score(
        self, uid: str, context: str, provider_getter: Callable
    ) -> None:
        try:
            vector = await self._scorer.score(context, provider_getter)
            self._cache[uid] = vector
            logger.debug("[BigFiveBuffer] scored uid=%s → %s", uid[:8], vector)
        finally:
            self._pending_tasks.pop(uid, None)

    def evict(self, uid: str) -> None:
        """Remove all state for a uid (called when session expires)."""
        self._counters.pop(uid, None)
        self._texts.pop(uid, None)
        self._cache.pop(uid, None)
        self._evidence.pop(uid, None)

    def evict_session(self, uids: list[str]) -> None:
        for uid in uids:
            self.evict(uid)
