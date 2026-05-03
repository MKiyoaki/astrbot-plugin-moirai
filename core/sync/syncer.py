"""Reverse sync: IMPRESSIONS.md → database.

When a user edits an IMPRESSIONS.md file the FileWatcher detects the change
and calls ReverseSyncer._on_change().  The syncer parses the file, raises the
confidence of every impression to the user-edit floor (0.9) so that user
edits override LLM inferences, and upserts them into the impression repository.
"""
from __future__ import annotations

import logging
from pathlib import Path

from ..domain.models import Impression
from ..repository.base import ImpressionRepository, PersonaRepository
from .parser import parse_impressions_md
from .watcher import FileWatcher

logger = logging.getLogger(__name__)

_USER_EDIT_CONFIDENCE_FLOOR = 0.9


class ReverseSyncer:
    """Wires FileWatcher callbacks to IMPRESSIONS.md files and writes to DB."""

    def __init__(
        self,
        data_dir: Path,
        persona_repo: PersonaRepository,
        impression_repo: ImpressionRepository,
        watcher: FileWatcher,
    ) -> None:
        self._data_dir = data_dir
        self._persona_repo = persona_repo
        self._impression_repo = impression_repo
        self._watcher = watcher

    async def register_all(self) -> int:
        """Register all existing IMPRESSIONS.md files with the watcher.

        Returns the number of files registered.
        """
        personas_dir = self._data_dir / "personas"
        if not personas_dir.exists():
            return 0
        count = 0
        for uid_dir in personas_dir.iterdir():
            if not uid_dir.is_dir():
                continue
            imp_file = uid_dir / "IMPRESSIONS.md"
            if imp_file.exists():
                self._register_file(imp_file, uid_dir.name)
                count += 1
        return count

    def register_persona(self, uid: str) -> None:
        """Register a single persona's IMPRESSIONS.md (called after projection)."""
        imp_file = self._data_dir / "personas" / uid / "IMPRESSIONS.md"
        if imp_file.exists():
            self._register_file(imp_file, uid)

    def _register_file(self, path: Path, subject_uid: str) -> None:
        async def _cb(p: Path) -> None:
            await self._on_change(p, subject_uid)

        self._watcher.register(path, _cb)

    async def _on_change(self, path: Path, subject_uid: str) -> None:
        """Parse the changed IMPRESSIONS.md and upsert all impressions to DB."""
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("[ReverseSyncer] could not read %s: %s", path, exc)
            return

        impressions = parse_impressions_md(content, subject_uid)
        if not impressions:
            logger.debug("[ReverseSyncer] no impressions parsed from %s", path)
            return

        count = 0
        for imp in impressions:
            # User edits override LLM inferences: raise confidence to floor
            if imp.confidence < _USER_EDIT_CONFIDENCE_FLOOR:
                imp = Impression(
                    observer_uid=imp.observer_uid,
                    subject_uid=imp.subject_uid,
                    relation_type=imp.relation_type,
                    affect=imp.affect,
                    intensity=imp.intensity,
                    confidence=_USER_EDIT_CONFIDENCE_FLOOR,
                    scope=imp.scope,
                    evidence_event_ids=imp.evidence_event_ids,
                    last_reinforced_at=imp.last_reinforced_at,
                )
            await self._impression_repo.upsert(imp)
            count += 1

        logger.info(
            "[ReverseSyncer] synced %d impression(s) from %s (subject=%s)",
            count,
            path.name,
            subject_uid,
        )
