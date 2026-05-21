"""Tests for Soul block / Memory block injection separation (scheme B).

Invariants verified:
- Soul segment uses SOUL markers, never appears inside MEMORY markers.
- Soul is always injected into system_prompt regardless of injection_position.
- Memory block respects injection_position (system_prompt / user_message_before /
  user_message_after).
- clear_previous_injection removes both MEMORY and SOUL blocks.
- When soul is empty, no SOUL markers appear anywhere.
- When memory is empty but soul is active, only the SOUL block is written.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.config import (
    MEMORY_INJECTION_FOOTER,
    MEMORY_INJECTION_HEADER,
    SOUL_INJECTION_FOOTER,
    SOUL_INJECTION_HEADER,
    InjectionConfig,
    RetrievalConfig,
    SoulConfig,
)
from core.domain.models import Event, EventStatus, EventType
from core.managers.recall_manager import RecallManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_rm(
    events: list[Event] | None = None,
    position: str = "system_prompt",
    soul_enabled: bool = True,
) -> RecallManager:
    event_repo = AsyncMock()
    event_repo.count_by_status = AsyncMock(return_value=len(events or []))
    event_repo.search_fts = AsyncMock(return_value=events or [])
    event_repo.search_vector = AsyncMock(return_value=[])
    event_repo.get_children = AsyncMock(return_value=[])
    event_repo.get = AsyncMock(return_value=None)
    event_repo.update_salience = AsyncMock(return_value=True)
    event_repo.update_last_accessed = AsyncMock(return_value=True)
    event_repo.increment_access_count = AsyncMock(return_value=True)

    encoder = MagicMock()
    encoder.dim = 0

    retriever = MagicMock()
    retriever._event_repo = event_repo
    retriever._encoder = encoder
    retriever._bm25_limit = 20
    retriever._vec_limit = 20

    impression_repo = AsyncMock()
    impression_repo.list_by_subject = AsyncMock(return_value=[])
    impression_repo.list_by_observer = AsyncMock(return_value=[])

    persona_repo = AsyncMock()
    persona_repo.get = AsyncMock(return_value=None)

    soul_cfg = SoulConfig(enabled=soul_enabled, decay_rate=0.0)

    return RecallManager(
        retriever,
        RetrievalConfig(final_limit=5),
        InjectionConfig(position=position),
        persona_repo=persona_repo,
        impression_repo=impression_repo,
        soul_config=soul_cfg,
    )


def _req(system_prompt: str = "", prompt: str = "") -> MagicMock:
    req = MagicMock()
    req.system_prompt = system_prompt
    req.prompt = prompt
    req.model = "gpt-4"
    req.contexts = []
    return req


def _event(eid: str = "e1") -> Event:
    return Event(
        event_id=eid,
        topic="test topic",
        summary="a test event",
        start_time=900.0,
        end_time=1000.0,
        salience=0.8,
        confidence=0.9,
        status=EventStatus.ACTIVE,
        event_type=EventType.EPISODE,
    )


# ---------------------------------------------------------------------------
# Soul uses its own markers, never inside MEMORY markers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_soul_block_uses_soul_markers_not_memory_markers():
    """Soul segment is wrapped in SOUL markers, not inside the MEMORY block."""
    rm = _make_rm(events=[_event()], position="system_prompt", soul_enabled=True)
    # Prime the soul state so it deviates from neutral (expression_desire > 0).
    from core.social.soul_state import SoulState
    rm._soul_states["sess"] = SoulState(expression_desire=8.0)

    req = _req()
    await rm.recall_and_inject("hi", req, "sess")

    sp = req.system_prompt
    assert SOUL_INJECTION_HEADER in sp
    assert SOUL_INJECTION_FOOTER in sp
    # Soul content must not appear between MEMORY markers
    mem_start = sp.find(MEMORY_INJECTION_HEADER)
    mem_end = sp.find(MEMORY_INJECTION_FOOTER)
    soul_start = sp.find(SOUL_INJECTION_HEADER)
    if mem_start != -1 and mem_end != -1 and soul_start != -1:
        assert not (mem_start < soul_start < mem_end), (
            "Soul content found inside MEMORY block"
        )


@pytest.mark.asyncio
async def test_memory_block_does_not_contain_soul_markers():
    """MEMORY block contains no SOUL markers."""
    rm = _make_rm(events=[_event()], position="system_prompt", soul_enabled=True)
    from core.social.soul_state import SoulState
    rm._soul_states["sess"] = SoulState(expression_desire=8.0)

    req = _req()
    await rm.recall_and_inject("hi", req, "sess")

    sp = req.system_prompt
    mem_start = sp.find(MEMORY_INJECTION_HEADER)
    mem_end = sp.find(MEMORY_INJECTION_FOOTER)
    if mem_start != -1 and mem_end != -1:
        mem_block = sp[mem_start:mem_end + len(MEMORY_INJECTION_FOOTER)]
        assert SOUL_INJECTION_HEADER not in mem_block
        assert SOUL_INJECTION_FOOTER not in mem_block


# ---------------------------------------------------------------------------
# Soul always targets system_prompt regardless of injection_position
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_soul_in_system_prompt_when_position_user_message_before():
    """Even with user_message_before, soul block lands in system_prompt."""
    rm = _make_rm(events=[_event()], position="user_message_before", soul_enabled=True)
    from core.social.soul_state import SoulState
    rm._soul_states["sess"] = SoulState(expression_desire=8.0)

    req = _req()
    await rm.recall_and_inject("hi", req, "sess")

    assert SOUL_INJECTION_HEADER in req.system_prompt
    assert SOUL_INJECTION_HEADER not in req.prompt


@pytest.mark.asyncio
async def test_soul_in_system_prompt_when_position_user_message_after():
    """Even with user_message_after, soul block lands in system_prompt."""
    rm = _make_rm(events=[_event()], position="user_message_after", soul_enabled=True)
    from core.social.soul_state import SoulState
    rm._soul_states["sess"] = SoulState(creativity=9.0)

    req = _req()
    await rm.recall_and_inject("hi", req, "sess")

    assert SOUL_INJECTION_HEADER in req.system_prompt
    assert SOUL_INJECTION_HEADER not in req.prompt


# ---------------------------------------------------------------------------
# Memory block respects injection_position
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_memory_in_prompt_when_position_user_message_before():
    """Memory block appears in req.prompt (before user text) for user_message_before."""
    rm = _make_rm(events=[_event()], position="user_message_before", soul_enabled=False)

    req = _req(prompt="user query")
    await rm.recall_and_inject("hi", req, "sess")

    assert MEMORY_INJECTION_HEADER in req.prompt
    assert req.prompt.index(MEMORY_INJECTION_HEADER) < req.prompt.index("user query")
    assert MEMORY_INJECTION_HEADER not in req.system_prompt


@pytest.mark.asyncio
async def test_memory_in_prompt_when_position_user_message_after():
    """Memory block appears after user text for user_message_after."""
    rm = _make_rm(events=[_event()], position="user_message_after", soul_enabled=False)

    req = _req(prompt="user query")
    await rm.recall_and_inject("hi", req, "sess")

    assert MEMORY_INJECTION_HEADER in req.prompt
    assert req.prompt.index("user query") < req.prompt.index(MEMORY_INJECTION_HEADER)
    assert MEMORY_INJECTION_HEADER not in req.system_prompt


# ---------------------------------------------------------------------------
# clear_previous_injection removes both block types
# ---------------------------------------------------------------------------

def test_clear_removes_memory_block():
    rm = _make_rm()
    req = _req(
        system_prompt=f"base {MEMORY_INJECTION_HEADER}\ncontent\n{MEMORY_INJECTION_FOOTER}",
        prompt=f"{MEMORY_INJECTION_HEADER}\nmore\n{MEMORY_INJECTION_FOOTER} rest",
    )
    removed = rm.clear_previous_injection(req)
    assert removed >= 2
    assert MEMORY_INJECTION_HEADER not in req.system_prompt
    assert MEMORY_INJECTION_HEADER not in req.prompt


def test_clear_removes_soul_block():
    rm = _make_rm()
    req = _req(
        system_prompt=f"base {SOUL_INJECTION_HEADER}\nsoul content\n{SOUL_INJECTION_FOOTER}",
    )
    removed = rm.clear_previous_injection(req)
    assert removed >= 1
    assert SOUL_INJECTION_HEADER not in req.system_prompt


def test_clear_removes_both_blocks_simultaneously():
    rm = _make_rm()
    mem_block = f"{MEMORY_INJECTION_HEADER}\nmemory\n{MEMORY_INJECTION_FOOTER}"
    soul_block = f"{SOUL_INJECTION_HEADER}\nsoul\n{SOUL_INJECTION_FOOTER}"
    req = _req(system_prompt=f"base\n\n{mem_block}\n\n{soul_block}")
    removed = rm.clear_previous_injection(req)
    assert removed >= 2
    assert MEMORY_INJECTION_HEADER not in req.system_prompt
    assert SOUL_INJECTION_HEADER not in req.system_prompt
    assert "base" in req.system_prompt


# ---------------------------------------------------------------------------
# Edge cases: empty soul / empty memory
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_soul_markers_when_soul_disabled():
    """When soul is disabled, no SOUL markers appear anywhere."""
    rm = _make_rm(events=[_event()], position="system_prompt", soul_enabled=False)
    req = _req()
    await rm.recall_and_inject("hi", req, "sess")
    assert SOUL_INJECTION_HEADER not in req.system_prompt
    assert SOUL_INJECTION_HEADER not in req.prompt


@pytest.mark.asyncio
async def test_no_soul_markers_when_soul_state_near_neutral():
    """When all soul dimensions are near zero, no SOUL block is written."""
    rm = _make_rm(events=[], position="system_prompt", soul_enabled=True)
    # Default SoulState has all zeros → format_soul_for_prompt returns ""
    req = _req()
    await rm.recall_and_inject("hi", req, "sess")
    assert SOUL_INJECTION_HEADER not in req.system_prompt


@pytest.mark.asyncio
async def test_only_soul_block_when_no_events():
    """When no memory events exist but soul state is active, only SOUL block appears."""
    rm = _make_rm(events=[], position="user_message_before", soul_enabled=True)
    from core.social.soul_state import SoulState
    rm._soul_states["sess"] = SoulState(expression_desire=10.0)

    req = _req()
    await rm.recall_and_inject("hi", req, "sess")

    assert SOUL_INJECTION_HEADER in req.system_prompt
    assert MEMORY_INJECTION_HEADER not in req.system_prompt
    assert MEMORY_INJECTION_HEADER not in req.prompt
