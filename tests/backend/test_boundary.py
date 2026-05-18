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

    # summary_trigger_rounds=100 ensures 99 messages doesn't hit the round-based trigger
    cfg = BoundaryConfig(summary_trigger_rounds=100)
    det = EventBoundaryDetector(config=cfg, encoder=MockEncoder())
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


# ---------------------------------------------------------------------------
# find_split_index tests
# ---------------------------------------------------------------------------

def _fill_window_with_embeddings(
    count: int, start: float = 1000.0, gap: float = 1.0,
    embedding_fn=None,
) -> MessageWindow:
    """Fill a window where every message has an embedding."""
    w = MessageWindow(session_id="s", group_id="g", start_time=start, last_message_time=start)
    for i in range(count):
        ts = start + i * gap
        w.add_message("uid-a", f"msg{i}", ts)
        vec = embedding_fn(i) if embedding_fn else [1.0] * 4
        w.attach_embedding(i, vec)
    return w


def test_find_split_index_time_gap_no_encoder() -> None:
    """Without encoder: split at the biggest time gap in the tail.

    gap=200 when i==17 means msg17 arrives 200s after msg16.
    The big gap is BETWEEN msg16 and msg17, so split_after=16:
    flush msgs[0..16], keep msgs[17..19] as seed.
    """
    det = EventBoundaryDetector()  # no encoder
    w = MessageWindow(session_id="s", group_id="g", start_time=1000.0, last_message_time=1000.0)
    ts = 1000.0
    for i in range(20):
        gap = 200.0 if i == 17 else 1.0
        ts += gap
        w.add_message("uid-a", f"msg{i}", ts)

    split = det.find_split_index(w)
    # gap(msg16→msg17) = 200s → split_after = 16
    assert split == 16


def test_find_split_index_time_gap_below_min_returns_last() -> None:
    """No gap exceeds _MIN_GAP_SECONDS → returns message_count - 1 (flush all)."""
    det = EventBoundaryDetector()
    w = _fill_window(20)  # all 1-second gaps
    split = det.find_split_index(w)
    assert split == w.message_count - 1


def test_find_split_index_encoder_path() -> None:
    """With encoder: split at maximum cosine distance pair in the tail."""
    from core.embedding.encoder import NullEncoder

    class MockEncoder(NullEncoder):
        @property
        def dim(self) -> int:
            return 4

    det = EventBoundaryDetector(encoder=MockEncoder())
    # 20 messages, all similar embeddings except index 17→18 has orthogonal vectors
    def emb(i: int) -> list[float]:
        # Messages 0–17: [1,0,0,0], messages 18–19: [0,1,0,0]
        return [1.0, 0.0, 0.0, 0.0] if i <= 17 else [0.0, 1.0, 0.0, 0.0]

    w = _fill_window_with_embeddings(20, embedding_fn=emb)
    split = det.find_split_index(w)
    # Cosine distance between msg17 ([1,0,0,0]) and msg18 ([0,1,0,0]) = 1.0 (max)
    assert split == 17


def test_find_split_index_encoder_fallback_on_missing_embeddings() -> None:
    """When embeddings are absent, encoder path falls back to time-gap."""
    from core.embedding.encoder import NullEncoder

    class MockEncoder(NullEncoder):
        @property
        def dim(self) -> int:
            return 4

    det = EventBoundaryDetector(encoder=MockEncoder())
    # 20 messages with NO embeddings, one large time gap at index 16
    w = MessageWindow(session_id="s", group_id="g", start_time=1000.0, last_message_time=1000.0)
    ts = 1000.0
    for i in range(20):
        ts += 200.0 if i == 16 else 1.0
        w.add_message("uid-a", f"msg{i}", ts)
    # No embeddings attached — encoder path finds no embedded pairs → time-gap fallback
    # ts += 200.0 if i==16 means gap is added BEFORE msg16, so gap is between msg15→msg16 → split_after=15
    split = det.find_split_index(w)
    assert split == 15


def test_find_split_index_small_window_returns_last() -> None:
    """Window with < 2 messages: returns message_count - 1."""
    det = EventBoundaryDetector()
    w = _fill_window(1)
    assert det.find_split_index(w) == 0
