"""Tests for ContextManager: LRU, TTL, and VCM state machine."""
import asyncio
import pytest
import time
from core.managers.context_manager import ContextManager
from core.config import ContextConfig
from core.utils.context_state_utils import VCMState

@pytest.fixture
def context_cfg():
    return ContextConfig(
        vcm_enabled=True,
        max_sessions=3,
        session_idle_seconds=1,
        window_size=10
    )

def test_lru_eviction(context_cfg):
    mgr = ContextManager(context_cfg)
    
    # Fill up to max
    mgr.get_window("s1", create=True)
    mgr.get_window("s2", create=True)
    mgr.get_window("s3", create=True)
    assert mgr.active_sessions_count == 3
    
    # Access s1 to make it most recent
    mgr.get_window("s1")
    
    # Add s4, should evict s2 (oldest)
    mgr.get_window("s4", create=True)
    assert mgr.active_sessions_count == 3
    assert mgr.get_window("s2") is None
    assert mgr.get_window("s1") is not None
    assert mgr.get_window("s3") is not None
    assert mgr.get_window("s4") is not None

def test_ttl_cleanup(context_cfg):
    mgr = ContextManager(context_cfg)
    mgr.get_window("s1", create=True)
    assert mgr.active_sessions_count == 1
    
    # Wait for idle timeout
    time.sleep(1.1)
    
    evicted = mgr.cleanup_expired()
    assert evicted == 1
    assert mgr.active_sessions_count == 0

def test_vcm_state_transitions(context_cfg):
    mgr = ContextManager(context_cfg)
    session_id = "s1"
    window = mgr.get_window(session_id, create=True)
    
    # Initial state
    assert mgr.get_state(session_id) == VCMState.FOCUSED
    
    # Test Drift
    state = mgr.update_state(session_id, drift_detected=True)
    assert state == VCMState.DRIFT
    assert mgr.get_state(session_id) == VCMState.DRIFT
    
    # Test recovery to Focused
    state = mgr.update_state(session_id)
    assert state == VCMState.FOCUSED
    
    # Test Recall
    state = mgr.update_state(session_id, recall_hit=True)
    assert state == VCMState.RECALL
    
    # Test Eviction (token pressure)
    # window_size is 10, eviction at 0.8 * 10 = 8 messages
    for i in range(8):
        window.add_message("u1", f"msg {i}", time.time())
        
    state = mgr.update_state(session_id)
    assert state == VCMState.EVICTION

def test_vcm_disabled(context_cfg):
    context_cfg.vcm_enabled = False
    mgr = ContextManager(context_cfg)
    session_id = "s1"
    mgr.get_window(session_id, create=True)

    # Should always stay FOCUSED
    state = mgr.update_state(session_id, drift_detected=True)
    assert state == VCMState.FOCUSED


# ---------------------------------------------------------------------------
# P0-1: LRU eviction must trigger evict_callback so messages are not silently lost
# ---------------------------------------------------------------------------

async def test_lru_eviction_triggers_evict_callback():
    evicted_sessions: list[str] = []

    async def capture(window):
        evicted_sessions.append(window.session_id)

    cfg = ContextConfig(max_sessions=2, vcm_enabled=False, session_idle_seconds=3600)
    mgr = ContextManager(cfg, evict_callback=capture)

    mgr.get_window("s1", create=True)
    mgr.get_window("s2", create=True)
    # Adding s3 must evict s1 (LRU) and call the callback
    mgr.get_window("s3", create=True)

    # Let the asyncio task scheduled by _evict_lru run
    await asyncio.sleep(0)

    assert evicted_sessions == ["s1"]


async def test_lru_eviction_without_callback_does_not_raise():
    """Existing behaviour without callback should be unaffected."""
    cfg = ContextConfig(max_sessions=2, vcm_enabled=False)
    mgr = ContextManager(cfg)  # no evict_callback

    mgr.get_window("s1", create=True)
    mgr.get_window("s2", create=True)
    mgr.get_window("s3", create=True)  # evicts s1, no callback

    await asyncio.sleep(0)
    assert mgr.get_window("s1") is None
    assert mgr.get_window("s2") is not None


# ---------------------------------------------------------------------------
# Scheduler integration: context_cleanup task pattern
# ---------------------------------------------------------------------------

async def test_context_cleanup_scheduler_pattern() -> None:
    """Regression: verifies the async wrapper pattern used in plugin_initializer.

    Old code registered `lambda: context_manager.cleanup_expired()` which returns
    int — awaiting that caused TypeError.  New code wraps it in `async def`.
    """
    from core.tasks.scheduler import TaskScheduler

    cfg = ContextConfig(max_sessions=10, vcm_enabled=False, session_idle_seconds=0)
    mgr = ContextManager(cfg)

    # Seed an idle session
    mgr.get_window("old_session", create=True, now=0.0)

    # Replicate the exact async wrapper from plugin_initializer
    async def _context_cleanup() -> None:
        mgr.cleanup_expired()

    s = TaskScheduler()
    s.register("context_cleanup", interval=60, fn=_context_cleanup)

    # Must not raise TypeError
    result = await s.run_now("context_cleanup")
    assert result is True
    # The idle session (last_active=0) should have been cleaned up
    assert mgr.get_window("old_session") is None


async def test_context_cleanup_returns_int_not_awaitable() -> None:
    """cleanup_expired() is intentionally sync and returns int — confirm this assumption."""
    cfg = ContextConfig(max_sessions=10, vcm_enabled=False, session_idle_seconds=0)
    mgr = ContextManager(cfg)
    mgr.get_window("s1", create=True, now=0.0)
    result = mgr.cleanup_expired()
    assert isinstance(result, int)
    assert result == 1
