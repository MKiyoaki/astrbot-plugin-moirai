"""Abstract base classes for all manager types.

Hierarchy:
    BaseManager                 — generic base: provides logger
      ├── BaseMemoryManager     — CRUD + lifecycle + decay + search
      └── BaseRecallManager     — retrieval pipeline + injection
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..domain.models import Event


class BaseManager:
    """Generic base class providing a logger to all manager subclasses."""

    def __init__(self) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)


class BaseMemoryManager(BaseManager, ABC):
    """Unified interface for all memory CRUD, retrieval, and lifecycle operations.

    Primary key convention
    ----------------------
    Events are identified externally by their string UUID (event_id).
    Internally, each event also carries a SQLite integer rowid that is used
    as the join key for FTS5 and vec0 indexes.  The integer rowid is exposed
    via ``get_event_rowid`` for callers that need it (e.g. low-level index
    inspection), but all high-level CRUD methods accept the string event_id.

    Sync guarantees
    ---------------
    - add_event:    INSERT → DocumentStorage (SQLite, gets rowid)
                    → FTS5  (automatic via DB trigger)
                    → vec0  (explicit upsert_vector call after INSERT)
    - update_event: UPSERT → DocumentStorage
                    → FTS5  (automatic via DB trigger)
                    → vec0  (explicit upsert_vector if embedding provided)
    - delete_event: DELETE vec0 first (by rowid lookup)
                    → DELETE DocumentStorage (triggers delete FTS5 entry)
    """

    # ------------------------------------------------------------------
    # Event CRUD
    # ------------------------------------------------------------------

    @abstractmethod
    async def add_event(self, event: Event, embedding: list[float] | None = None) -> None:
        """Persist a new event and (optionally) its vector embedding.

        Sync order: SQLite INSERT → vec0 upsert (FTS5 is trigger-driven).
        """
        ...

    @abstractmethod
    async def get_event(self, event_id: str) -> Event | None:
        """Retrieve an event by its string UUID. Returns None if not found."""
        ...

    @abstractmethod
    async def get_event_by_int_id(self, rowid: int) -> Event | None:
        """Retrieve an event by its integer SQLite rowid."""
        ...

    @abstractmethod
    async def get_event_rowid(self, event_id: str) -> int | None:
        """Return the integer rowid for an event UUID, or None if not found."""
        ...

    @abstractmethod
    async def update_event(
        self, event: Event, embedding: list[float] | None = None
    ) -> None:
        """Update an existing event.

        Sync order: SQLite UPSERT → vec0 upsert if embedding given (FTS5 is trigger-driven).
        """
        ...

    @abstractmethod
    async def delete_event(self, event_id: str) -> bool:
        """Delete an event and all its index entries.

        Sync order: vec0 DELETE → SQLite DELETE (FTS5 deletion is trigger-driven).
        Returns False if the event_id was not found.
        """
        ...

    # ------------------------------------------------------------------
    # Event lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    async def archive_event(self, event_id: str) -> bool:
        """Mark an event as archived. Returns False if not found."""
        ...

    @abstractmethod
    async def unarchive_event(self, event_id: str) -> bool:
        """Restore an archived event to active status. Returns False if not found."""
        ...

    @abstractmethod
    async def list_active_events(self, limit: int = 100) -> list[Event]:
        """Return active events ordered by start_time DESC."""
        ...

    @abstractmethod
    async def list_archived_events(self, limit: int = 100) -> list[Event]:
        """Return archived events ordered by start_time DESC."""
        ...

    # ------------------------------------------------------------------
    # Retrieval / search
    # ------------------------------------------------------------------

    @abstractmethod
    async def search(
        self,
        query: str,
        limit: int = 10,
        active_only: bool = True,
    ) -> list[Event]:
        """Hybrid BM25 + vector search over events.

        When active_only is True (default), archived events are excluded.
        """
        ...

    # ------------------------------------------------------------------
    # Importance & decay
    # ------------------------------------------------------------------

    @abstractmethod
    async def apply_decay(self) -> int:
        """Run one salience decay pass. Returns the number of rows updated."""
        ...

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    @abstractmethod
    async def stats(self) -> dict:
        """Return a dict of memory statistics (counts, salience distribution, etc.)."""
        ...


class BaseRecallManager(BaseManager, ABC):
    """Contract for the retrieval + injection pipeline."""

    @abstractmethod
    async def recall(self, query: str, group_id: str | None = None) -> list[Event]:
        """Retrieve relevant events for the given query.

        group_id is reserved for future scope filtering; pass None to search globally.
        """
        ...

    @abstractmethod
    async def recall_and_inject(
        self,
        query: str,
        req: object,
        session_id: str,
        group_id: str | None = None,
    ) -> int:
        """Recall events and inject them into the ProviderRequest.

        Returns the number of events actually injected.
        """
        ...

    @abstractmethod
    def clear_previous_injection(self, req: object) -> int:
        """Remove previously injected memory markers from req.

        Clears system_prompt, prompt, and contexts fields.
        Returns the count of injection blocks removed.
        """
        ...
