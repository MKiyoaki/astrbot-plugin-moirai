"""Salience decay periodic task (daily, no LLM)."""
from __future__ import annotations

import logging

from ..repository.base import EventRepository

logger = logging.getLogger(__name__)

_DEFAULT_LAMBDA = 0.01  # exp(-0.01) ≈ 0.99; half-life ≈ 69 days


async def run_salience_decay(
    event_repo: EventRepository,
    lambda_: float = _DEFAULT_LAMBDA,
) -> int:
    """Multiply every event's salience by exp(-lambda_).

    Returns the number of rows updated.
    """
    count = await event_repo.decay_all_salience(lambda_)
    logger.info("[Decay] salience decay applied to %d events (λ=%.4f)", count, lambda_)
    return count
