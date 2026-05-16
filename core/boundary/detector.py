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


@dataclass
class BoundaryConfig:
    time_gap_minutes: float = 30.0
    max_messages: int = 50
    max_duration_minutes: float = 60.0
    summary_trigger_rounds: int = 30
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

        # If no encoder is provided, treat max_messages as a hard cap for backward compatibility        if not self._encoder or self._encoder.dim == 0:
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
