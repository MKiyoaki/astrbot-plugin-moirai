"""Sliding message window — accumulates raw messages for one in-progress event."""
from __future__ import annotations

import time as _time
from dataclasses import dataclass, field


@dataclass
class RawMessage:
    uid: str
    text: str
    timestamp: float


@dataclass
class MessageWindow:
    """Mutable per-session state accumulating messages until an event boundary fires."""

    session_id: str
    group_id: str | None  # None = private chat
    messages: list[RawMessage] = field(default_factory=list)
    start_time: float = field(default_factory=_time.time)
    last_message_time: float = field(default_factory=_time.time)

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def duration_seconds(self) -> float:
        return self.last_message_time - self.start_time

    def age_since_last_message(self, now: float) -> float:
        return now - self.last_message_time

    def add_message(self, uid: str, text: str, timestamp: float) -> None:
        self.messages.append(RawMessage(uid=uid, text=text, timestamp=timestamp))
        self.last_message_time = timestamp

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
