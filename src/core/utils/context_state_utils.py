"""VCM State Machine utilities and types."""
from __future__ import annotations

from enum import Enum


class VCMState(Enum):
    """Virtual Context Management states."""
    FOCUSED = "focused"   # Continuous conversation, low token pressure
    RECALL = "recall"     # Long-term memory retrieval active
    EVICTION = "eviction" # Token pressure high, compression needed
    DRIFT = "drift"       # Topic shift detected


def determine_next_state(
    current_state: VCMState,
    message_count: int,
    window_size: int,
    drift_detected: bool = False,
    recall_hit: bool = False
) -> VCMState:
    """Simple state transition logic for VCM."""
    if drift_detected:
        return VCMState.DRIFT
    
    if message_count >= window_size * 0.8: # Threshold for eviction
        return VCMState.EVICTION
    
    if recall_hit:
        return VCMState.RECALL
    
    # Default/Recovery
    if current_state == VCMState.DRIFT:
        return VCMState.FOCUSED
        
    return VCMState.FOCUSED
