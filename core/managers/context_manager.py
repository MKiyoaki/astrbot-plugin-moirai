"""ContextManager: centralized session window management and VCM state machine."""
from __future__ import annotations

import logging
import time
from collections import OrderedDict
from typing import TYPE_CHECKING

from ..boundary.window import MessageWindow
from ..utils.context_state_utils import VCMState, determine_next_state

if TYPE_CHECKING:
    from ..config import ContextConfig

logger = logging.getLogger(__name__)


class ContextManager:
    """Manages active MessageWindows with LRU caching and TTL eviction.
    
    Also implements the VCM (Virtual Context Management) state machine
    for each session.
    """

    def __init__(self, config: ContextConfig) -> None:
        self._cfg = config
        # session_id -> MessageWindow
        self._windows: OrderedDict[str, MessageWindow] = OrderedDict()
        # session_id -> VCMState
        self._states: dict[str, VCMState] = {}
        # session_id -> last_active_time
        self._last_active: dict[str, float] = {}

    def get_window(self, session_id: str, create: bool = False, group_id: str | None = None, now: float | None = None) -> MessageWindow | None:
        """Retrieve a window from cache, updating LRU order."""
        now = now if now is not None else time.time()
        if session_id in self._windows:
            window = self._windows.pop(session_id)
            self._windows[session_id] = window # Move to end (most recent)
            self._last_active[session_id] = now
            return window
        
        if create:
            if len(self._windows) >= self._cfg.max_sessions:
                self._evict_lru()
            
            window = MessageWindow(
                session_id=session_id,
                group_id=group_id,
                start_time=now,
                last_message_time=now,
            )
            self._windows[session_id] = window
            self._states[session_id] = VCMState.FOCUSED
            self._last_active[session_id] = now
            return window
            
        return None

    def pop_window(self, session_id: str) -> MessageWindow | None:
        """Remove and return a window (e.g. when an event closes)."""
        self._states.pop(session_id, None)
        self._last_active.pop(session_id, None)
        return self._windows.pop(session_id, None)

    def update_state(self, session_id: str, drift_detected: bool = False, recall_hit: bool = False) -> VCMState:
        """Update and return the VCM state for a session."""
        if not self._cfg.vcm_enabled:
            return VCMState.FOCUSED
            
        window = self._windows.get(session_id)
        if not window:
            return VCMState.FOCUSED
            
        current_state = self._states.get(session_id, VCMState.FOCUSED)
        next_state = determine_next_state(
            current_state=current_state,
            message_count=window.message_count,
            window_size=self._cfg.window_size,
            drift_detected=drift_detected,
            recall_hit=recall_hit
        )
        self._states[session_id] = next_state
        return next_state

    def get_state(self, session_id: str) -> VCMState:
        """Get current VCM state (defaults to FOCUSED)."""
        return self._states.get(session_id, VCMState.FOCUSED)

    def cleanup_expired(self) -> int:
        """Remove sessions that haven't been active for session_idle_seconds.
        
        Returns the number of evicted sessions.
        """
        now = time.time()
        idle_threshold = self._cfg.session_idle_seconds
        to_remove = [
            sid for sid, last_t in self._last_active.items()
            if now - last_t > idle_threshold
        ]
        
        for sid in to_remove:
            self.pop_window(sid)
            
        if to_remove:
            logger.debug("[ContextManager] cleaned up %d idle sessions", len(to_remove))
        return len(to_remove)

    def _evict_lru(self) -> None:
        """Remove the oldest session to make room."""
        if not self._windows:
            return
        sid, _ = self._windows.popitem(last=False)
        self._states.pop(sid, None)
        self._last_active.pop(sid, None)
        logger.debug("[ContextManager] LRU eviction of session %s", sid)

    @property
    def active_sessions_count(self) -> int:
        return len(self._windows)
