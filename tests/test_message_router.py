"""Integration tests for MessageRouter — no AstrBot runtime needed."""
from __future__ import annotations

import pytest

from core.adapters.astrbot import MessageRouter
from core.adapters.identity import IdentityResolver
from core.boundary.detector import BoundaryConfig, EventBoundaryDetector
from core.domain.models import Event
from core.repository.memory import InMemoryEventRepository, InMemoryPersonaRepository


def make_router(
    time_gap_minutes: float = 30.0,
    max_messages: int = 50,
) -> tuple[MessageRouter, InMemoryEventRepository]:
    persona_repo = InMemoryPersonaRepository()
    event_repo = InMemoryEventRepository()
    resolver = IdentityResolver(persona_repo)
    detector = EventBoundaryDetector(
        BoundaryConfig(time_gap_minutes=time_gap_minutes, max_messages=max_messages)
    )
    router = MessageRouter(
        event_repo=event_repo,
        identity_resolver=resolver,
        detector=detector,
    )
    return router, event_repo


async def test_router_accumulates_messages_in_window() -> None:
    router, event_repo = make_router()
    t = 1000.0
    await router.process("qq", "u1", "Alice", "hello", "g1", now=t)
    await router.process("qq", "u2", "Bob", "hi", "g1", now=t + 10)
    # No event saved yet (window still open)
    events = await event_repo.list_by_group("g1")
    assert len(events) == 0


async def test_router_flush_all_saves_event() -> None:
    router, event_repo = make_router()
    t = 1000.0
    await router.process("qq", "u1", "Alice", "hello", "g1", now=t)
    await router.process("qq", "u2", "Bob", "hi", "g1", now=t + 10)
    await router.flush_all()
    events = await event_repo.list_by_group("g1")
    assert len(events) == 1
    ev = events[0]
    assert ev.group_id == "g1"
    assert len(ev.interaction_flow) == 2


async def test_router_time_gap_closes_window() -> None:
    router, event_repo = make_router(time_gap_minutes=1.0)
    t = 1000.0
    await router.process("qq", "u1", "Alice", "msg1", "g1", now=t)
    # 2 minutes later — exceeds 1-minute gap → old window closes, new one starts
    await router.process("qq", "u1", "Alice", "msg2", "g1", now=t + 120)
    events = await event_repo.list_by_group("g1")
    assert len(events) == 1  # first window flushed
    # Window still holds the second message
    await router.flush_all()
    events = await event_repo.list_by_group("g1")
    assert len(events) == 2


async def test_router_max_messages_closes_window() -> None:
    router, event_repo = make_router(max_messages=3)
    t = 1000.0
    for i in range(3):
        await router.process("qq", "u1", "Alice", f"msg{i}", "g1", now=t + i)
    # 4th message triggers close of the 3-message window
    await router.process("qq", "u1", "Alice", "msg3", "g1", now=t + 3)
    events = await event_repo.list_by_group("g1")
    assert len(events) == 1
    assert len(events[0].interaction_flow) == 3


async def test_router_separate_sessions_independent() -> None:
    router, event_repo = make_router(time_gap_minutes=1.0)
    t = 1000.0
    await router.process("qq", "u1", "Alice", "grp msg", "g1", now=t)
    await router.process("qq", "u2", "Bob", "private msg", None, now=t)
    await router.flush_all()
    grp_events = await event_repo.list_by_group("g1")
    priv_events = await event_repo.list_by_group(None)
    assert len(grp_events) == 1
    assert len(priv_events) == 1


async def test_router_event_contains_correct_participants() -> None:
    router, event_repo = make_router()
    t = 1000.0
    await router.process("qq", "u1", "Alice", "hi", "g1", now=t)
    await router.process("qq", "u2", "Bob", "hey", "g1", now=t + 1)
    await router.process("qq", "u1", "Alice", "again", "g1", now=t + 2)
    await router.flush_all()
    events = await event_repo.list_by_group("g1")
    assert len(events[0].participants) == 2  # deduplicated


async def test_router_on_event_close_callback_called() -> None:
    closed: list[Event] = []

    async def capture(event, window):
        closed.append(event)

    persona_repo = InMemoryPersonaRepository()
    event_repo = InMemoryEventRepository()
    router = MessageRouter(
        event_repo=event_repo,
        identity_resolver=IdentityResolver(persona_repo),
        detector=EventBoundaryDetector(BoundaryConfig(max_messages=2)),
        on_event_close=capture,
    )
    t = 1000.0
    await router.process("qq", "u1", "Alice", "msg1", "g1", now=t)
    await router.process("qq", "u1", "Alice", "msg2", "g1", now=t + 1)
    # 3rd message triggers close of 2-message window
    await router.process("qq", "u1", "Alice", "msg3", "g1", now=t + 2)
    assert len(closed) == 1
    assert len(closed[0].interaction_flow) == 2


async def test_router_flush_all_clears_windows() -> None:
    router, event_repo = make_router()
    await router.process("qq", "u1", "Alice", "hi", "g1", now=1000.0)
    assert len(router._windows) == 1
    await router.flush_all()
    assert len(router._windows) == 0


async def test_router_same_platform_different_users_share_group_window() -> None:
    router, event_repo = make_router()
    t = 1000.0
    await router.process("qq", "u1", "Alice", "hello", "g1", now=t)
    await router.process("qq", "u2", "Bob", "world", "g1", now=t + 5)
    await router.flush_all()
    events = await event_repo.list_by_group("g1")
    assert len(events) == 1
    assert len(events[0].interaction_flow) == 2
