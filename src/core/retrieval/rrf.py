"""Reciprocal Rank Fusion for combining multiple ranked result lists."""
from __future__ import annotations

from ..domain.models import Event


def rrf_scores(ranked_lists: list[list[Event]], k: int = 60) -> dict[str, float]:
    """Return event_id → raw RRF score without sorting or truncation.

    Used by RecallManager for weighted multi-signal re-ranking.
    """
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, event in enumerate(ranked, start=1):
            scores[event.event_id] = scores.get(event.event_id, 0.0) + 1.0 / (k + rank)
    return scores
