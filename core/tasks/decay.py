"""Salience decay periodic task (daily, no LLM).

Applies exponential decay to all event salience scores and archives events
whose salience falls below the configured threshold.
"""
from __future__ import annotations

import logging
import math

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
        archived = await event_repo.archive_low_salience_events(cfg.archive_threshold)
        if archived:
            logger.info("[Decay] archived %d events (salience < %.3f)", archived, cfg.archive_threshold)

    return count


async def run_access_weighted_decay(
    event_repo: EventRepository,
    decay_config=None,  # DecayConfig | None
) -> int:
    """Per-event decay where frequently accessed events decay slower.

    Effective lambda for each event = base_lambda / (1 + access_count * weight),
    where weight defaults to 0.1 so an event accessed 10 times decays at half speed.

    Returns the number of events updated.
    """
    from ..config import DecayConfig
    cfg = decay_config or DecayConfig()
    base_lambda = cfg.lambda_
    weight = 0.1

    active_events = await event_repo.list_by_status(EventStatus.ACTIVE, limit=10_000)
    updated = 0
    for event in active_events:
        effective_lambda = base_lambda / (1.0 + event.access_count * weight)
        new_salience = max(0.0, event.salience * math.exp(-effective_lambda))
        if new_salience != event.salience:
            await event_repo.update_salience(event.event_id, new_salience)
            updated += 1

    logger.info("[Decay] access-weighted decay applied to %d events (λ_base=%.4f)", updated, base_lambda)

    if cfg.archive_threshold > 0:
        archived = await event_repo.archive_low_salience_events(cfg.archive_threshold)
        if archived:
            logger.info("[Decay] archived %d events (salience < %.3f)", archived, cfg.archive_threshold)

    return updated
