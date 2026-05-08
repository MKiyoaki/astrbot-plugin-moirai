"""Tests for Phase 8: TaskScheduler, decay, synthesis, aggregation, summary."""
from __future__ import annotations

import asyncio
import dataclasses
import time
from pathlib import Path

import pytest

from core.domain.models import Event, Impression, Persona
from core.repository.memory import (
    InMemoryEventRepository,
    InMemoryImpressionRepository,
    InMemoryPersonaRepository,
)
from core.tasks.decay import run_salience_decay
from core.tasks.scheduler import TaskScheduler
from core.tasks.summary import run_group_summary
from core.tasks.synthesis import run_impression_aggregation, run_persona_synthesis
from core.config import DecayConfig


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

class _MockResponse:
    def __init__(self, text: str) -> None:
        self.completion_text = text


class _MockProvider:
    def __init__(self, response: str) -> None:
        self._response = response
        self.calls: list[str] = []

    async def text_chat(self, prompt: str = "", system_prompt: str = "") -> _MockResponse:
        self.calls.append(prompt)
        return _MockResponse(self._response)


def make_persona(uid: str, name: str = "Alice") -> Persona:
    return Persona(
        uid=uid,
        bound_identities=[("qq", "123")],
        primary_name=name,
        persona_attrs={"affect_type": "中性"},
        confidence=0.8,
        created_at=1000.0,
        last_active_at=2000.0,
    )


def make_event(event_id: str, topic: str = "test", uid: str = "u1", group_id: str | None = "g1") -> Event:
    return Event(
        event_id=event_id,
        group_id=group_id,
        start_time=1000.0,
        end_time=1010.0,
        participants=[uid],
        interaction_flow=[],
        topic=topic,
        chat_content_tags=[],
        salience=0.5,
        confidence=0.8,
        inherit_from=[],
        last_accessed_at=1010.0,
    )


def make_impression(observer: str, subject: str, evidence: list[str] | None = None) -> Impression:
    return Impression(
        observer_uid=observer,
        subject_uid=subject,
        ipc_orientation="友好",
        benevolence=0.0,
        power=0.0,
        affect_intensity=0.3,
        r_squared=0.5,
        confidence=0.5,
        scope="global",
        evidence_event_ids=evidence or [],
        last_reinforced_at=1000.0,
    )


# ---------------------------------------------------------------------------
# TaskScheduler
# ---------------------------------------------------------------------------

async def test_scheduler_register_and_list_tasks() -> None:
    s = TaskScheduler()
    s.register("task_a", interval=3600, fn=lambda: asyncio.sleep(0))
    s.register("task_b", interval=7200, fn=lambda: asyncio.sleep(0))
    assert s.task_names == ["task_a", "task_b"]


async def test_scheduler_run_now_executes_task() -> None:
    ran: list[bool] = []

    async def my_task() -> None:
        ran.append(True)

    s = TaskScheduler()
    s.register("test", interval=9999, fn=my_task)
    result = await s.run_now("test")
    assert result is True
    assert ran == [True]


async def test_scheduler_run_now_unknown_returns_false() -> None:
    s = TaskScheduler()
    assert await s.run_now("nonexistent") is False


async def test_scheduler_swallows_task_exception() -> None:
    async def bad_task() -> None:
        raise RuntimeError("intentional error")

    s = TaskScheduler()
    s.register("bad", interval=9999, fn=bad_task)
    # Should not raise
    await s.run_now("bad")


async def test_scheduler_updates_last_run_after_success() -> None:
    before = time.time()

    async def my_task() -> None:
        pass

    s = TaskScheduler()
    s.register("t", interval=9999, fn=my_task)
    await s.run_now("t")
    assert s._tasks[0].last_run >= before


async def test_scheduler_start_stop() -> None:
    s = TaskScheduler(tick_seconds=0.05)
    s.register("noop", interval=9999, fn=lambda: asyncio.sleep(0))
    await s.start()
    assert s._handle is not None
    await s.stop()
    assert s._handle is None


async def test_scheduler_does_not_rerun_before_interval() -> None:
    run_count = [0]

    async def my_task() -> None:
        run_count[0] += 1

    s = TaskScheduler(tick_seconds=0.01)
    s.register("counted", interval=9999, fn=my_task)

    # Force first run, set last_run to now
    await s.run_now("counted")
    count_after_first = run_count[0]

    # Start loop briefly — should NOT fire again (interval not elapsed)
    await s.start()
    await asyncio.sleep(0.05)
    await s.stop()

    assert run_count[0] == count_after_first


