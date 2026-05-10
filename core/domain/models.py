"""
Core domain model — pure Python, zero I/O, zero external dependencies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Validation mixins
# ---------------------------------------------------------------------------

class _BoundedMixin:
    """Bounded-interval validation helpers for domain dataclasses."""

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
    content_hash: str
    content_preview: str


@dataclass(slots=True)
class Persona(_BoundedMixin):
    """A participant (human or bot) with a stable cross-platform identity."""

    uid: str
    bound_identities: list[tuple[str, str]]
    primary_name: str
    persona_attrs: dict
    confidence: float
    created_at: float
    last_active_at: float

    def __post_init__(self) -> None:
        self._check_unit("confidence", self.confidence)


@dataclass(slots=True, kw_only=True)
class Event(_BoundedMixin):
    """A closed conversation window — the primary unit of episodic memory."""

    event_id: str = ""
    group_id: str | None = None
    start_time: float = 0.0
    end_time: float = 0.0
    participants: list[str] = field(default_factory=list)
    interaction_flow: list[MessageRef] = field(default_factory=list)
    topic: str = ""
    summary: str = ""
    chat_content_tags: list[str] = field(default_factory=list)
    salience: float = 0.5
    confidence: float = 0.8
    inherit_from: list[str] = field(default_factory=list)
    last_accessed_at: float = 0.0
    status: str = field(default=EventStatus.ACTIVE)
    is_locked: bool = field(default=False)
    bot_persona_name: str | None = None

    def __post_init__(self) -> None:
        self._check_unit("salience", self.salience)
        self._check_unit("confidence", self.confidence)
        if self.start_time > self.end_time:
            raise ValueError(
                f"start_time ({self.start_time}) must be <= end_time ({self.end_time})"
            )


@dataclass(slots=True)
class Impression(_BoundedMixin):
    """A directional social relationship."""

    observer_uid: str
    subject_uid: str
    ipc_orientation: str
    benevolence: float
    power: float
    affect_intensity: float
    r_squared: float
    confidence: float
    scope: str
    evidence_event_ids: list[str]
    last_reinforced_at: float

    def __post_init__(self) -> None:
        self._check_range("benevolence", self.benevolence, -1.0, 1.0)
        self._check_range("power", self.power, -1.0, 1.0)
        self._check_unit("affect_intensity", self.affect_intensity)
        self._check_unit("r_squared", self.r_squared)
        self._check_unit("confidence", self.confidence)


@dataclass(slots=True, frozen=True)
class BigFiveVector(_BoundedMixin):
    """Big Five personality trait scores."""

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
