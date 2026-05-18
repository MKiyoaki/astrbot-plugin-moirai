"""Tests for Phase 2 additions: periodic window flush, persona-switch flush,
window prefix ops, and extractor fallback to ``last_active_persona``.
"""
from __future__ import annotations

import asyncio
import pytest

from core.adapters.astrbot import MessageRouter
from core.adapters.identity import IdentityResolver
from core.boundary.detector import BoundaryConfig, EventBoundaryDetector
from core.boundary.window import MessageWindow
from core.config import ContextConfig
from core.embedding.encoder import NullEncoder
from core.managers.context_manager import ContextManager
from core.repository.memory import InMemoryEventRepository, InMemoryPersonaRepository


# ---------------------------------------------------------------------------
# MessageWindow.clone_prefix / drop_prefix
# ---------------------------------------------------------------------------

def _make_window(n: int = 5) -> MessageWindow:
    w = MessageWindow(session_id="s", group_id="g", start_time=1000.0, last_message_time=1000.0)
    for i in range(n):
        w.add_message(uid=f"u{i}", text=f"m{i}", timestamp=1000.0 + i, display_name=f"name{i}")
    return w


def test_clone_prefix_returns_copy_with_first_n_messages() -> None:
    w = _make_window(5)
    pre = w.clone_prefix(3)
    assert pre.message_count == 3
    assert [m.text for m in pre.messages] == ["m0", "m1", "m2"]
    # Original is untouched
    assert w.message_count == 5
    assert pre.start_time == 1000.0
    assert pre.last_message_time == 1002.0


def test_clone_prefix_clamps_out_of_range() -> None:
    w = _make_window(3)
    assert w.clone_prefix(0).message_count == 0
    assert w.clone_prefix(100).message_count == 3
    assert w.clone_prefix(-5).message_count == 0


def test_drop_prefix_mutates_window_and_resets_timestamps() -> None:
    w = _make_window(5)
    w.drop_prefix(2)
    assert w.message_count == 3
    assert [m.text for m in w.messages] == ["m2", "m3", "m4"]
    assert w.start_time == 1002.0
    assert w.last_message_time == 1004.0


def test_clone_then_drop_preserves_persona_tag() -> None:
    w = _make_window(4)
    w.last_active_persona = "綾地寧寧"
    pre = w.clone_prefix(2)
    w.drop_prefix(2)
    assert pre.last_active_persona == "綾地寧寧"
    assert w.last_active_persona == "綾地寧寧"


# ---------------------------------------------------------------------------
# Router helpers
# ---------------------------------------------------------------------------

def _make_router() -> tuple[MessageRouter, list[MessageWindow]]:
    """Create a router whose on_event_close just records the windows it sees."""
    captured: list[MessageWindow] = []

    async def _capture(window: MessageWindow) -> None:
        captured.append(window)

    router = MessageRouter(
        event_repo=InMemoryEventRepository(),
        identity_resolver=IdentityResolver(InMemoryPersonaRepository()),
        detector=EventBoundaryDetector(BoundaryConfig(time_gap_minutes=999.0, max_messages=999)),
        context_manager=ContextManager(ContextConfig()),
        encoder=NullEncoder(),
        on_event_close=_capture,
    )
    return router, captured


async def test_note_session_persona_sets_window_field() -> None:
    router, _ = _make_router()
    await router.process("qq", "u1", "Alice", "hi", "g1", now=1000.0)
    router.note_session_persona("qq:g1", "綾地寧寧")
    window = router._context_manager.get_window("qq:g1")
    assert window is not None
    assert window.last_active_persona == "綾地寧寧"


async def test_flush_window_split_tail_emits_prefix_and_keeps_tail() -> None:
    router, captured = _make_router()
    for i in range(5):
        await router.process("qq", f"u{i}", f"name{i}", f"m{i}", "g1", now=1000.0 + i)
    flushed = await router.flush_window_split_tail("qq:g1", tail=1, new_persona="B")
    assert flushed is True
    # Prefix flushed contains messages [0..3]
    assert len(captured) == 1
    assert [m.text for m in captured[0].messages] == ["m0", "m1", "m2", "m3"]
    # Remaining window holds only the tail message and new persona tag
    window = router._context_manager.get_window("qq:g1")
    assert window is not None and window.message_count == 1
    assert window.messages[0].text == "m4"
    assert window.last_active_persona == "B"


async def test_flush_window_split_tail_noop_when_too_short() -> None:
    router, captured = _make_router()
    await router.process("qq", "u1", "Alice", "hi", "g1", now=1000.0)
    flushed = await router.flush_window_split_tail("qq:g1", tail=1, new_persona="B")
    assert flushed is False
    assert captured == []
    # New persona still recorded on existing window even without flush
    window = router._context_manager.get_window("qq:g1")
    assert window is not None and window.last_active_persona == "B"


async def test_run_periodic_flush_emits_stable_prefix() -> None:
    router, captured = _make_router()
    for i in range(8):
        await router.process("qq", "u1", "Alice", f"m{i}", "g1", now=1000.0 + i)

    # Drive the periodic loop manually for one tick by making interval tiny.
    enabled = {"v": True}
    task = asyncio.create_task(
        router.run_periodic_flush(
            interval_minutes=0.05,  # clamped floor — fires in ~3s
            tail_keep=3,
            enabled_getter=lambda: enabled["v"],
        )
    )
    await asyncio.sleep(3.5)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert len(captured) >= 1
    # First flush should contain the first 5 messages (8 - 3 tail_keep)
    assert [m.text for m in captured[0].messages] == ["m0", "m1", "m2", "m3", "m4"]
    window = router._context_manager.get_window("qq:g1")
    assert window is not None and window.message_count == 3
    assert [m.text for m in window.messages] == ["m5", "m6", "m7"]


# ---------------------------------------------------------------------------
# Extractor fallback to window.last_active_persona for 0-bot events
# ---------------------------------------------------------------------------

async def test_extractor_uses_last_active_persona_when_no_bot_message() -> None:
    from core.extractor.extractor import EventExtractor
    from core.config import ExtractorConfig

    repo = InMemoryEventRepository()
    persona_repo = InMemoryPersonaRepository()
    extractor = EventExtractor(
        event_repo=repo,
        provider_getter=lambda: None,
        encoder=NullEncoder(),
        extractor_config=ExtractorConfig(persona_influenced_summary=True),
        persona_repo=persona_repo,
    )

    window = MessageWindow(session_id="s", group_id="g", start_time=1000.0, last_message_time=1003.0)
    window.last_active_persona = "丰川祥子"
    for i, name in enumerate(["Alice", "Bob", "Alice"]):
        window.add_message(uid=f"user:{name}", text=f"m{i}", timestamp=1000.0 + i, display_name=name)

    name, desc = await extractor._resolve_window_persona(window)
    assert name == "丰川祥子"
