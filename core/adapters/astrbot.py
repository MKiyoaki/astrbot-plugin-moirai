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
        on_event_close: Callable[[Event, MessageWindow], Awaitable[None]] | None = None,
    ) -> None:
        self._event_repo = event_repo
        self._resolver = identity_resolver
        self._detector = detector
        self._on_event_close = on_event_close
        self._windows: dict[str, MessageWindow] = {}

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

        window = self._windows.get(session_id)
        if window is not None:
            should_close, _reason = self._detector.should_close(window, now)
            if should_close:
                await self._flush_window(window)
                window = None

        if window is None:
            window = MessageWindow(
                session_id=session_id,
                group_id=group_id,
                start_time=now,
                last_message_time=now,
            )
            self._windows[session_id] = window

        window.add_message(uid, text, now, display_name)

    async def flush_all(self) -> None:
        """Flush all open windows (called on plugin shutdown)."""
        for window in list(self._windows.values()):
            await self._flush_window(window)
        self._windows.clear()

    async def _flush_window(self, window: MessageWindow) -> None:
        event = Event(
            event_id=str(uuid.uuid4()),
            group_id=window.group_id,
            start_time=window.start_time,
            end_time=window.last_message_time,
            participants=window.participants,
            interaction_flow=[
                MessageRef(
                    sender_uid=m.uid,
                    timestamp=m.timestamp,
                    content_hash="",
                    content_preview=m.text[:100],
                )
                for m in window.messages
            ],
            topic="",  # filled by LLM extractor in Phase 4
            chat_content_tags=[],
            salience=0.5,
            confidence=0.5,
            inherit_from=[],
            last_accessed_at=window.last_message_time,
        )
        await self._event_repo.upsert(event)
        if self._on_event_close is not None:
            await self._on_event_close(event, window)
        self._windows.pop(window.session_id, None)
