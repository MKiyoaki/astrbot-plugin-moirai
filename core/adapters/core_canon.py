"""Canon story memory as a Core Generation Protocol v1 participant: a canon prompt block, recall tools and reply review.

All canon reader work, and the model calls the review makes, run on one worker thread, because the reader's sqlite
connection must stay on the thread that opened it. Calls queue behind each other on that thread. Moirai imports no
Core source; the contract is the versioned dictionaries.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from ..canon.assembly import EvidenceSettings
from ..canon.config import CanonPersona
from ..canon.reader import CanonReader
from ..canon.recall import PROBE_TOOL, TURN_BUDGET, present_phrase, recall_tool
from ..canon.turn import ARCHIVE_TOOL, CanonTurn, tier_label

logger = logging.getLogger(__name__)

BLOCK = {"id": "canon", "start": "<!-- EM:CANON:START -->", "end": "<!-- EM:CANON:END -->"}
RETAINED = 256
RETENTION_SECONDS = 900.0
TIMEOUT_SECONDS = 60.0
MAX_TEXT = 32_000
NO_TURN = "这一轮没有可用的回忆。"

Complete = Callable[[list[dict], float], str]


def without_block(text: str) -> str:
    """The host's system prompt with the canon block taken out, as the persona of a repair prompt."""
    start = text.find(BLOCK["start"])
    if start < 0:
        return text.strip()
    end = text.find(BLOCK["end"], start)
    tail = text[end + len(BLOCK["end"]):] if end >= 0 else ""
    return (text[:start].rstrip() + "\n\n" + tail.lstrip()).strip()


def history_of(contexts: object) -> list[dict]:
    """Spoken turns only; tool rounds, injected tool pairs and non-text parts are not part of what was said."""
    return [{"role": item["role"], "content": item["content"]} for item in contexts or []
            if isinstance(item, dict) and item.get("role") in ("user", "assistant")
            and isinstance(item.get("content"), str) and item["content"].strip()]


def tool_specs(reader: CanonReader) -> list[dict]:
    """The terminal's tool schemas in the declaration's shape; the recall tool states the canon's present."""
    specs = [PROBE_TOOL, recall_tool(present_phrase(reader)), *([ARCHIVE_TOOL] if reader.has_archives else [])]
    return [{"name": spec["function"]["name"], "description": spec["function"]["description"],
             "parameters": spec["function"]["parameters"]} for spec in specs]


def is_doctor(persona: CanonPersona, sender: str) -> bool:
    return persona.user_is_doctor == "all" or (persona.user_is_doctor == "bound" and sender in persona.doctor_uids)


def host_complete_for(context, loop: asyncio.AbstractEventLoop) -> Callable[[str], Complete]:
    """Repair calls use the chat provider of the reply's own session, on the host's event loop."""
    def complete_for(session_id: str) -> Complete:
        def complete(messages: list[dict], temperature: float) -> str:
            try:
                provider = context.get_using_provider(umo=session_id)
            except TypeError:
                provider = context.get_using_provider()
            if provider is None:
                raise RuntimeError("No chat provider for the canon review.")
            request = provider.text_chat(prompt=messages[-1]["content"], system_prompt=messages[0]["content"],
                                         contexts=messages[1:-1])
            response = asyncio.run_coroutine_threadsafe(request, loop).result(TIMEOUT_SECONDS)
            return str(getattr(response, "completion_text", "") or "").strip()
        return complete
    return complete_for


