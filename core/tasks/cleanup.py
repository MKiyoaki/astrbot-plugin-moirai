"""Periodic task for cleaning up low-salience events."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..repository.base import EventRepository
    from ..config import CleanupConfig

logger = logging.getLogger(__name__)


async def run_memory_cleanup(
    event_repo: EventRepository,
    cleanup_config: CleanupConfig,
) -> int:
    """Delete non-locked events with salience below threshold."""
    if not cleanup_config.enabled:
        return 0
        
    try:
        count = await event_repo.cleanup_low_salience_events(cleanup_config.threshold)
        if count > 0:
            logger.info("[CleanupTask] deleted %d low-salience events (threshold=%.2f)", count, cleanup_config.threshold)
        return count
    except Exception as exc:
        logger.error("[CleanupTask] failed: %s", exc)
        return 0
