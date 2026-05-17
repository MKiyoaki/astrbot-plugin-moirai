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
from core.tasks.synthesis import run_impression_recalculation, run_persona_synthesis
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
        persona_attrs={"description": "test user"},
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
        summary="test summary",
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
        ipc_orientation="affinity",
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

async def test_scheduler_sync_fn_raises_type_error(caplog) -> None:
    """Regression: registering a sync fn that returns int causes TypeError on await.

    This reproduces the original context_cleanup bug where cleanup_expired()
    returned int and the scheduler tried to await it.  The scheduler catches the
    exception internally but logs it — we verify the error is recorded.
    """
    import logging

    def sync_returns_int() -> int:
        return 42

    s = TaskScheduler()
    s.register("bad", interval=9999, fn=sync_returns_int)  # type: ignore[arg-type]
    with caplog.at_level(logging.ERROR, logger="core.tasks.scheduler"):
        await s.run_now("bad")
    assert any("bad" in r.message and "int" in r.message for r in caplog.records)


async def test_scheduler_async_wrapper_around_sync_fn_works() -> None:
    """Fix verification: wrapping a sync fn in async def avoids TypeError."""
    side_effects: list[int] = []

    def sync_cleanup() -> int:
        side_effects.append(1)
        return len(side_effects)

    async def cleanup_wrapper() -> None:
        sync_cleanup()

    s = TaskScheduler()
    s.register("cleanup", interval=9999, fn=cleanup_wrapper)
    await s.run_now("cleanup")
    assert side_effects == [1]


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
    provider = _MockProvider('{"description":"test","big_five":{"O":0.5},"content_tags":[]}')
    count = await run_persona_synthesis(pr, er, provider_getter=lambda: provider)
    assert count == 0
    assert provider.calls == []


async def test_persona_synthesis_updates_attrs() -> None:
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    await pr.upsert(make_persona("u1", "Alice"))
    await er.upsert(make_event("ev1", topic="Python开发", uid="u1"))
    provider = _MockProvider(
        '{"description":"热爱编程的开发者","big_five":{"O":0.6,"E":0.4,"N":-0.2}}'
    )
    count = await run_persona_synthesis(pr, er, provider_getter=lambda: provider)
    assert count == 1
    updated = await pr.get("u1")
    assert updated is not None
    assert updated.persona_attrs.get("description") == "热爱编程的开发者"
    bf = updated.persona_attrs.get("big_five", {})
    assert abs(bf.get("O", 0) - 0.6) < 0.01
    assert abs(bf.get("E", 0) - 0.4) < 0.01


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
    provider = _MockProvider(f'{{"description":"{long_desc}","big_five":{{"O":0.1}}}}')
    await run_persona_synthesis(pr, er, provider_getter=lambda: provider)
    updated = await pr.get("u1")
    assert updated is not None
    assert len(updated.persona_attrs.get("description", "")) <= 80


async def test_persona_synthesis_stores_big_five_evidence_dict() -> None:
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    await pr.upsert(make_persona("u1", "Alice"))
    await er.upsert(make_event("ev1", topic="技术讨论", uid="u1"))
    # LLM returns O=0.7 → pct = round((0.7+1)/2*100) = 85
    provider = _MockProvider(
        '{"description":"技术爱好者","big_five":{"O":0.7},'
        '"big_five_evidence":{"O":"Alice 在开放性上表现出高水平，可以推断出 85% 的量化结果。"}}'
    )
    from core.config import SynthesisConfig
    await run_persona_synthesis(pr, er, provider_getter=lambda: provider,
                                synthesis_config=SynthesisConfig(ema_alpha=1.0))  # no blending
    updated = await pr.get("u1")
    assert updated is not None
    evidence = updated.persona_attrs.get("big_five_evidence")
    assert isinstance(evidence, dict)
    assert "O" in evidence
    assert "85%" in evidence["O"]
    assert len(evidence["O"]) <= 120