# ---------------------------------------------------------------------------
# Salience decay
# ---------------------------------------------------------------------------

async def test_decay_reduces_salience() -> None:
    er = InMemoryEventRepository()
    await er.upsert(make_event("e1"))
    await run_salience_decay(er, decay_config=DecayConfig(lambda_=0.5))
    event = await er.get("e1")
    assert event is not None
    assert event.salience < 0.5


async def test_decay_returns_count() -> None:
    er = InMemoryEventRepository()
    await er.upsert(make_event("e1"))
    await er.upsert(make_event("e2"))
    count = await run_salience_decay(er)
    assert count == 2


async def test_decay_lambda_zero_no_change() -> None:
    er = InMemoryEventRepository()
    await er.upsert(make_event("e1"))
    await run_salience_decay(er, decay_config=DecayConfig(lambda_=0.0))
    event = await er.get("e1")
    assert event is not None
    assert abs(event.salience - 0.5) < 1e-9


# ---------------------------------------------------------------------------
# list_group_ids
# ---------------------------------------------------------------------------

async def test_list_group_ids_returns_unique_groups() -> None:
    er = InMemoryEventRepository()
    await er.upsert(make_event("e1", group_id="g1"))
    await er.upsert(make_event("e2", group_id="g1"))
    await er.upsert(make_event("e3", group_id="g2"))
    await er.upsert(make_event("e4", group_id=None))
    ids = await er.list_group_ids()
    assert set(ids) == {"g1", "g2", None}


async def test_list_group_ids_empty_repo() -> None:
    er = InMemoryEventRepository()
    assert await er.list_group_ids() == []


# ---------------------------------------------------------------------------
# Persona synthesis
# ---------------------------------------------------------------------------

async def test_persona_synthesis_no_provider_returns_zero() -> None:
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    await pr.upsert(make_persona("u1"))
    count = await run_persona_synthesis(pr, er, provider_getter=lambda: None)
    assert count == 0


async def test_persona_synthesis_skips_persona_with_no_events() -> None:
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    await pr.upsert(make_persona("u1"))
    provider = _MockProvider('{"description":"test","affect_type":"积极","content_tags":[]}')
    count = await run_persona_synthesis(pr, er, provider_getter=lambda: provider)
    assert count == 0
    assert provider.calls == []


async def test_persona_synthesis_updates_attrs() -> None:
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    await pr.upsert(make_persona("u1", "Alice"))
    await er.upsert(make_event("ev1", topic="Python开发", uid="u1"))
    provider = _MockProvider(
        '{"description":"热爱编程的开发者","affect_type":"积极","content_tags":["编程","Python"]}'
    )
    count = await run_persona_synthesis(pr, er, provider_getter=lambda: provider)
    assert count == 1
    updated = await pr.get("u1")
    assert updated is not None
    assert updated.persona_attrs.get("description") == "热爱编程的开发者"
    assert updated.persona_attrs.get("affect_type") == "积极"


async def test_persona_synthesis_handles_parse_failure() -> None:
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    await pr.upsert(make_persona("u1"))
    await er.upsert(make_event("ev1", uid="u1"))
    provider = _MockProvider("这不是JSON")
    count = await run_persona_synthesis(pr, er, provider_getter=lambda: provider)
    assert count == 0


async def test_persona_synthesis_truncates_description() -> None:
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    await pr.upsert(make_persona("u1"))
    await er.upsert(make_event("ev1", uid="u1"))
    long_desc = "x" * 100
    provider = _MockProvider(f'{{"description":"{long_desc}","affect_type":"中性","content_tags":[]}}')
    await run_persona_synthesis(pr, er, provider_getter=lambda: provider)
    updated = await pr.get("u1")
    assert updated is not None
    assert len(updated.persona_attrs.get("description", "")) <= 50


# ---------------------------------------------------------------------------
# Impression aggregation
# ---------------------------------------------------------------------------

async def test_impression_aggregation_no_provider_returns_zero() -> None:
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()
    await pr.upsert(make_persona("u1"))
    await ir.upsert(make_impression("u1", "u2", evidence=["ev1"]))
    count = await run_impression_aggregation(pr, er, ir, provider_getter=lambda: None)
    assert count == 0


async def test_impression_aggregation_skips_no_evidence() -> None:
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()
    await pr.upsert(make_persona("u1"))
    await ir.upsert(make_impression("u1", "u2", evidence=[]))
    provider = _MockProvider('{"ipc_orientation":"友好","benevolence":0.8,"power":0.0,"affect_intensity":0.9,"r_squared":0.7,"confidence":0.7}')
    count = await run_impression_aggregation(pr, er, ir, provider_getter=lambda: provider)
    assert count == 0
    assert provider.calls == []