class CanonGeneration:
    """One canon database shared by every canon-mapped persona bucket, with one turn per generation attempt."""

    def __init__(self, reader: CanonReader, tools: list[dict], persona_map: dict[str, CanonPersona],
                 pool: ThreadPoolExecutor, complete_for: Callable[[str], Complete], *, top_k: int = 5,
                 evidence_lines: int = 4, token_budget: int = TURN_BUDGET, temperature: float = 0.3,
                 observer: Callable[[dict], None] | None = None) -> None:
        self.reader, self._tools, self.persona_map = reader, tools, persona_map
        self._pool, self._complete_for = pool, complete_for
        self.top_k, self.evidence_lines, self.token_budget = top_k, evidence_lines, token_budget
        self.temperature, self._observer = temperature, observer
        self._turns: OrderedDict[str, tuple[CanonTurn, float]] = OrderedDict()
        self.declared = False

    @classmethod
    async def open(cls, open_reader: Callable[[], CanonReader], persona_map: dict[str, CanonPersona],
                   complete_for: Callable[[str], Complete], **options) -> "CanonGeneration":
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="moirai-canon")
        loop = asyncio.get_running_loop()
        try:
            reader = await loop.run_in_executor(pool, open_reader)
            tools = await loop.run_in_executor(pool, tool_specs, reader)
        except BaseException:
            pool.shutdown(wait=False)
            raise
        return cls(reader, tools, persona_map, pool, complete_for, **options)

    async def _run(self, function: Callable, *args):
        return await asyncio.get_running_loop().run_in_executor(self._pool, function, *args)

    def declaration(self) -> dict:
        """Reading the declaration means the host speaks the protocol; only then is a canon block injected."""
        self.declared = True
        return {"version": "1", "tools": [dict(tool) for tool in self._tools], "review": True,
                "timeout_seconds": TIMEOUT_SECONDS}

    def persona(self, bucket: str | None) -> CanonPersona | None:
        persona = self.persona_map.get(bucket) if bucket else None
        return persona if persona is not None and persona.character == self.reader.character else None

    async def before_generation(self, event: dict, bucket: str) -> list[dict]:
        persona = self.persona(bucket)
        payload = event.get("payload") or {}
        request, message = payload.get("request"), payload.get("message") or {}
        query = str(message.get("text") or "").strip()
        if not self.declared or persona is None or not isinstance(request, dict) or not query:
            return []
        doctor = is_doctor(persona, str(message.get("sender_id") or ""))
        turn, block = await self._run(self._open_turn, query, doctor, request)
        self._keep(event["correlation_id"], turn)
        return [{"kind": "text_block", "block_id": BLOCK["id"], "target": "system_prompt", "position": "after",
                 "text": block}]

    def _open_turn(self, query: str, doctor: bool, request: dict) -> tuple[CanonTurn, str]:
        settings = EvidenceSettings(doctor=doctor, top_k=self.top_k, evidence_lines=self.evidence_lines,
                                    token_budget=self.token_budget)
        turn = CanonTurn(self.reader, settings, query=query, persona="",
                         history=history_of(request.get("contexts")), prompt=str(request.get("prompt") or query))
        turn.start()
        return turn, turn.block()

    def _keep(self, correlation_id: str, turn: CanonTurn) -> None:
        cutoff = time.monotonic() - RETENTION_SECONDS
        for key, (_, created) in tuple(self._turns.items()):
            if created < cutoff:
                self._turns.pop(key, None)
        self._turns[correlation_id] = (turn, time.monotonic())
        while len(self._turns) > RETAINED:
            self._turns.popitem(last=False)

    async def on_generation(self, call: dict, bucket: str) -> dict:
        kind, event = call.get("kind"), call.get("event") or {}
        kept = self._turns.get(event.get("correlation_id"))
        turn = kept[0] if kept and self.persona(bucket) is not None else None
        if kind == "offer":
            tools = [tool["name"] for tool in self._tools] if turn is not None and turn.offer else []
            return {"version": "1", "kind": "offer", "tools": tools, "review": turn is not None}
        if kind == "tool":
            text = NO_TURN if turn is None else await self._run(turn.tool_text, call.get("name", ""),
                                                                 call.get("arguments") or {})
            return {"version": "1", "kind": "tool", "text": text[:MAX_TEXT]}
        if kind != "review":
            raise ValueError("Unsupported generation call.")
        reply = call.get("reply") or ""
        if turn is None:
            return {"version": "1", "kind": "review", "action": "keep"}
        self._turns.pop(event["correlation_id"], None)
        request = (event.get("payload") or {}).get("request") or {}
        complete = self._complete_for(str(event.get("session_id") or ""))
        answer, summary = await self._run(self._finish, turn, reply, request, complete)
        if self._observer is not None:
            try:
                self._observer({"correlation_id": event["correlation_id"], **summary})
            except Exception:
                logger.warning("[Moirai] canon observer failed", exc_info=True)
        if answer == reply or not answer.strip():
            return {"version": "1", "kind": "review", "action": "keep"}
        return {"version": "1", "kind": "review", "action": "replace", "text": answer[:MAX_TEXT]}

    def _finish(self, turn: CanonTurn, reply: str, request: dict, complete: Complete) -> tuple[str, dict]:
        turn.persona = without_block(str(request.get("system_prompt") or ""))
        turn.prompt = str(request.get("prompt") or turn.query)
        turn.history = history_of(request.get("contexts"))
        settled, calls = turn.settle(reply, complete, self.temperature)
        answer, report = turn.check(settled, complete, self.temperature)
        items = list(turn.pack.items)
        return answer, {
            "tier": tier_label(turn.recall.log), "task": turn.task, "tools": list(turn.tool_queries),
            "recalls": list(turn.recall.log), "executed": turn.executed,
            "evidence": [{"eid": item.eid, "event_id": item.event_id, "channel": item.channel} for item in items],
            "evidence_text": turn.pack.render() if items else "", "draft": turn.draft, "outline": turn.outline,
            "problems": {str(index): reason for index, reason in sorted(report.problems.items())},
            "review_calls": calls + report.calls, "answer": answer,
        }

    def close(self) -> None:
        try:
            self._pool.submit(self.reader.close).result()
        finally:
            self._pool.shutdown()
            self._turns.clear()
