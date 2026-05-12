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
        embedding: list[float] | None = None
    ) -> None:
        msg = RawMessage(uid=uid, text=text, timestamp=timestamp, display_name=display_name, embedding=embedding)
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