async def test_persona_synthesis_evidence_pct_matches_merged_score() -> None:
    """Evidence sentence percentage must reflect the EMA-merged score, not the LLM's raw value."""
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    import dataclasses as _dc
    base = make_persona("u1", "Alice")
    persona_with_history = _dc.replace(base, persona_attrs={"big_five": {"O": 0.8}})
    await pr.upsert(persona_with_history)
    await er.upsert(make_event("ev1", uid="u1"))
    # LLM says O=0.0 (75% raw), but EMA should blend: 0.35*0.0 + 0.65*0.8 = 0.52 → 76%
    # The evidence sentence has a wrong "50%" from LLM — it must be replaced with 76%
    provider = _MockProvider(
        '{"description":"test","big_five":{"O":0.0},'
        '"big_five_evidence":{"O":"Alice 在开放性上表现出中等水平，可以推断出 50% 的量化结果。"}}'
    )
    from core.config import SynthesisConfig
    await run_persona_synthesis(pr, er, provider_getter=lambda: provider,
                                synthesis_config=SynthesisConfig(ema_alpha=0.35))
    updated = await pr.get("u1")
    assert updated is not None
    merged_o = updated.persona_attrs["big_five"]["O"]
    expected_pct = round((merged_o + 1) / 2 * 100)
    evidence_o = updated.persona_attrs["big_five_evidence"]["O"]
    assert f"{expected_pct}%" in evidence_o
    assert "50%" not in evidence_o  # LLM's stale value must be replaced


async def test_persona_synthesis_evidence_backward_compat_string() -> None:
    """Old-format single string evidence is preserved as-is for backward compat."""
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    await pr.upsert(make_persona("u1"))
    await er.upsert(make_event("ev1", uid="u1"))
    provider = _MockProvider(
        '{"description":"test","big_five":{"O":0.1},"big_five_evidence":"旧格式综合依据"}'
    )
    await run_persona_synthesis(pr, er, provider_getter=lambda: provider)
    updated = await pr.get("u1")
    assert updated is not None
    evidence = updated.persona_attrs.get("big_five_evidence")
    assert isinstance(evidence, str)
    assert len(evidence) <= 120


async def test_persona_synthesis_truncates_evidence_dict() -> None:
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    await pr.upsert(make_persona("u1"))
    await er.upsert(make_event("ev1", uid="u1"))
    long_sentence = "e" * 200
    provider = _MockProvider(
        f'{{"description":"test","big_five":{{"O":0.1}},"big_five_evidence":{{"O":"{long_sentence}"}}}}'
    )
    await run_persona_synthesis(pr, er, provider_getter=lambda: provider)
    updated = await pr.get("u1")
    assert updated is not None
    evidence = updated.persona_attrs.get("big_five_evidence")
    assert isinstance(evidence, dict)
    assert len(evidence.get("O", "")) <= 120


async def test_persona_synthesis_ema_blends_existing_scores() -> None:
    """EMA merge: new score is blended with existing score, not fully replaced."""
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    persona = make_persona("u1", "Alice")
    persona = persona.__class__(
        uid=persona.uid,
        bound_identities=persona.bound_identities,
        primary_name=persona.primary_name,
        persona_attrs={"big_five": {"O": 0.8}},  # existing high O
        confidence=persona.confidence,
        created_at=persona.created_at,
        last_active_at=persona.last_active_at,
    )
    await pr.upsert(persona)
    await er.upsert(make_event("ev1", uid="u1"))
    # LLM returns low O — should be blended, not fully replaced
    provider = _MockProvider('{"description":"test","big_five":{"O":0.0}}')
    from core.config import SynthesisConfig
    await run_persona_synthesis(pr, er, provider_getter=lambda: provider,
                                synthesis_config=SynthesisConfig(ema_alpha=0.35))
    updated = await pr.get("u1")
    assert updated is not None
    blended_o = updated.persona_attrs.get("big_five", {}).get("O", 0)
    # Expected: 0.35*0.0 + 0.65*0.8 = 0.52
    assert abs(blended_o - 0.52) < 0.01


# ---------------------------------------------------------------------------
# Impression recalculation
# ---------------------------------------------------------------------------

async def test_impression_recalculation_empty_returns_zero() -> None:
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()
    count = await run_impression_recalculation(pr, er, ir)
    assert count == 0


async def test_impression_recalculation_updates_derived_fields() -> None:
    from core.social.ipc_model import derive_fields
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()
    await pr.upsert(make_persona("u1"))
    imp = make_impression("u1", "u2")
    imp = dataclasses.replace(imp, benevolence=0.6, power=0.3)
    await ir.upsert(imp)
    count = await run_impression_recalculation(pr, er, ir)
    assert count == 1
    updated = await ir.get("u1", "u2", "global")
    assert updated is not None
    expected_ipc, expected_ai, expected_rs = derive_fields(0.6, 0.3)
    assert updated.ipc_orientation == expected_ipc
    assert abs(updated.affect_intensity - expected_ai) < 1e-6
    assert abs(updated.r_squared - expected_rs) < 1e-6
    assert abs(updated.confidence - expected_rs) < 1e-6