async def test_impression_aggregation_updates_impression() -> None:
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()
    await pr.upsert(make_persona("u1"))
    await er.upsert(make_event("ev1", topic="合作项目", uid="u1"))
    await ir.upsert(make_impression("u1", "u2", evidence=["ev1"]))
    provider = _MockProvider('{"ipc_orientation":"主导友好","benevolence":0.6,"power":0.4,"affect_intensity":0.8,"r_squared":0.75,"confidence":0.75}')
    count = await run_impression_aggregation(pr, er, ir, provider_getter=lambda: provider)
    assert count == 1
    updated = await ir.get("u1", "u2", "global")
    assert updated is not None
    assert updated.ipc_orientation == "主导友好"
    assert abs(updated.benevolence - 0.6) < 0.01


async def test_impression_aggregation_rejects_invalid_relation() -> None:
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()
    await pr.upsert(make_persona("u1"))
    await er.upsert(make_event("ev1", uid="u1"))
    await ir.upsert(make_impression("u1", "u2", evidence=["ev1"]))
    provider = _MockProvider('{"ipc_orientation":"INVALID","benevolence":0.5,"power":0.0,"affect_intensity":0.5,"r_squared":0.5,"confidence":0.5}')
    await run_impression_aggregation(pr, er, ir, provider_getter=lambda: provider)
    updated = await ir.get("u1", "u2", "global")
    assert updated is not None
    assert updated.ipc_orientation == "友好"  # original unchanged


async def test_impression_aggregation_clamps_affect() -> None:
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()
    await pr.upsert(make_persona("u1"))
    await er.upsert(make_event("ev1", uid="u1"))
    await ir.upsert(make_impression("u1", "u2", evidence=["ev1"]))
    provider = _MockProvider('{"ipc_orientation":"友好","benevolence":99.0,"power":99.0,"affect_intensity":99.0,"r_squared":99.0,"confidence":99.0}')
    await run_impression_aggregation(pr, er, ir, provider_getter=lambda: provider)
    updated = await ir.get("u1", "u2", "global")
    assert updated is not None
    assert updated.benevolence <= 1.0
    assert updated.affect_intensity <= 1.0
    assert updated.confidence <= 1.0


# ---------------------------------------------------------------------------
# Group summary
# ---------------------------------------------------------------------------

async def test_group_summary_no_provider_returns_zero(tmp_path: Path) -> None:
    er = InMemoryEventRepository()
    await er.upsert(make_event("ev1", group_id="g1"))
    count = await run_group_summary(er, tmp_path, provider_getter=lambda: None)
    assert count == 0


async def test_group_summary_writes_file(tmp_path: Path) -> None:
    er = InMemoryEventRepository()
    await er.upsert(make_event("ev1", topic="Python讨论", group_id="g1"))
    provider = _MockProvider("## 本期主要话题\n- Python讨论\n")
    count = await run_group_summary(er, tmp_path, provider_getter=lambda: provider)
    assert count == 1
    summaries = list((tmp_path / "groups" / "g1" / "summaries").glob("*.md"))
    assert len(summaries) == 1
    assert "Python讨论" in summaries[0].read_text(encoding="utf-8")


async def test_group_summary_skips_empty_group(tmp_path: Path) -> None:
    er = InMemoryEventRepository()
    # No events inserted
    provider = _MockProvider("summary content")
    count = await run_group_summary(er, tmp_path, provider_getter=lambda: provider)
    assert count == 0
    assert provider.calls == []


async def test_group_summary_private_chat_goes_to_global(tmp_path: Path) -> None:
    er = InMemoryEventRepository()
    await er.upsert(make_event("ev1", topic="私聊内容", group_id=None))
    provider = _MockProvider("## 私聊摘要\n")
    await run_group_summary(er, tmp_path, provider_getter=lambda: provider)
    summaries = list((tmp_path / "global" / "summaries").glob("*.md"))
    assert len(summaries) == 1


async def test_group_summary_multiple_groups(tmp_path: Path) -> None:
    er = InMemoryEventRepository()
    await er.upsert(make_event("ev1", group_id="g1"))
    await er.upsert(make_event("ev2", group_id="g2"))
    provider = _MockProvider("摘要内容")
    count = await run_group_summary(er, tmp_path, provider_getter=lambda: provider)
    assert count == 2
