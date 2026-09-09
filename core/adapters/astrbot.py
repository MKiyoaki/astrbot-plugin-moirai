"""Routes AstrBot messages to the boundary detector and manages event windows.

One MessageWindow per session (group or private chat). When the detector fires,
the window is persisted as an Event and the on_event_close callback is invoked.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from typing import TYPE_CHECKING, Set

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from ..boundary.detector import EventBoundaryDetector
    from ..boundary.window import MessageWindow
    from ..repository.base import EventRepository
    from ..managers.context_manager import ContextManager
    from ..managers.raw_message_writer import RawMessageWriter
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
        raw_message_writer: RawMessageWriter | None = None,
    ) -> None:
        self._event_repo = event_repo
        self._resolver = identity_resolver
        self._detector = detector
        self._context_manager = context_manager
        self._encoder = encoder
        self._on_event_close = on_event_close
        self._raw_message_writer = raw_message_writer
        
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
        session_platform: str | None = None,
        session_id_override: str | None = None,
        stream_group_id: str | None = None,
        bot_persona_name: str | None = None,
    ) -> None:
        """Entry point for every incoming message.

        raw_group_id: group ID from the platform adapter, or None/"" for DM.
        now: override timestamp (for deterministic testing).
        session_platform: if given, overrides the platform component used to
            compute session_id (but not the identity lookup).  Used to make
            bot replies join the same MessageWindow as the human speakers.
        session_id_override: explicit stable stream key supplied by the adapter
            layer.  Used for platforms such as Discord where the real memory
            stream is a channel/session rather than sender private ID.
        stream_group_id: group/scope ID persisted onto Event.group_id.  Defaults
            to raw_group_id; for channel-based platforms this can be the same
            stable channel/session ID as session_id_override.
        """
        import time as _time

        now = now if now is not None else _time.time()
        group_id: str | None = stream_group_id or raw_group_id or None
        _sid_platform = session_platform or platform
        session_id = session_id_override or (
            f"{_sid_platform}:{group_id}" if group_id else f"{_sid_platform}:private:{physical_id}"
        )

        uid = await self._resolver.get_or_create_uid(platform, physical_id, display_name)

        window = self._context_manager.get_window(session_id, now=now)
        if window is not None:
            should_close, reason = self._detector.should_close(window, now)
            
            # If a drift was detected by a previous message's background task, close now
            if not should_close and getattr(window, "drift_detected", False):
                should_close, reason = True, "topic_drift"
            
            if should_close:
                if reason in ("max_messages", "max_messages_hard_cap") and window.message_count > 1:
                    split_after = self._detector.find_split_index(window)
                    if split_after < window.message_count - 1:
                        await self._flush_window_smart_split(window, split_after)
                        # window stays alive with tail messages as seed
                    else:
                        await self._flush_window(window)
                        window = None
                else:
                    await self._flush_window(window)
                    window = None

        if window is None:
            window = self._context_manager.get_window(session_id, create=True, group_id=group_id, now=now)
            window.drift_detected = False

        message_id = f"msg_{uuid.uuid4().hex}"
        content_hash = hashlib.sha256(
            f"{platform}\0{physical_id}\0{now:.6f}\0{text}".encode("utf-8", "ignore")
        ).hexdigest()
        from ..domain.models import INTERNAL_PLATFORM
        role = "assistant" if platform == INTERNAL_PLATFORM else "user"

        # 1. Add message to window immediately (no delay)
        msg_idx = window.message_count
        window.add_message(
            uid,
            text,
            now,
            display_name,
            bot_persona_name=bot_persona_name,
            message_id=message_id,
            platform=platform,
            physical_id=physical_id,
            role=role,
            content_hash=content_hash,
        )
        if bot_persona_name:
            window.last_active_persona = bot_persona_name

        await self._enqueue_raw_message(
            message_id=message_id,
            session_id=session_id,
            group_id=group_id,
            platform=platform,
            physical_id=physical_id,
            sender_uid=uid,
            display_name=display_name,
            role=role,
            text=text,
            content_hash=content_hash,
            bot_persona_name=bot_persona_name,
            created_at=now,
        )
        
        # 2. Update basic state (without drift info yet)
        self._context_manager.update_state(session_id, drift_detected=False)
        
        # 3. Trigger background brain logic (embedding + drift check)
        task = asyncio.create_task(self._process_brain_async(window, msg_idx, text))
        self._brain_tasks.add(task)
        task.add_done_callback(self._brain_tasks.discard)

    async def _enqueue_raw_message(
        self,
        *,
        message_id: str,
        session_id: str,
        group_id: str | None,
        platform: str,
        physical_id: str,
        sender_uid: str,
        display_name: str,
        role: str,
        text: str,
        content_hash: str,
        bot_persona_name: str | None,
        created_at: float,
    ) -> None:
        if self._raw_message_writer is None:
            return
        try:
            import time as _time
            from ..domain.models import RawStoredMessage

            await self._raw_message_writer.enqueue(
                RawStoredMessage(
                    message_id=message_id,
                    session_id=session_id,
                    group_id=group_id,
                    platform=platform,
                    physical_id=physical_id,
                    sender_uid=sender_uid,
                    display_name=display_name,
                    role=role,
                    text=text,
                    content_hash=content_hash,
                    bot_persona_name=bot_persona_name,
                    created_at=created_at,
                    ingested_at=_time.time(),
                )
            )
        except Exception as exc:
            logger.warning("[MessageRouter] raw message enqueue failed: %s", exc)

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

    async def prepare_persona(self, session_id: str, persona_name: str) -> None:
        """Close a different persona's window before consuming the next scoped event."""
        window = self._context_manager.get_window(session_id)
        if window is not None and window.last_active_persona and window.last_active_persona != persona_name:
            await self.flush_window_split_tail(session_id, tail=0, new_persona=persona_name)
        self.note_session_persona(session_id, persona_name)

    def note_session_persona(self, session_id: str, persona_name: str | None) -> None:
        """Record the active persona for a session on its current window.

        Called by EventHandler.handle_llm_request right after the persona name
        is resolved. Lets 0-bot-message events (pure user chatter) still be
        attributed when extracted.
        """
        if not persona_name:
            return
        window = self._context_manager.get_window(session_id)
        if window is not None:
            window.last_active_persona = persona_name

    async def flush_window_split_tail(
        self, session_id: str, tail: int = 1, new_persona: str | None = None
    ) -> bool:
        """Flush the window's prefix as an Event and keep ``tail`` newest messages.

        Used on persona switch: messages up to (but not including) the trigger
        user message become an Event under the old persona; the trigger message
        starts a fresh window under the new persona.

        Returns True if a flush happened, False if the window was too short or
        absent.
        """
        window = self._context_manager.get_window(session_id)
        if window is None:
            return False
        prefix_len = window.message_count - tail
        if prefix_len <= 0:
            # Nothing stable to flush yet; just update persona tag.
            if new_persona:
                window.last_active_persona = new_persona
            return False
        prefix = window.clone_prefix(prefix_len)
        # Drop the prefix BEFORE extraction so extraction failures don't leave
        # the window in a half-flushed state.
        window.drop_prefix(prefix_len)
        if new_persona:
            window.last_active_persona = new_persona
        if self._on_event_close is not None:
            try:
                await self._on_event_close(prefix)
            except Exception as exc:
                logger.warning(
                    "[MessageRouter] split-tail flush failed for session=%s: %s",
                    session_id, exc,
                )
                return False
        return True

    async def run_periodic_flush(
        self, interval_minutes: float, tail_keep: int, enabled_getter
    ) -> None:
        """Background loop: every interval, flush stable prefixes of all windows.

        ``enabled_getter`` is a zero-arg callable so the loop respects live config
        toggles without needing a restart.
        """
        # Minimum 0.05 minutes (3 seconds) — protects against accidentally tight
        # loops while still allowing fast-tick tests.
        interval = max(0.05, float(interval_minutes)) * 60.0
        while True:
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                return
            if not enabled_getter():
                continue
            try:
                session_ids = list(self._context_manager._windows.keys())
            except Exception:
                continue
            for sid in session_ids:
                try:
                    window = self._context_manager.get_window(sid)
                    if window is None:
                        continue
                    if window.message_count <= tail_keep:
                        continue
                    prefix_len = window.message_count - tail_keep
                    prefix = window.clone_prefix(prefix_len)
                    window.drop_prefix(prefix_len)
                    if self._on_event_close is not None:
                        await self._on_event_close(prefix)
                    logger.info(
                        "[MessageRouter] periodic flush: session=%s prefix=%d tail_kept=%d",
                        sid, prefix_len, tail_keep,
                    )
                except asyncio.CancelledError:
                    return
                except Exception as exc:
                    logger.warning(
                        "[MessageRouter] periodic flush error session=%s: %s", sid, exc,
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

    async def _flush_window_smart_split(self, window: MessageWindow, split_after: int) -> None:
        prefix = window.clone_prefix(split_after + 1)
        window.drop_prefix(split_after + 1)
        window.drift_detected = False
        if self._on_event_close is not None:
            try:
                await self._on_event_close(prefix)
            except Exception as exc:
                logger.warning(
                    "[MessageRouter] smart-split flush failed session=%s split=%d: %s",
                    window.session_id, split_after, exc,
                )

    async def _flush_window(self, window: MessageWindow) -> None:
        if self._on_event_close is not None:
            await self._on_event_close(window)
        self._context_manager.pop_window(window.session_id)