async def test_impression_recalculation_rebuilds_evidence_event_ids() -> None:
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()
    await pr.upsert(make_persona("u1"))

    # Two shared events, one event only for u1
    shared_ev = make_event("ev_shared", uid="u1")
    shared_ev = dataclasses.replace(shared_ev, participants=["u1", "u2"])
    await er.upsert(shared_ev)
    only_u1 = make_event("ev_only_u1", uid="u1")
    await er.upsert(only_u1)

    await ir.upsert(make_impression("u1", "u2", evidence=[]))
    await run_impression_recalculation(pr, er, ir)
    updated = await ir.get("u1", "u2", "global")
    assert updated is not None
    assert "ev_shared" in updated.evidence_event_ids
    assert "ev_only_u1" not in updated.evidence_event_ids


async def test_impression_recalculation_batch_queries_each_uid_once() -> None:
    """Each uid should be queried exactly once regardless of impression count."""
    pr = InMemoryPersonaRepository()
    ir = InMemoryImpressionRepository()

    query_log: list[str] = []

    class _CountingRepo(InMemoryEventRepository):
        async def list_by_participant(self, uid: str, limit: int = 100):
            query_log.append(uid)
            return await super().list_by_participant(uid, limit=limit)

    er = _CountingRepo()
    await pr.upsert(make_persona("u1"))
    # Three impressions all involving u1 as observer
    await ir.upsert(make_impression("u1", "u2"))
    await ir.upsert(make_impression("u1", "u3"))
    await ir.upsert(make_impression("u1", "u4"))

    await run_impression_recalculation(pr, er, ir)
    # u1 should appear exactly once in query_log (batch pre-load)
    assert query_log.count("u1") == 1


# ---------------------------------------------------------------------------
# Group summary
# ---------------------------------------------------------------------------

async def test_group_summary_no_provider_returns_zero(tmp_path: Path) -> None:
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()
    pr = InMemoryPersonaRepository()
    await er.upsert(make_event("ev1", group_id="g1"))
    count = await run_group_summary(er, tmp_path, provider_getter=lambda: None, impression_repo=ir, persona_repo=pr)
    assert count == 0


async def test_group_summary_writes_file(tmp_path: Path) -> None:
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()
    pr = InMemoryPersonaRepository()
    await er.upsert(make_event("ev1", topic="Python讨论", group_id="g1"))
    provider = _MockProvider("## 本期主要话题\n- Python讨论\n")
    count = await run_group_summary(er, tmp_path, provider_getter=lambda: provider, impression_repo=ir, persona_repo=pr)
    assert count == 1
    summaries = list((tmp_path / "groups" / "g1" / "summaries").glob("*.md"))
    assert len(summaries) == 1
    assert "Python讨论" in summaries[0].read_text(encoding="utf-8")


async def test_group_summary_skips_empty_group(tmp_path: Path) -> None:
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()
    pr = InMemoryPersonaRepository()
    # No events inserted
    provider = _MockProvider("summary content")
    count = await run_group_summary(er, tmp_path, provider_getter=lambda: provider, impression_repo=ir, persona_repo=pr)
    assert count == 0
    assert provider.calls == []


async def test_group_summary_private_chat_goes_to_global(tmp_path: Path) -> None:
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()
    pr = InMemoryPersonaRepository()
    await er.upsert(make_event("ev1", topic="私聊内容", group_id=None))
    provider = _MockProvider("## 私聊摘要\n")
    await run_group_summary(er, tmp_path, provider_getter=lambda: provider, impression_repo=ir, persona_repo=pr)
    summaries = list((tmp_path / "global" / "summaries").glob("*.md"))
    assert len(summaries) == 1


async def test_group_summary_multiple_groups(tmp_path: Path) -> None:
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()
    pr = InMemoryPersonaRepository()
    await er.upsert(make_event("ev1", group_id="g1"))
    await er.upsert(make_event("ev2", group_id="g2"))
    provider = _MockProvider("摘要内容")
    count = await run_group_summary(er, tmp_path, provider_getter=lambda: provider, impression_repo=ir, persona_repo=pr)
    assert count == 2
