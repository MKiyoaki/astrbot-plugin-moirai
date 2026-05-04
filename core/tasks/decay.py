"""Salience decay periodic task (daily, no LLM).

Applies exponential decay to all event salience scores and archives events
whose salience falls below the configured threshold.
"""
from __future__ import annotations

import dataclasses
import logging

from ..domain.models import EventStatus
from ..repository.base import EventRepository

logger = logging.getLogger(__name__)


async def run_salience_decay(
    event_repo: EventRepository,
    decay_config=None,  # DecayConfig | None
) -> int:
    """Multiply every active event's salience by exp(-lambda_), then archive
    events whose salience drops below archive_threshold.

    Returns the number of rows whose salience was updated.
    """
    from ..config import DecayConfig
    cfg = decay_config or DecayConfig()

    count = await event_repo.decay_all_salience(cfg.lambda_)
    logger.info("[Decay] salience decay applied to %d events (λ=%.4f)", count, cfg.lambda_)

    if cfg.archive_threshold > 0:
        archived = await _archive_below_threshold(event_repo, cfg.archive_threshold)
        if archived:
            logger.info("[Decay] archived %d events (salience < %.3f)", archived, cfg.archive_threshold)

    return count


async def _archive_below_threshold(event_repo: EventRepository, threshold: float) -> int:
    active_events = await event_repo.list_by_status(EventStatus.ACTIVE, limit=10_000)
    archived = 0
    for event in active_events:
        if event.salience < threshold:
            await event_repo.set_status(event.event_id, EventStatus.ARCHIVED)
            archived += 1
    return archived
