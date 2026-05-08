"""Event boundary detection using simple heuristics (v1).

No LLM is used. Topic-drift check is a stub until an embedding model is
wired in Phase 5.

Boundary signals (from CLAUDE.md spec):
  1. time_gap_since_last_message > 30 min
  2. message_count >= 20 AND topic_drift > 0.6
  3. (hard cap) message_count >= 50 OR window_duration >= 60 min
"""
from __future__ import annotations

from dataclasses import dataclass

from .window import MessageWindow


@dataclass
class BoundaryConfig:
    time_gap_minutes: float = 30.0
    max_messages: int = 20
    max_duration_minutes: float = 60.0


class EventBoundaryDetector:
    def __init__(self, config: BoundaryConfig | None = None) -> None:
        self.config = config or BoundaryConfig()

    def should_close(
        self, window: MessageWindow, now: float
    ) -> tuple[bool, str]:
        """Return (should_close, reason).

        reason is one of: "time_gap", "max_messages", "max_duration",
        or "" (no close).
        """
        cfg = self.config

        if window.age_since_last_message(now) > cfg.time_gap_minutes * 60:
            return True, "time_gap"

        if window.message_count >= cfg.max_messages:
            return True, "max_messages"

        if window.duration_seconds >= cfg.max_duration_minutes * 60:
            return True, "max_duration"

        return False, ""
