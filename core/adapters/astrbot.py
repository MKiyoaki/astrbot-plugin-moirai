"""Routes AstrBot messages to the boundary detector and manages event windows.

One MessageWindow per session (group or private chat). When the detector fires,
the window is persisted as an Event and the on_event_close callback is invoked.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Set

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from ..boundary.detector import EventBoundaryDetector
    from ..boundary.window import MessageWindow
    from ..repository.base import EventRepository
    from ..managers.context_manager import ContextManager
    from ..embedding.encoder import Encoder
    from .identity import IdentityResolver

logger = logging.getLogger(__name__)


class MessageRouter:
    def __init__(
        self,
        event_repo: EventRepository,
        identity_resolver: IdentityResolver,
        detector: EventBoundaryDetector,
        context_manager: ContextManager,
        encoder: Encoder,
        on_event_close: Callable[[MessageWindow], Awaitable[None]] | None = None,
    ) -> None:
        self._event_repo = event_repo
        self._resolver = identity_resolver
        self._detector = detector
        self._context_manager = context_manager
        self._encoder = encoder
        self._on_event_close = on_event_close
        
        # Track background brain tasks to allow waiting for them (Phase 1 performance)
        self._brain_tasks: Set[asyncio.Task] = set()

    async def process(
        self,
        platform: str,
        physical_id: str,
        display_name: str,
        text: str,
        raw_group_id: str | None,
        now: float | None = None,
    ) -> None:
        """Entry point for every incoming message.

        raw_group_id: group ID from the platform adapter, or None/"" for DM.
        now: override timestamp (for deterministic testing).
        """
        import time as _time

        now = now if now is not None else _time.time()
        group_id: str | None = raw_group_id if raw_group_id else None
        session_id = (
            f"{platform}:{group_id}" if group_id else f"{platform}:private:{physical_id}"
        )

        uid = await self._resolver.get_or_create_uid(platform, physical_id, display_name)

        window = self._context_manager.get_window(session_id, now=now)
        if window is not None:
            should_close, reason = self._detector.should_close(window, now)
            
            # If a drift was detected by a previous message's background task, close now
            if not should_close and getattr(window, "drift_detected", False):
                should_close, reason = True, "topic_drift"
            
            if should_close:
                await self._flush_window(window)
                window = None

        if window is None:
            window = self._context_manager.get_window(session_id, create=True, group_id=group_id, now=now)
            window.drift_detected = False

        # 1. Add message to window immediately (no delay)
        msg_idx = window.message_count
        window.add_message(uid, text, now, display_name)
        
        # 2. Update basic state (without drift info yet)
        self._context_manager.update_state(session_id, drift_detected=False)
        
        # 3. Trigger background brain logic (embedding + drift check)
        task = asyncio.create_task(self._process_brain_async(window, msg_idx, text))
        self._brain_tasks.add(task)
        task.add_done_callback(self._brain_tasks.discard)

    async def _process_brain_async(self, window: MessageWindow, msg_idx: int, text: str) -> None:
        """Background task for embedding calculation and drift detection."""
        try:
            # Step A: Single-pass encoding
            vecs = await self._encoder.encode_batch([text])
            if not vecs:
                return
            new_vec = vecs[0]
            
            # Step B: Attach to window (updates centroid automatically)
            window.attach_embedding(msg_idx, new_vec)
            
            # Step C: Perform drift detection (using pre-calculated centroid and new_vec)
            if await self._detector.check_drift(window, new_vec):
                window.drift_detected = True
                # Update state again with drift info
                self._context_manager.update_state(window.session_id, drift_detected=True)
                
        except Exception as exc:
            logger.warning(
                "[MessageRouter] brain background task failed (session=%s, msg_idx=%d): %s",
                getattr(window, "session_id", "?"), msg_idx, exc,
            )

    async def flush_all(self) -> None:
        """Flush all open windows (called on plugin shutdown)."""
        # 1. Wait for all pending brain tasks to finish to ensure embeddings are ready
        if self._brain_tasks:
            logger.debug("[MessageRouter] waiting for %d brain tasks to finish", len(self._brain_tasks))
            await asyncio.gather(*list(self._brain_tasks), return_exceptions=True)
            
        # 2. Iterate over a snapshot of keys to avoid modification during iteration
        for session_id in list(self._context_manager._windows.keys()):
            window = self._context_manager.get_window(session_id)
            if window:
                await self._flush_window(window)

    async def _flush_window(self, window: MessageWindow) -> None:
        if self._on_event_close is not None:
            await self._on_event_close(window)
        self._context_manager.pop_window(window.session_id)
