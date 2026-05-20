"""Sliding message window — accumulates raw messages for one in-progress event."""
from __future__ import annotations

import time as _time
from dataclasses import dataclass, field


@dataclass
class RawMessage:
    uid: str
    text: str
    timestamp: float
    display_name: str = ""
    embedding: list[float] | None = None
    # Name of the bot persona that produced this message; None for user messages.
    bot_persona_name: str | None = None
    message_id: str = ""
    platform: str = ""
    physical_id: str = ""
    role: str = "user"
    content_hash: str = ""


@dataclass
class MessageWindow:
    """Mutable per-session state accumulating messages until an event boundary fires."""

    session_id: str
    group_id: str | None  # None = private chat
    messages: list[RawMessage] = field(default_factory=list)
    start_time: float = field(default_factory=_time.time)
    last_message_time: float = field(default_factory=_time.time)
    
    # Rolling centroid of the current window's embeddings for O(1) topic drift detection.
    # Centroid is the average vector of all messages in the window that have embeddings.
    centroid: list[float] | None = None
    _sum_vec: list[float] | None = None
    _embedded_count: int = 0

    # Most recently seen bot persona for this session. Set when a bot message
    # arrives, OR when EventHandler tells the router about a persona during
    # an LLM request (so 0-bot-message events can still be attributed).
    last_active_persona: str | None = None

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def duration_seconds(self) -> float:
        return self.last_message_time - self.start_time

    def age_since_last_message(self, now: float) -> float:
        return now - self.last_message_time

    def add_message(
        self, uid: str, text: str, timestamp: float, display_name: str = "",
        embedding: list[float] | None = None, bot_persona_name: str | None = None,
        message_id: str = "", platform: str = "", physical_id: str = "",
        role: str = "user", content_hash: str = "",
    ) -> None:
        msg = RawMessage(
            uid=uid, text=text, timestamp=timestamp, display_name=display_name,
            embedding=embedding, bot_persona_name=bot_persona_name,
            message_id=message_id, platform=platform, physical_id=physical_id,
            role=role, content_hash=content_hash,
        )
        self.messages.append(msg)
        self.last_message_time = timestamp
        
        if embedding:
            self._update_centroid(embedding)

    def attach_embedding(self, msg_idx: int, embedding: list[float]) -> None:
        """Attach an embedding to a message already in the window (for async processing)."""
        if 0 <= msg_idx < len(self.messages):
            msg = self.messages[msg_idx]
            if msg.embedding is None:
                msg.embedding = embedding
                self._update_centroid(embedding)

    def _update_centroid(self, vec: list[float]) -> None:
        """Update the rolling centroid with a new vector (O(1))."""
        if self._sum_vec is None:
            self._sum_vec = list(vec)
            self._embedded_count = 1
        else:
            # sum_vec = sum_vec + vec
            for i in range(len(self._sum_vec)):
                self._sum_vec[i] += vec[i]
            self._embedded_count += 1
        
        # Recalculate average
        self.centroid = [v / self._embedded_count for v in self._sum_vec]

    @property
    def first_text(self) -> str:
        return self.messages[0].text if self.messages else ""

    @property
    def latest_text(self) -> str:
        return self.messages[-1].text if self.messages else ""

    def clone_prefix(self, n: int) -> "MessageWindow":
        """Return a new MessageWindow containing only the first ``n`` messages.

        Used by periodic flush and persona-switch flush to materialize a
        "stable prefix" as an Event without disturbing the running window.
        The centroid of the clone is recomputed from the kept messages.
        """
        n = max(0, min(n, len(self.messages)))
        kept = self.messages[:n]
        clone = MessageWindow(
            session_id=self.session_id,
            group_id=self.group_id,
            messages=list(kept),
            start_time=kept[0].timestamp if kept else self.start_time,
            last_message_time=kept[-1].timestamp if kept else self.last_message_time,
            last_active_persona=self.last_active_persona,
        )
        for m in kept:
            if m.embedding:
                clone._update_centroid(m.embedding)
        return clone

    def drop_prefix(self, n: int) -> None:
        """Remove the first ``n`` messages in place and rebuild centroid/timestamps."""
        n = max(0, min(n, len(self.messages)))
        if n == 0:
            return
        self.messages = self.messages[n:]
        # Reset centroid state and recompute from remaining messages.
        self._sum_vec = None
        self._embedded_count = 0
        self.centroid = None
        for m in self.messages:
            if m.embedding:
                self._update_centroid(m.embedding)
        if self.messages:
            self.start_time = self.messages[0].timestamp
            self.last_message_time = self.messages[-1].timestamp
        # Note: an empty tail keeps the previous timestamps so the window can
        # be safely reused; the next add_message will overwrite them.

    @property
    def participants(self) -> list[str]:
        """Deduplicated UIDs in first-appearance order."""
        seen: set[str] = set()
        result: list[str] = []
        for m in self.messages:
            if m.uid not in seen:
                seen.add(m.uid)
                result.append(m.uid)
        return result
