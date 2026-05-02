"""
Core domain model — pure Python, zero I/O, zero external dependencies.
All fields are required; no defaults, so slots=True works without field().
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class MessageRef:
    """Immutable reference to a single raw message stored elsewhere."""

    sender_uid: str
    timestamp: float
    content_hash: str    # SHA-256 of the original message content
    content_preview: str  # First 200 chars for display


@dataclass(slots=True)
class Persona:
    """A participant (human or bot) with a stable cross-platform identity."""

    uid: str                                # Internal stable UUID4
    bound_identities: list[tuple[str, str]] # [(platform, physical_id), ...]
    primary_name: str
    persona_attrs: dict                     # affect_type, content_tags, description
    confidence: float                       # LLM extraction confidence [0, 1]
    created_at: float                       # Unix timestamp
    last_active_at: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")


@dataclass(slots=True)
class Event:
    """A closed conversation window — the primary unit of episodic memory."""

    event_id: str
    group_id: str | None         # None = private chat
    start_time: float
    end_time: float
    participants: list[str]      # uid list
    interaction_flow: list[MessageRef]
    topic: str                   # LLM-extracted topic summary (≤ 15 chars)
    chat_content_tags: list[str]
    salience: float              # Importance [0, 1]; decays over time
    confidence: float            # LLM extraction confidence [0, 1]
    inherit_from: list[str]      # Parent event_ids (continuation chain)
    last_accessed_at: float      # Updated on every retrieval

    def __post_init__(self) -> None:
        if not 0.0 <= self.salience <= 1.0:
            raise ValueError(f"salience must be in [0, 1], got {self.salience}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")
        if self.start_time > self.end_time:
            raise ValueError(
                f"start_time ({self.start_time}) must be <= end_time ({self.end_time})"
            )


@dataclass(slots=True)
class Impression:
    """A directional social relationship: observer perceives subject.
    Impression(A→B) ≠ Impression(B→A).
    """

    observer_uid: str
    subject_uid: str
    relation_type: str           # friend | colleague | stranger | family | rival | ...
    affect: float                # Sentiment [-1, 1]
    intensity: float             # Strength [0, 1]
    confidence: float            # [0, 1]
    scope: str                   # 'global' or a specific group_id
    evidence_event_ids: list[str]  # Events that support this impression
    last_reinforced_at: float

    def __post_init__(self) -> None:
        if not -1.0 <= self.affect <= 1.0:
            raise ValueError(f"affect must be in [-1, 1], got {self.affect}")
        if not 0.0 <= self.intensity <= 1.0:
            raise ValueError(f"intensity must be in [0, 1], got {self.intensity}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")
