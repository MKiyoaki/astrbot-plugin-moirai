"""Tests for MessageWindow, EventBoundaryDetector, and IdentityResolver."""
from __future__ import annotations

import pytest

from core.boundary.detector import BoundaryConfig, EventBoundaryDetector
from core.boundary.window import MessageWindow
from core.adapters.identity import IdentityResolver
from core.repository.memory import InMemoryPersonaRepository


# ---------------------------------------------------------------------------
# MessageWindow tests
# ---------------------------------------------------------------------------

def make_window(session_id: str = "test", group_id: str | None = "g1") -> MessageWindow:
    return MessageWindow(session_id=session_id, group_id=group_id, start_time=1000.0, last_message_time=1000.0)


def test_window_initial_state() -> None:
    w = make_window()
    assert w.message_count == 0
    assert w.duration_seconds == 0.0
    assert w.first_text == ""
    assert w.latest_text == ""
    assert w.participants == []


def test_window_add_message_updates_count_and_time() -> None:
    w = make_window()
    w.add_message("uid-a", "hello", 1010.0)
    assert w.message_count == 1
    assert w.last_message_time == 1010.0
    assert w.duration_seconds == 10.0


def test_window_first_and_latest_text() -> None:
    w = make_window()
    w.add_message("uid-a", "first", 1001.0)
    w.add_message("uid-b", "second", 1002.0)
    assert w.first_text == "first"
    assert w.latest_text == "second"


def test_window_participants_deduplication() -> None:
    w = make_window()
    w.add_message("uid-a", "msg1", 1001.0)
    w.add_message("uid-b", "msg2", 1002.0)
    w.add_message("uid-a", "msg3", 1003.0)  # duplicate
    assert w.participants == ["uid-a", "uid-b"]


def test_window_age_since_last_message() -> None:
    w = make_window()
    w.add_message("uid-a", "hi", 1005.0)
    assert w.age_since_last_message(1010.0) == pytest.approx(5.0)


def test_window_private_chat_group_id_none() -> None:
    w = MessageWindow(session_id="platform:private:u1", group_id=None, start_time=0.0, last_message_time=0.0)
    assert w.group_id is None


# ---------------------------------------------------------------------------
# EventBoundaryDetector tests
# ---------------------------------------------------------------------------

def _fill_window(count: int, start: float = 1000.0) -> MessageWindow:
    w = MessageWindow(session_id="s", group_id="g", start_time=start, last_message_time=start)
    for i in range(count):
        w.add_message("uid-a", f"msg{i}", start + i)
    return w


def test_detector_no_close_for_fresh_window() -> None:
    cfg = BoundaryConfig(time_gap_minutes=30, max_messages=50, max_duration_minutes=60)
    det = EventBoundaryDetector(cfg)
    w = _fill_window(5, start=1000.0)
    should_close, reason = det.should_close(w, now=1001.0)
    assert not should_close
    assert reason == ""


def test_detector_time_gap_fires() -> None:
    cfg = BoundaryConfig(time_gap_minutes=30)
    det = EventBoundaryDetector(cfg)
    w = _fill_window(3, start=1000.0)
    now = 1000.0 + 31 * 60  # 31 minutes after last message
    should_close, reason = det.should_close(w, now=now)
    assert should_close
    assert reason == "time_gap"


def test_detector_time_gap_exact_boundary_does_not_fire() -> None:
    cfg = BoundaryConfig(time_gap_minutes=30)
    det = EventBoundaryDetector(cfg)
    w = _fill_window(1, start=1000.0)
    now = 1000.0 + 30 * 60  # exactly 30 minutes — not > 30
    should_close, _ = det.should_close(w, now=now)
    assert not should_close


def test_detector_max_messages_hard_cap_fires() -> None:
    from core.embedding.encoder import NullEncoder
    class MockEncoder(NullEncoder):
        @property
        def dim(self): return 512
        
    # Hard cap is max(50, max_messages * 2) = 100 (since default max_messages is 50)
    det = EventBoundaryDetector(encoder=MockEncoder())
    w = _fill_window(100, start=1000.0)
    should_close, reason = det.should_close(w, now=1001.0)
    assert should_close
    assert reason == "max_messages_hard_cap"


