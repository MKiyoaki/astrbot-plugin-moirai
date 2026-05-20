"""Tests for the recall feedback loop.

Covers:
- recall_and_inject caches injected event IDs per session
- bump_salience_on_use raises salience of used events
- bump_salience_on_use updates last_accessed_at
- overlap filter: only events whose tags overlap with response text are bumped
- overlap filter: event with no tag overlap is not bumped
- salience is capped at 1.0
- access_count increments on each bump
- access-weighted decay: high access_count events decay slower
"""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.config import InjectionConfig, RetrievalConfig
from core.domain.models import Event, EventStatus, EventType
from core.managers.recall_manager import RecallManager
from core.repository.memory import InMemoryEventRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _event(eid: str, tags: list[str] | None = None, salience: float = 0.5) -> Event:
    return Event(
        event_id=eid,
        group_id=None,
        start_time=1000.0,
        end_time=2000.0,
        participants=["u1"],
        interaction_flow=[],
        topic=f"topic-{eid}",
        summary="",
        chat_content_tags=tags or [],
        salience=salience,
        confidence=0.9,
        inherit_from=[],
        last_accessed_at=0.0,
        status=EventStatus.ACTIVE,
        is_locked=False,
        bot_persona_name=None,
        event_type=EventType.EPISODE,
        access_count=0,
    )


def _make_retriever(events: list[Event]):
    event_repo = AsyncMock()
    event_repo.count_by_status = AsyncMock(return_value=len(events))
    event_repo.search_fts = AsyncMock(return_value=events)
    event_repo.search_vector = AsyncMock(return_value=[])
    event_repo.get_children = AsyncMock(return_value=[])
    event_repo.get = AsyncMock(return_value=None)

    encoder = MagicMock()
    encoder.dim = 0

    retriever = MagicMock()
    retriever._event_repo = event_repo
    retriever._encoder = encoder
    retriever._bm25_limit = 20
    retriever._vec_limit = 20
    return retriever, event_repo


def _make_rm(retriever):
    return RecallManager(
        retriever,
        RetrievalConfig(final_limit=5),
        InjectionConfig(position="system_prompt"),
    )


# ---------------------------------------------------------------------------
# 1. recall_and_inject caches injected event IDs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recall_and_inject_caches_injected_ids():
    """After recall_and_inject, get_last_injected_ids returns the injected event IDs."""
    ev = _event("e1")
    retriever, _ = _make_retriever([ev])
    rm = _make_rm(retriever)

    req = MagicMock()
    req.system_prompt = ""
    req.prompt = ""
    req.model = "gpt-4"

    await rm.recall_and_inject("query", req, "sess1")

    ids = rm.get_last_injected_ids("sess1")
    assert ids == ["e1"]


@pytest.mark.asyncio
async def test_get_last_injected_ids_empty_when_nothing_injected():
    """Returns empty list for unknown session."""
    retriever, _ = _make_retriever([])
    rm = _make_rm(retriever)
    assert rm.get_last_injected_ids("unknown") == []


# ---------------------------------------------------------------------------
# 2. bump_salience_on_use: basic salience + last_accessed update
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bump_salience_raises_salience():
    """bump_salience_on_use increases salience of bumped events."""
    repo = InMemoryEventRepository()
    ev = _event("e1", salience=0.5)
    await repo.upsert(ev)

    retriever = MagicMock()
    retriever._event_repo = repo
    retriever._encoder = MagicMock(dim=0)
    retriever._bm25_limit = 20
    retriever._vec_limit = 20
    rm = _make_rm(retriever)

    await rm.bump_salience_on_use(["e1"], response_text="anything", boost=0.1)

    updated = await repo.get("e1")
    assert updated.salience == pytest.approx(0.6)


@pytest.mark.asyncio
async def test_bump_salience_updates_last_accessed():
    """bump_salience_on_use sets last_accessed_at to a recent timestamp."""
    repo = InMemoryEventRepository()
    ev = _event("e1")
    await repo.upsert(ev)

    retriever = MagicMock()
    retriever._event_repo = repo
    retriever._encoder = MagicMock(dim=0)
    retriever._bm25_limit = 20
    retriever._vec_limit = 20
    rm = _make_rm(retriever)

    t_before = time.time()
    await rm.bump_salience_on_use(["e1"], response_text="anything", boost=0.1)

    updated = await repo.get("e1")
    assert updated.last_accessed_at >= t_before


