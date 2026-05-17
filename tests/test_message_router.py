"""Integration tests for MessageRouter — no AstrBot runtime needed."""
from __future__ import annotations

import pytest

from core.adapters.astrbot import MessageRouter
from core.adapters.identity import IdentityResolver
from core.boundary.detector import BoundaryConfig, EventBoundaryDetector
from core.embedding.encoder import NullEncoder
from core.domain.models import Event
from core.repository.memory import InMemoryEventRepository, InMemoryPersonaRepository
from core.managers.context_manager import ContextManager
from core.config import ContextConfig


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

    async def mock_on_event_close(window: MessageWindow):
        from core.domain.models import Event, MessageRef
        import uuid
        event = Event(
            event_id=str(uuid.uuid4()),
            group_id=window.group_id,
            start_time=window.start_time,
            end_time=window.last_message_time,
            participants=window.participants,
            interaction_flow=[
                MessageRef(sender_uid=m.uid, timestamp=m.timestamp, content_hash="", content_preview=m.text[:100])
                for m in window.messages
            ],
            topic="test",
            summary="test summary",
            chat_content_tags=[],
            salience=0.5,
            confidence=0.5,
            inherit_from=[],
            last_accessed_at=window.last_message_time,
        )
        await event_repo.upsert(event)

    router = MessageRouter(
        event_repo=event_repo,
        identity_resolver=resolver,
        detector=detector,
        context_manager=ContextManager(ContextConfig()),
        encoder=NullEncoder(),
        on_event_close=mock_on_event_close,
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
    from core.boundary.window import MessageWindow
    closed: list[MessageWindow] = []

    async def capture(window: MessageWindow):
        closed.append(window)

    persona_repo = InMemoryPersonaRepository()
    event_repo = InMemoryEventRepository()
    router = MessageRouter(
        event_repo=event_repo,
        identity_resolver=IdentityResolver(persona_repo),
        detector=EventBoundaryDetector(BoundaryConfig(max_messages=2)),
        context_manager=ContextManager(ContextConfig()),
        encoder=NullEncoder(),
        on_event_close=capture,
    )
    t = 1000.0
    await router.process("qq", "u1", "Alice", "msg1", "g1", now=t)
    await router.process("qq", "u1", "Alice", "msg2", "g1", now=t + 1)
    # 3rd message triggers close of 2-message window
    await router.process("qq", "u1", "Alice", "msg3", "g1", now=t + 2)
    assert len(closed) == 1
    assert closed[0].message_count == 2


async def test_router_flush_all_clears_windows() -> None:
    router, event_repo = make_router()
    await router.process("qq", "u1", "Alice", "hi", "g1", now=1000.0)
    assert len(router._context_manager._windows) == 1
    await router.flush_all()
    assert len(router._context_manager._windows) == 0


# ---------------------------------------------------------------------------
# P0-2: topic_drift dead code — boundary detector never returns "topic_drift";
#        drift_detected in MessageRouter must be False for all v1 close reasons.
# ---------------------------------------------------------------------------

async def test_router_drift_detected_is_false_for_time_gap_close() -> None:
    """drift_detected must be False when a window closes due to a time gap.

    In v1, EventBoundaryDetector does not implement topic_drift detection.
    The old code `drift_detected = (reason == "topic_drift")` was always False;
    after the fix it is statically False so the intent is explicit.
    """
    from core.utils.context_state_utils import VCMState
    from core.managers.context_manager import ContextManager as _CM
    from core.config import ContextConfig

    states_seen: list[VCMState] = []

    class _TrackingContextManager(_CM):
        def update_state(self, session_id, drift_detected=False, recall_hit=False):
            state = super().update_state(session_id, drift_detected=drift_detected, recall_hit=recall_hit)
            states_seen.append(state)
            # drift_detected must always be False in v1
            assert drift_detected is False, "drift_detected should be False in v1"
            return state

    persona_repo = InMemoryPersonaRepository()
    event_repo = InMemoryEventRepository()
    ctx_mgr = _TrackingContextManager(ContextConfig())
    router = MessageRouter(
        event_repo=event_repo,
        identity_resolver=IdentityResolver(persona_repo),
        detector=EventBoundaryDetector(BoundaryConfig(time_gap_minutes=1.0)),
        context_manager=ctx_mgr,
        encoder=NullEncoder(),
        on_event_close=None,
    )

    t = 1000.0
    await router.process("qq", "u1", "Alice", "msg1", "g1", now=t)
    # 2-minute gap closes the window, then new message arrives
    await router.process("qq", "u1", "Alice", "msg2", "g1", now=t + 120)

    import asyncio
    await asyncio.sleep(0.01) # Wait for background tasks

    assert len(states_seen) >= 1

async def test_router_same_platform_different_users_share_group_window() -> None:
    router, event_repo = make_router()
    t = 1000.0
    await router.process("qq", "u1", "Alice", "hello", "g1", now=t)
    await router.process("qq", "u2", "Bob", "world", "g1", now=t + 5)
    await router.flush_all()
    events = await event_repo.list_by_group("g1")
    assert len(events) == 1
    assert len(events[0].interaction_flow) == 2


async def test_normalized_text_propagates_through_router_to_fallback_event() -> None:
    """End-to-end: EventHandler-style normalization → router → window → fallback_extraction.

    Demonstrates that a napcat-flavored message containing `[CQ:at,...]` and
    `@昵称(QQ号)` residue never reaches the resulting event's topic or tags
    as polluted strings.
    """
    from core.boundary.window import MessageWindow
    from core.adapters.message_normalizer import normalize_message_text
    from core.extractor.parser import fallback_extraction

    captured: list[MessageWindow] = []

    async def capture(window: MessageWindow):
        captured.append(window)

    persona_repo = InMemoryPersonaRepository()
    event_repo = InMemoryEventRepository()
    router = MessageRouter(
        event_repo=event_repo,
        identity_resolver=IdentityResolver(persona_repo),
        detector=EventBoundaryDetector(BoundaryConfig(max_messages=3)),
        context_manager=ContextManager(ContextConfig()),
        encoder=NullEncoder(),
        on_event_close=capture,
    )

    raw_inputs = [
        "[CQ:at,qq=1783088492] 你看这个",
        "@卢比鹏(1783088492) 在吗",
        "[CQ:image,file=x.jpg]",
    ]
    t = 1000.0
    for i, raw in enumerate(raw_inputs):
        await router.process(
            "qq", f"u{i}", f"User{i}", normalize_message_text(raw), "g1", now=t + i,
        )
    await router.flush_all()

    assert captured, "expected on_event_close to fire"
    window = captured[0]

    for m in window.messages:
        assert "1783088492" not in m.text
        assert "[CQ:" not in m.text

    result = fallback_extraction(window)
    ev = result[0]
    assert "[CQ:" not in ev["topic"]
    assert "1783088492" not in ev["topic"]
    for tag in ev["chat_content_tags"]:
        assert not tag.startswith("@")
        assert "1783088492" not in tag
        assert not tag.isdigit()