def test_detector_max_messages_below_hard_cap_does_not_fire() -> None:
    from core.embedding.encoder import NullEncoder
    class MockEncoder(NullEncoder):
        @property
        def dim(self): return 512
        
    det = EventBoundaryDetector(encoder=MockEncoder())
    w = _fill_window(99, start=1000.0)
    should_close, _ = det.should_close(w, now=1001.0)
    assert not should_close


async def test_detector_topic_drift_check() -> None:
    from core.embedding.encoder import NullEncoder
    
    cfg = BoundaryConfig(drift_min_messages=5, drift_threshold=0.5, drift_check_interval=1)
    det = EventBoundaryDetector(cfg)
    
    vec_a = [1.0] * 512
    vec_b = [-1.0] * 512

    # 1. Below drift_min_messages: no drift check
    w = _fill_window(4)
    # Mock centroid by adding messages with embeddings
    for m in w.messages:
        w.attach_embedding(w.messages.index(m), vec_a)
    assert not await det.check_drift(w, vec_b)
    
    # 2. At drift_min_messages, but same topic: no drift
    w = _fill_window(5)
    for m in w.messages:
        w.attach_embedding(w.messages.index(m), vec_a)
    assert not await det.check_drift(w, vec_a)
    
    # 3. At drift_min_messages, different topic: drift!
    assert await det.check_drift(w, vec_b)


def test_detector_defaults_are_reasonable() -> None:
    det = EventBoundaryDetector()
    assert det.config.time_gap_minutes == 30.0
    assert det.config.max_messages == 50
    assert det.config.max_duration_minutes == 60.0
    assert det.config.drift_threshold == 0.6
    assert det.config.drift_min_messages == 20


# ---------------------------------------------------------------------------
# IdentityResolver tests
# ---------------------------------------------------------------------------

@pytest.fixture
def persona_repo():
    return InMemoryPersonaRepository()


async def test_identity_resolver_creates_new_uid(persona_repo) -> None:
    resolver = IdentityResolver(persona_repo)
    uid = await resolver.get_or_create_uid("qq", "123456", "Alice")
    assert isinstance(uid, str) and len(uid) > 0


async def test_identity_resolver_same_identity_returns_same_uid(persona_repo) -> None:
    resolver = IdentityResolver(persona_repo)
    uid1 = await resolver.get_or_create_uid("qq", "123456", "Alice")
    uid2 = await resolver.get_or_create_uid("qq", "123456", "Alice Renamed")
    assert uid1 == uid2


async def test_identity_resolver_different_platform_different_uid(persona_repo) -> None:
    resolver = IdentityResolver(persona_repo)
    uid_qq = await resolver.get_or_create_uid("qq", "123456", "Alice")
    uid_tg = await resolver.get_or_create_uid("telegram", "123456", "Alice")
    assert uid_qq != uid_tg


async def test_identity_resolver_creates_persona_with_correct_binding(persona_repo) -> None:
    resolver = IdentityResolver(persona_repo)
    uid = await resolver.get_or_create_uid("slack", "U001", "Bob")
    persona = await persona_repo.get(uid)
    assert persona is not None
    assert ("slack", "U001") in persona.bound_identities
    assert persona.primary_name == "Bob"


async def test_identity_resolver_empty_display_name_defaults_to_user(persona_repo) -> None:
    resolver = IdentityResolver(persona_repo)
    uid = await resolver.get_or_create_uid("qq", "999", "")
    persona = await persona_repo.get(uid)
    assert persona is not None
    assert persona.primary_name == "User"


async def test_identity_resolver_touch_last_active_updates_timestamp(persona_repo) -> None:
    import time
    resolver = IdentityResolver(persona_repo)
    uid = await resolver.get_or_create_uid("qq", "111", "Carol")
    before = (await persona_repo.get(uid)).last_active_at

    time.sleep(0.01)
    await resolver.touch_last_active(uid)
    after = (await persona_repo.get(uid)).last_active_at
    assert after >= before


async def test_identity_resolver_touch_last_active_missing_uid_noop(persona_repo) -> None:
    resolver = IdentityResolver(persona_repo)
    await resolver.touch_last_active("nonexistent-uid")  # should not raise
