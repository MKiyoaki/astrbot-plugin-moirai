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
