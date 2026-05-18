"""Event boundary detection using simple heuristics (v1).

Includes topic-drift check using an embedding model.

Boundary signals:
  1. time_gap_since_last_message > 30 min
  2. message_count >= max_messages AND (topic_drift > threshold OR no_encoder)
  3. (hard cap) message_count >= max_messages * 2.5 OR duration >= 60 min
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .window import MessageWindow
    from ..embedding.encoder import Encoder

logger = logging.getLogger(__name__)

_MIN_GAP_SECONDS = 120.0


@dataclass
class BoundaryConfig:
    time_gap_minutes: float = 30.0
    max_messages: int = 50
    max_duration_minutes: float = 60.0
    summary_trigger_rounds: int = 50
    drift_detection_enabled: bool = True
    drift_threshold: float = 0.6
    drift_min_messages: int = 20
    drift_check_interval: int = 5


class EventBoundaryDetector:
    def __init__(
        self, 
        config: BoundaryConfig | None = None,
        encoder: Encoder | None = None
    ) -> None:
        self.config = config or BoundaryConfig()
        self._encoder = encoder

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

        # Hard cap for message count
        hard_cap = max(50, cfg.max_messages * 2)
        if window.message_count >= hard_cap:
            return True, "max_messages_hard_cap"
            
        if window.duration_seconds >= cfg.max_duration_minutes * 60:
            return True, "max_duration"

        # Round-based trigger (1 round = 2 messages: user + bot)
        if window.message_count >= cfg.summary_trigger_rounds * 2:
            return True, "summary_trigger_rounds"

        # If no encoder is provided, treat max_messages as a hard cap for backward compatibility
        if not self._encoder or self._encoder.dim == 0:
            if window.message_count >= cfg.max_messages:
                return True, "max_messages"

        return False, ""

    async def check_drift(self, window: MessageWindow, new_vec: list[float] | None) -> bool:
        """Calculate topic drift between the window's rolling centroid and the new message vector.
        
        Returns True if drift exceeds the threshold.
        """
        if not self.config.drift_detection_enabled:
            return False
            
        if new_vec is None or window.centroid is None:
            return False
            
        if window.message_count < self.config.drift_min_messages:
            return False
            
        # Optimization: Only check drift every N messages
        if (window.message_count - self.config.drift_min_messages) % self.config.drift_check_interval != 0:
            return False

        try:
            # Cosine Similarity between centroid and new message
            import math
            def cosine_similarity(v1, v2):
                dot = sum(a*b for a, b in zip(v1, v2))
                norm1 = math.sqrt(sum(a*a for a in v1))
                norm2 = math.sqrt(sum(a*a for a in v2))
                if norm1 == 0 or norm2 == 0: return 0
                return dot / (norm1 * norm2)
            
            sim = cosine_similarity(window.centroid, new_vec)
            drift = 1.0 - sim
            
            if drift > self.config.drift_threshold:
                logger.info("[BoundaryDetector] topic drift detected: %.3f (threshold: %.2f)", drift, self.config.drift_threshold)
                return True
        except Exception as exc:
            logger.debug("[BoundaryDetector] drift check failed: %s", exc)

        return False

    def find_split_index(self, window: "MessageWindow") -> int:
        """Find the best split point in a window that's at max capacity.

        Returns split_after: index of the last message in the current event.
        Messages [0..split_after] are flushed; [split_after+1..] become seed.
        Returns message_count - 1 (flush all) if no better split is found.
        """
        n = window.message_count
        if n < 2:
            return n - 1

        tail_start = n - min(20, max(3, n // 4))

        if self._encoder and self._encoder.dim > 0:
            return self._find_split_by_embedding(window, tail_start)
        return self._find_split_by_time_gap(window, tail_start)

    def _find_split_by_embedding(self, window: "MessageWindow", tail_start: int) -> int:
        """Split at the pair with maximum cosine distance in the tail.

        Falls back to time-gap if no adjacent pair has embeddings.
        """
        import math

        messages = window.messages
        best_idx = -1
        best_dist = -1.0

        for i in range(tail_start, len(messages) - 1):
            v1 = messages[i].embedding if hasattr(messages[i], "embedding") else None
            v2 = messages[i + 1].embedding if hasattr(messages[i + 1], "embedding") else None
            if v1 is None or v2 is None:
                continue
            dot = sum(a * b for a, b in zip(v1, v2))
            n1 = math.sqrt(sum(a * a for a in v1))
            n2 = math.sqrt(sum(a * a for a in v2))
            if n1 == 0 or n2 == 0:
                continue
            dist = 1.0 - dot / (n1 * n2)
            if dist > best_dist:
                best_dist = dist
                best_idx = i

        if best_idx >= 0:
            return best_idx
        return self._find_split_by_time_gap(window, tail_start)

    def _find_split_by_time_gap(self, window: "MessageWindow", tail_start: int) -> int:
        """Split at the pair with the largest time gap >= _MIN_GAP_SECONDS in the tail.

        Returns message_count - 1 if no qualifying gap is found.
        """
        messages = window.messages
        best_idx = -1
        best_gap = _MIN_GAP_SECONDS

        for i in range(tail_start, len(messages) - 1):
            gap = messages[i + 1].timestamp - messages[i].timestamp
            if gap > best_gap:
                best_gap = gap
                best_idx = i

        return best_idx if best_idx >= 0 else window.message_count - 1
