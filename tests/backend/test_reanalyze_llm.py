"""Tests for LLM-based impression reanalysis (core/tasks/reanalyze_llm.py)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.domain.models import Event, Impression
from core.repository.memory import InMemoryEventRepository, InMemoryImpressionRepository
from core.tasks.reanalyze_llm import ReanalyzeError, reanalyze_impressions_llm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _event(event_id: str, participants: list[str], group_id: str = "g1") -> Event:
    return Event(
        event_id=event_id,
        group_id=group_id,
        start_time=1000.0,
        end_time=1010.0,
        participants=participants,
        interaction_flow=[],
        topic=f"topic-{event_id}",
        summary=f"summary of {event_id}",
        chat_content_tags=[],
        salience=0.5,
        confidence=0.8,
    )


class _MockProvider:
    def __init__(self, response: str = '{"benevolence": 0.7, "power": 0.2}') -> None:
        self.response = response
        self.calls = 0

    async def text_chat(self, prompt: str = "", system_prompt: str = "") -> SimpleNamespace:
        self.calls += 1
        return SimpleNamespace(completion_text=self.response)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reanalyze_llm_provider_none_raises_before_any_write() -> None:
    """provider=None → ReanalyzeError raised; no impressions created."""
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()

    await er.upsert(_event("e1", ["u1", "u2"]))
    await er.upsert(_event("e2", ["u1", "u2"]))

    with pytest.raises(ReanalyzeError) as exc_info:
        await reanalyze_impressions_llm(er, ir, "g1", None, lambda: None)

    assert exc_info.value.code == "provider_none"
    # No impressions were written
    assert await ir.list_by_observer("u1") == []


@pytest.mark.asyncio
async def test_reanalyze_llm_insufficient_data_raises() -> None:
    """Fewer than 2 participants → ReanalyzeError, no writes."""
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()

    await er.upsert(_event("e1", ["u1"]))

    provider = _MockProvider()
    with pytest.raises(ReanalyzeError) as exc_info:
        await reanalyze_impressions_llm(er, ir, "g1", None, lambda: provider)

    assert exc_info.value.code == "insufficient_data"
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_reanalyze_llm_happy_path_creates_impressions() -> None:
    """Valid data + working LLM → impressions upserted for all pairs."""
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()

    await er.upsert(_event("e1", ["u1", "u2"]))
    await er.upsert(_event("e2", ["u1", "u2"]))

    provider = _MockProvider('{"benevolence": 0.8, "power": 0.3}')
    updated = await reanalyze_impressions_llm(er, ir, "g1", None, lambda: provider)

    assert updated == 2  # u1→u2 and u2→u1
    assert provider.calls == 2

    imp = await ir.get("u1", "u2", "g1")
    assert imp is not None
    assert abs(imp.benevolence - 0.8) < 0.01
    assert abs(imp.power - 0.3) < 0.01


@pytest.mark.asyncio
async def test_reanalyze_llm_skips_pair_on_llm_failure() -> None:
    """Individual LLM failures skip that pair; other pairs still succeed."""
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()

    await er.upsert(_event("e1", ["u1", "u2", "u3"]))

    call_count = [0]

    class _FlakyProvider:
        async def text_chat(self, prompt: str = "", system_prompt: str = "") -> SimpleNamespace:
            call_count[0] += 1
            if "u1" in prompt and "u2" in prompt:
                raise RuntimeError("timeout")
            return SimpleNamespace(completion_text='{"benevolence": 0.6, "power": 0.1}')

    updated = await reanalyze_impressions_llm(er, ir, "g1", None, lambda: _FlakyProvider())

    # u1→u2 fails, u2→u1 might fail too; other pairs succeed
    # At minimum, u1→u3 and u3→u1 and u2→u3 and u3→u2 should succeed
    assert updated >= 2


@pytest.mark.asyncio
async def test_reanalyze_llm_skips_pair_on_bad_json() -> None:
    """Unparseable LLM output → pair skipped, existing impression unchanged."""
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()

    await er.upsert(_event("e1", ["u1", "u2"]))

    # Pre-existing impression
    existing = Impression(
        observer_uid="u1", subject_uid="u2",
        ipc_orientation="P+", benevolence=0.5, power=0.5,
        affect_intensity=0.5, r_squared=0.5, confidence=0.5,
        scope="g1", evidence_event_ids=[], last_reinforced_at=1000.0,
    )
    await ir.upsert(existing)

    provider = _MockProvider("not json at all")
    updated = await reanalyze_impressions_llm(er, ir, "g1", None, lambda: provider)

    assert updated == 0
    # Original impression unchanged
    imp = await ir.get("u1", "u2", "g1")
    assert imp is not None
    assert imp.benevolence == 0.5


@pytest.mark.asyncio
async def test_reanalyze_llm_merges_with_existing_impression() -> None:
    """Existing impression → scores blended with alpha=0.4."""
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()

    await er.upsert(_event("e1", ["u1", "u2"]))

    existing = Impression(
        observer_uid="u1", subject_uid="u2",
        ipc_orientation="P+", benevolence=0.5, power=0.0,
        affect_intensity=0.3, r_squared=0.3, confidence=0.3,
        scope="g1", evidence_event_ids=[], last_reinforced_at=1000.0,
    )
    await ir.upsert(existing)

    provider = _MockProvider('{"benevolence": 1.0, "power": 0.0}')
    await reanalyze_impressions_llm(er, ir, "g1", None, lambda: provider)

    imp = await ir.get("u1", "u2", "g1")
    assert imp is not None
    # alpha=0.4: 0.4*1.0 + 0.6*0.5 = 0.7
    assert abs(imp.benevolence - 0.7) < 0.01
