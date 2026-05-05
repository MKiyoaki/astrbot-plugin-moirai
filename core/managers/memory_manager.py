"""Concrete MemoryManager implementation.

Owns all memory CRUD, lifecycle management, and statistics.  main.py
instantiates one instance of this class and passes it to wherever it is
needed (scheduler tasks, retrieval hook, WebUI API handlers).

Sync guarantees (see BaseMemoryManager docstring for the contract):
  add_event:    upsert(event) → upsert_vector(event_id, embedding)
  update_event: upsert(event) → upsert_vector(event_id, embedding)
  delete_event: delete_vector(event_id) → delete(event_id)
  FTS5 entries are maintained automatically by DB triggers.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from ..domain.models import Event, EventStatus
from ..tasks.decay import run_salience_decay
from .base import BaseMemoryManager

if TYPE_CHECKING:
    from ..config import DecayConfig
    from ..embedding.encoder import Encoder
    from ..repository.base import EventRepository
    from ..retrieval.hybrid import HybridRetriever

logger = logging.getLogger(__name__)


class MemoryManager(BaseMemoryManager):
    """High-level memory façade used by main.py and the WebUI server.

    Parameters
    ----------
    event_repo:
        SQLite-backed (or in-memory) EventRepository.
    retriever:
        HybridRetriever used for BM25 + vector search.
    encoder:
        Encoder used to produce embeddings for add_event / update_event.
        Pass NullEncoder() to disable vector indexing.
    decay_config:
        DecayConfig controlling λ and archive_threshold for apply_decay().
    """

    def __init__(
        self,
        event_repo: EventRepository,
        retriever: HybridRetriever,
        encoder: Encoder,
        decay_config: DecayConfig | None = None,
    ) -> None:
        from ..config import DecayConfig as _DC
        self._repo = event_repo
        self._retriever = retriever
        self._encoder = encoder
        self._decay_cfg = decay_config or _DC()

    # ------------------------------------------------------------------
    # Event CRUD
    # ------------------------------------------------------------------

    async def add_event(self, event: Event, embedding: list[float] | None = None) -> None:
        # Step 1: INSERT into DocumentStorage (SQLite); FTS5 trigger fires here.
        await self._repo.upsert(event)
        # Step 2: store vector (no-op if NullEncoder or no embedding given).
        vec = embedding if embedding is not None else self._encode(event)
        if vec:
            await self._repo.upsert_vector(event.event_id, vec)

    async def get_event(self, event_id: str) -> Event | None:
        return await self._repo.get(event_id)

    async def get_event_by_int_id(self, rowid: int) -> Event | None:
        return await self._repo.get_by_rowid(rowid)

    async def get_event_rowid(self, event_id: str) -> int | None:
        return await self._repo.get_rowid(event_id)

    async def update_event(
        self, event: Event, embedding: list[float] | None = None
    ) -> None:
        # Step 1: UPSERT into DocumentStorage; FTS5 update trigger fires here.
        await self._repo.upsert(event)
        # Step 2: re-index vector only when embedding is explicitly provided.
        vec = embedding if embedding is not None else self._encode(event)
        if vec:
            await self._repo.upsert_vector(event.event_id, vec)

    async def delete_event(self, event_id: str) -> bool:
        return await self._repo.delete_with_vector(event_id)

    # ------------------------------------------------------------------
    # Event lifecycle
    # ------------------------------------------------------------------

    async def archive_event(self, event_id: str) -> bool:
        return await self._repo.set_status(event_id, EventStatus.ARCHIVED)

    async def unarchive_event(self, event_id: str) -> bool:
        return await self._repo.set_status(event_id, EventStatus.ACTIVE)

    async def list_active_events(self, limit: int = 100) -> list[Event]:
        return await self._repo.list_by_status(EventStatus.ACTIVE, limit=limit)

    async def list_archived_events(self, limit: int = 100) -> list[Event]:
        return await self._repo.list_by_status(EventStatus.ARCHIVED, limit=limit)

    # ------------------------------------------------------------------
    # Retrieval / search
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        limit: int = 10,
        active_only: bool = True,
    ) -> list[Event]:
        results = await self._retriever.search(query, limit=limit)
        if active_only:
            results = [e for e in results if e.status == EventStatus.ACTIVE]
        # Touch last_accessed_at for retrieved events (best-effort, non-blocking).
        now = time.time()
        for event in results:
            try:
                await self._repo.update_last_accessed(event.event_id, now)
            except Exception:
                pass
        return results

    # ------------------------------------------------------------------
    # Importance & decay
    # ------------------------------------------------------------------

    async def apply_decay(self) -> int:
        return await run_salience_decay(self._repo, self._decay_cfg)

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    async def stats(self) -> dict:
        active = await self._repo.list_by_status(EventStatus.ACTIVE, limit=100_000)
        archived = await self._repo.list_by_status(EventStatus.ARCHIVED, limit=100_000)

        saliences = [e.salience for e in active]
        avg_salience = sum(saliences) / len(saliences) if saliences else 0.0

        return {
            "active_count": len(active),
            "archived_count": len(archived),
            "total_count": len(active) + len(archived),
            "avg_salience": round(avg_salience, 4),
            "min_salience": round(min(saliences, default=0.0), 4),
            "max_salience": round(max(saliences, default=0.0), 4),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _encode(self, event: Event) -> list[float]:
        """Produce an embedding for an event's topic + tags. Returns [] on failure."""
        if self._encoder.dim == 0:
            return []
        text = event.topic
        if event.chat_content_tags:
            text += " " + " ".join(event.chat_content_tags)
        if not text.strip():
            return []
        try:
            return self._encoder.encode(text)
        except Exception as exc:
            logger.warning("[MemoryManager] encoding failed: %s", exc)
            return []
