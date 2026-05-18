import pytest
from core.utils.context_state_utils import VCMState, determine_next_state
from core.managers.context_manager import ContextManager
from core.config import ContextConfig

def test_determine_next_state_logic():
    # 1. Default -> Focused
    assert determine_next_state(VCMState.FOCUSED, 5, 50) == VCMState.FOCUSED
    
    # 2. Drift detection (Highest priority)
    assert determine_next_state(VCMState.FOCUSED, 5, 50, drift_detected=True) == VCMState.DRIFT
    
    # 3. Eviction (Message count >= 80% of window_size)
    assert determine_next_state(VCMState.FOCUSED, 40, 50) == VCMState.EVICTION
    assert determine_next_state(VCMState.FOCUSED, 39, 50) == VCMState.FOCUSED # 39/50 < 0.8
    
    # 4. Recall Hit
    assert determine_next_state(VCMState.FOCUSED, 5, 50, recall_hit=True) == VCMState.RECALL
    
    # 5. Drift Recovery
    assert determine_next_state(VCMState.DRIFT, 5, 50) == VCMState.FOCUSED

def test_context_manager_state_tracking():
    cfg = ContextConfig(vcm_enabled=True, window_size=10)
    cm = ContextManager(cfg)
    sid = "test_session"
    
    # Initial state
    cm.get_window(sid, create=True)
    assert cm.get_state(sid) == VCMState.FOCUSED
    
    # Test Eviction trigger via message count
    window = cm.get_window(sid)
    for i in range(8):
        window.add_message("u", f"msg {i}", 0.0)
    
    cm.update_state(sid)
    assert cm.get_state(sid) == VCMState.EVICTION
    
    # Test Drift trigger
    cm.update_state(sid, drift_detected=True)
    assert cm.get_state(sid) == VCMState.DRIFT

def test_vcm_disabled_logic():
    cfg = ContextConfig(vcm_enabled=False)
    cm = ContextManager(cfg)
    sid = "test_session"
    cm.get_window(sid, create=True)
    
    # Even with triggers, it should stay FOCUSED if disabled
    cm.update_state(sid, drift_detected=True)
    assert cm.get_state(sid) == VCMState.FOCUSED