@pytest.mark.asyncio
async def test_bump_salience_increments_access_count():
    """bump_salience_on_use increments access_count by 1."""
    repo = InMemoryEventRepository()
    ev = _event("e1")
    await repo.upsert(ev)

    retriever = MagicMock()
    retriever._event_repo = repo
    retriever._encoder = MagicMock(dim=0)
    retriever._bm25_limit = 20
    retriever._vec_limit = 20
    rm = _make_rm(retriever)

    await rm.bump_salience_on_use(["e1"], response_text="anything", boost=0.05)

    updated = await repo.get("e1")
    assert updated.access_count == 1


@pytest.mark.asyncio
async def test_bump_salience_capped_at_1():
    """salience never exceeds 1.0 after bump."""
    repo = InMemoryEventRepository()
    ev = _event("e1", salience=0.98)
    await repo.upsert(ev)

    retriever = MagicMock()
    retriever._event_repo = repo
    retriever._encoder = MagicMock(dim=0)
    retriever._bm25_limit = 20
    retriever._vec_limit = 20
    rm = _make_rm(retriever)

    await rm.bump_salience_on_use(["e1"], response_text="anything", boost=0.1)

    updated = await repo.get("e1")
    assert updated.salience <= 1.0


# ---------------------------------------------------------------------------
# 3. Overlap filter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_overlap_filter_bumps_matching_event():
    """Event whose tags appear in response_text gets bumped."""
    repo = InMemoryEventRepository()
    ev = _event("e1", tags=["咖啡", "下午茶"], salience=0.5)
    await repo.upsert(ev)

    retriever = MagicMock()
    retriever._event_repo = repo
    retriever._encoder = MagicMock(dim=0)
    retriever._bm25_limit = 20
    retriever._vec_limit = 20
    rm = _make_rm(retriever)

    await rm.bump_salience_on_use(["e1"], response_text="你上次提到喜欢咖啡", boost=0.1)

    updated = await repo.get("e1")
    assert updated.salience > 0.5


@pytest.mark.asyncio
async def test_overlap_filter_skips_non_matching_event():
    """Event whose tags have no overlap with response_text is NOT bumped."""
    repo = InMemoryEventRepository()
    ev = _event("e1", tags=["咖啡", "下午茶"], salience=0.5)
    await repo.upsert(ev)

    retriever = MagicMock()
    retriever._event_repo = repo
    retriever._encoder = MagicMock(dim=0)
    retriever._bm25_limit = 20
    retriever._vec_limit = 20
    rm = _make_rm(retriever)

    await rm.bump_salience_on_use(["e1"], response_text="今天天气不错", boost=0.1)

    updated = await repo.get("e1")
    assert updated.salience == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_overlap_filter_bypassed_when_no_tags():
    """Event with empty chat_content_tags is always bumped (no filter basis)."""
    repo = InMemoryEventRepository()
    ev = _event("e1", tags=[], salience=0.5)
    await repo.upsert(ev)

    retriever = MagicMock()
    retriever._event_repo = repo
    retriever._encoder = MagicMock(dim=0)
    retriever._bm25_limit = 20
    retriever._vec_limit = 20
    rm = _make_rm(retriever)

    await rm.bump_salience_on_use(["e1"], response_text="完全不相关的内容", boost=0.1)

    updated = await repo.get("e1")
    assert updated.salience > 0.5


# ---------------------------------------------------------------------------
# 4. Access-weighted decay
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_access_weighted_decay_slows_for_frequently_accessed():
    """Event with higher access_count decays slower than event with access_count=0."""
    from core.tasks.decay import run_access_weighted_decay
    from core.config import DecayConfig

    repo = InMemoryEventRepository()
    import dataclasses
    ev_fresh = _event("fresh", salience=0.8)  # access_count=0
    ev_used = dataclasses.replace(_event("used", salience=0.8), access_count=10)
    await repo.upsert(ev_fresh)
    await repo.upsert(ev_used)

    await run_access_weighted_decay(repo, DecayConfig(lambda_=0.1))

    fresh_after = await repo.get("fresh")
    used_after = await repo.get("used")

    assert used_after.salience > fresh_after.salience, (
        "Frequently accessed event should decay slower"
    )
