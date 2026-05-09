"""
Core domain model — pure Python, zero I/O, zero external dependencies.
All fields are required; no defaults, so slots=True works without field().
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Validation mixins
# ---------------------------------------------------------------------------

class _BoundedMixin:
    """Bounded-interval validation helpers for domain dataclasses.

    Use ``__slots__ = ()`` so this mixin is compatible with ``slots=True``
    dataclasses: the derived dataclass will generate its own __slots__ for
    declared fields; the mixin contributes no additional slots.
    """

    __slots__ = ()

    @staticmethod
    def _check_unit(name: str, value: float) -> None:
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be in [0, 1], got {value}")

    @staticmethod
    def _check_range(name: str, value: float, lo: float, hi: float) -> None:
        if not lo <= value <= hi:
            raise ValueError(f"{name} must be in [{lo}, {hi}], got {value}")


# ---------------------------------------------------------------------------
# Event lifecycle states
# ---------------------------------------------------------------------------

class EventStatus:
    ACTIVE = "active"
    ARCHIVED = "archived"


# ---------------------------------------------------------------------------
# IPC social orientation constants
# ---------------------------------------------------------------------------

IPC_VALID_ORIENTATIONS: frozenset[str] = frozenset({
    "亲和", "活跃", "掌控", "高傲",
    "冷淡", "孤避", "顺应", "谦让",
})


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class MessageRef:
    """Immutable reference to a single raw message stored elsewhere."""

    sender_uid: str
    timestamp: float
    content_hash: str    # SHA-256 of the original message content
    content_preview: str  # First 200 chars for display


@dataclass(slots=True)
class Persona(_BoundedMixin):
    """A participant (human or bot) with a stable cross-platform identity."""

    uid: str                                # Internal stable UUID4
    bound_identities: list[tuple[str, str]] # [(platform, physical_id), ...]
    primary_name: str
    persona_attrs: dict                     # affect_type, content_tags, description
    confidence: float                       # LLM extraction confidence [0, 1]
    created_at: float                       # Unix timestamp
    last_active_at: float

    def __post_init__(self) -> None:
        self._check_unit("confidence", self.confidence)


@dataclass(slots=True)
class Event(_BoundedMixin):
    """A closed conversation window — the primary unit of episodic memory."""

    event_id: str
    group_id: str | None         # None = private chat
    start_time: float
    end_time: float
    participants: list[str]      # uid list
    interaction_flow: list[MessageRef]
    topic: str                   # LLM-extracted topic summary (≤ 30 chars)
    summary: str                 # De-noised distilled semantic summary (≤ 200 chars)
    chat_content_tags: list[str]
    salience: float              # Importance [0, 1]; decays over time
    confidence: float            # LLM extraction confidence [0, 1]
    inherit_from: list[str]      # Parent event_ids (continuation chain)
    last_accessed_at: float      # Updated on every retrieval
    status: str = field(default=EventStatus.ACTIVE)  # "active" | "archived"
    is_locked: bool = field(default=False)           # User-protected from auto-cleanup

    def __post_init__(self) -> None:
        self._check_unit("salience", self.salience)
        self._check_unit("confidence", self.confidence)
        if self.start_time > self.end_time:
            raise ValueError(
                f"start_time ({self.start_time}) must be <= end_time ({self.end_time})"
            )


@dataclass(slots=True)
class Impression(_BoundedMixin):
    """A directional social relationship: observer perceives subject.

    Impression(A→B) ≠ Impression(B→A).
    Coordinates are in the Interpersonal Circumplex (IPC) space:
      benevolence: Affiliation axis [-1, 1]  (friendly ↔ hostile)
      power:       Dominance axis  [-1, 1]  (dominant ↔ submissive)
    """

    observer_uid: str
    subject_uid: str
    ipc_orientation: str    # One of IPC_VALID_ORIENTATIONS (8 Chinese labels)
    benevolence: float      # Affiliation axis [-1, 1]  (formerly: affect)
    power: float            # Dominance axis  [-1, 1]  (new field)
    affect_intensity: float # √(B²+P²)/√2   [0, 1]   (formerly: intensity)
    r_squared: float        # Octant-fit confidence [0, 1]  (new field)
    confidence: float       # Overall extraction confidence [0, 1]
    scope: str              # 'global' or a specific group_id
    evidence_event_ids: list[str]  # Events that support this impression
    last_reinforced_at: float

    def __post_init__(self) -> None:
        self._check_range("benevolence", self.benevolence, -1.0, 1.0)
        self._check_range("power", self.power, -1.0, 1.0)
        self._check_unit("affect_intensity", self.affect_intensity)
        self._check_unit("r_squared", self.r_squared)
        self._check_unit("confidence", self.confidence)


@dataclass(slots=True, frozen=True)
class BigFiveVector(_BoundedMixin):
    """Big Five personality trait scores, each in [-1, 1].

    Used as an intermediate representation before IPC rotation.
    Positive values indicate higher trait expression.
    """

    openness: float
    conscientiousness: float
    extraversion: float
    agreeableness: float
    neuroticism: float

    def __post_init__(self) -> None:
        for name, val in (
            ("openness", self.openness),
            ("conscientiousness", self.conscientiousness),
            ("extraversion", self.extraversion),
            ("agreeableness", self.agreeableness),
            ("neuroticism", self.neuroticism),
        ):
            self._check_range(name, val, -1.0, 1.0)
