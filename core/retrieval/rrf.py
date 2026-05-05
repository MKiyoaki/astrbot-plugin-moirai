"""Reciprocal Rank Fusion for combining multiple ranked result lists."""
from __future__ import annotations

from ..domain.models import Event


def rrf_fuse(
    ranked_lists: list[list[Event]],
    k: int = 60,
    limit: int = 10,
) -> list[Event]:
    """Merge ranked lists of Events using Reciprocal Rank Fusion (RRF).

    Each document's score = sum over lists of 1 / (k + rank).
    Higher scores win. Handles duplicate event_ids across lists.

    k=60 is the standard value from the original RRF paper.
    """
    scores: dict[str, float] = {}
    event_map: dict[str, Event] = {}

    for ranked in ranked_lists:
        for rank, event in enumerate(ranked, start=1):
            scores[event.event_id] = scores.get(event.event_id, 0.0) + 1.0 / (k + rank)
            event_map[event.event_id] = event

    sorted_ids = sorted(scores, key=lambda eid: -scores[eid])
    return [event_map[eid] for eid in sorted_ids[:limit]]


def rrf_scores(ranked_lists: list[list[Event]], k: int = 60) -> dict[str, float]:
    """Return event_id → raw RRF score without sorting or truncation.

    Used by RecallManager for weighted multi-signal re-ranking.
    """
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, event in enumerate(ranked, start=1):
            scores[event.event_id] = scores.get(event.event_id, 0.0) + 1.0 / (k + rank)
    return scores
