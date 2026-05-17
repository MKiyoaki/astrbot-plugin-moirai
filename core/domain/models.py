"""
Core domain model — pure Python, zero I/O, zero external dependencies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..mixins.base import SerializableMixin, ValidationMixin


# ---------------------------------------------------------------------------
# Event lifecycle states
# ---------------------------------------------------------------------------

class EventStatus:
    ACTIVE = "active"
    ARCHIVED = "archived"


class EventType:
    EPISODE = "episode"
    NARRATIVE = "narrative"


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
class Persona(SerializableMixin, ValidationMixin):
    """A participant (human or bot) with a stable cross-platform identity."""

    uid: str
    bound_identities: list[tuple[str, str]]
    primary_name: str
    persona_attrs: dict
    confidence: float
    created_at: float
    last_active_at: float
    bot_persona_name: str | None = None

    def __post_init__(self) -> None:
        self._check_unit("confidence", self.confidence)

    def to_web_node(self) -> dict[str, Any]:
        """Format as a Cytoscape-compatible node dictionary."""
        return {
            "data": {
                "id": self.uid,
                "label": self.primary_name,
                "confidence": round(self.confidence, 3),
                "attrs": self.persona_attrs,
                "bound_identities": [
                    {"platform": p, "physical_id": pid}
                    for p, pid in self.bound_identities
                ],
                "created_at": datetime.fromtimestamp(self.created_at, tz=timezone.utc).isoformat(),
                "last_active_at": datetime.fromtimestamp(self.last_active_at, tz=timezone.utc).isoformat(),
                "is_bot": any(p == "internal" for p, _ in self.bound_identities),
            }
        }


@dataclass(slots=True, kw_only=True)
class Event(SerializableMixin, ValidationMixin):
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
    event_type: str = field(default=EventType.EPISODE)

    def __post_init__(self) -> None:
        self._check_unit("salience", self.salience)
        self._check_unit("confidence", self.confidence)
        if self.start_time > self.end_time:
            raise ValueError(
                f"start_time ({self.start_time}) must be <= end_time ({self.end_time})"
            )

    def to_web_dict(self) -> dict[str, Any]:
        """Convert to WebUI-friendly dictionary with formatted timestamps."""
        def ts_to_iso(ts: float) -> str:
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

        return {
            "id": self.event_id,
            "content": self.topic or self.event_id[:8],
            "topic": self.topic or "",
            "summary": self.summary or "",
            "start": ts_to_iso(self.start_time),
            "end": ts_to_iso(self.end_time),
            "start_ts": self.start_time,
            "end_ts": self.end_time,
            "group": self.group_id,
            "salience": round(self.salience, 3),
            "confidence": round(self.confidence, 3),
            "tags": self.chat_content_tags or [],
            "inherit_from": self.inherit_from or [],
            "participants": self.participants or [],
            "status": self.status or "active",
            "is_locked": bool(self.is_locked),
            "bot_persona_name": self.bot_persona_name,
            "event_type": self.event_type,
        }


@dataclass(slots=True)
class Impression(SerializableMixin, ValidationMixin):
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
    bot_persona_name: str | None = None

    def __post_init__(self) -> None:
        self._check_range("benevolence", self.benevolence, -1.0, 1.0)
        self._check_range("power", self.power, -1.0, 1.0)
        self._check_unit("affect_intensity", self.affect_intensity)
        self._check_unit("r_squared", self.r_squared)
        self._check_unit("confidence", self.confidence)

    def to_web_edge(self) -> dict[str, Any]:
        """Format as a Cytoscape-compatible edge dictionary."""
        def ts_to_iso(ts: float) -> str:
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

        return {
            "data": {
                "id": f"{self.observer_uid}--{self.subject_uid}--{self.scope}",
                "source": self.observer_uid,
                "target": self.subject_uid,
                "label": self.ipc_orientation,
                "affect": round(self.benevolence, 3),
                "intensity": round(self.affect_intensity, 3),
                "power": round(self.power, 3),
                "r_squared": round(self.r_squared, 3),
                "confidence": round(self.confidence, 3),
                "scope": self.scope,
                "evidence_event_ids": self.evidence_event_ids,
                "last_reinforced_at": ts_to_iso(self.last_reinforced_at),
            }
        }


@dataclass(slots=True, frozen=True)
class BigFiveVector(ValidationMixin):
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
