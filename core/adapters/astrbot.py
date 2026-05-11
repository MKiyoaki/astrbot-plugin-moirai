"""Routes AstrBot messages to the boundary detector and manages event windows.

One MessageWindow per session (group or private chat). When the detector fires,
the window is persisted as an Event and the on_event_close callback is invoked
(Phase 4 will wire this to the LLM extractor).
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from ..boundary.window import MessageWindow
from ..domain.models import Event, MessageRef

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from ..boundary.detector import EventBoundaryDetector
    from ..repository.base import EventRepository
    from .identity import IdentityResolver



class MessageRouter:
    def __init__(
        self,
        event_repo: EventRepository,
        identity_resolver: IdentityResolver,
        detector: EventBoundaryDetector,
        context_manager: ContextManager,
        on_event_close: Callable[[MessageWindow], Awaitable[None]] | None = None,
    ) -> None:
        self._event_repo = event_repo
        self._resolver = identity_resolver
        self._detector = detector
        self._context_manager = context_manager
        self._on_event_close = on_event_close

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
            should_close, _ = self._detector.should_close(window, now)
            if should_close:
                await self._flush_window(window)
                window = None

        if window is None:
            window = self._context_manager.get_window(session_id, create=True, group_id=group_id, now=now)

        window.add_message(uid, text, now, display_name)
        self._context_manager.update_state(session_id)

    async def flush_all(self) -> None:
        """Flush all open windows (called on plugin shutdown)."""
        # Iterate over a snapshot of keys to avoid modification during iteration
        for session_id in list(self._context_manager._windows.keys()):
            window = self._context_manager.get_window(session_id)
            if window:
                await self._flush_window(window)

    async def _flush_window(self, window: MessageWindow) -> None:
        if self._on_event_close is not None:
            await self._on_event_close(window)
        self._context_manager.pop_window(window.session_id)
