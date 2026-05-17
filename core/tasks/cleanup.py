"""Periodic task for cleaning up low-salience events.

Two-phase strategy:
  1. Archive active events below salience threshold (soft delete).
  2. Permanently delete archived events older than retention_days (hard delete).

This avoids silent data loss: events are demoted to 'archived' first and can
be inspected / restored before they are permanently removed.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..repository.base import EventRepository
    from ..config import CleanupConfig

logger = logging.getLogger(__name__)


async def run_memory_cleanup(
    event_repo: EventRepository,
    cleanup_config: CleanupConfig,
) -> int:
    """Two-phase cleanup: archive low-salience events, then delete old archived ones."""
    from ..utils.perf import performance_timer
    async with performance_timer("task_cleanup"):
        if not cleanup_config.enabled:
            return 0

    total = 0
    try:
        # Phase 1: permanently delete archived events that were already past
        # the retention window before this cleanup cycle began. New archives
        # from this run should get at least one cycle of visibility.
        cutoff_ts = time.time() - cleanup_config.retention_days * 86400.0
        deleted = await event_repo.delete_old_archived_events(cutoff_ts)
        if deleted > 0:
            logger.info(
                "[CleanupTask] permanently deleted %d archived events (retention=%d days)",
                deleted, cleanup_config.retention_days,
            )
        total += deleted

        # Phase 2: demote low-salience active events to archived.
        archived = await event_repo.archive_low_salience_events(cleanup_config.threshold)
        if archived > 0:
            logger.info(
                "[CleanupTask] archived %d low-salience events (threshold=%.2f)",
                archived, cleanup_config.threshold,
            )
        total += archived

    except Exception as exc:
        logger.error("[CleanupTask] failed: %s", exc)

    return total
